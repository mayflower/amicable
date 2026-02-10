import { MessageBus } from "./messageBus";
import type { Message } from "../types/messages";
import { MessageType, createMessage } from "../types/messages";

const isRecord = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);

export interface WebSocketBusConfig {
  url: string;
  messageBus: MessageBus;
  sessionId?: string;
}

export class WebSocketBus {
  private ws: WebSocket | null = null;
  private config: WebSocketBusConfig;
  private isReady = false;
  private disposed = false;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;
  private connectTimeoutMs = 10_000;

  constructor(config: WebSocketBusConfig) {
    this.config = config;
  }

  private websocketUrl(): string {
    const url = new URL(this.config.url);
    return url.toString();
  }

  public async connect(): Promise<WebSocket> {
    const wsUrl = this.websocketUrl();

    return await new Promise<WebSocket>((resolve, reject) => {
      let settled = false;

      const fail = (err: Error) => {
        if (settled) return;
        settled = true;
        try {
          this.ws?.close();
        } catch {
          // ignore
        }
        reject(err);
      };

      // (Re)create the socket for this attempt.
      this.ws = new WebSocket(wsUrl);

      const timeout = window.setTimeout(() => {
        fail(new Error(`WebSocket connect timeout after ${this.connectTimeoutMs}ms`));
      }, this.connectTimeoutMs);

      this.ws.onmessage = (event: MessageEvent) => {
        try {
          const rawMessage: unknown = JSON.parse(event.data);
          console.log("Received WebSocket message:", rawMessage);

          const message = this.convertRawMessage(rawMessage);
          if (message) {
            // Handle ping messages automatically
            if (message.type === MessageType.PING) {
              this.sendMessage(createMessage(MessageType.PING, {}));
            }
            this.config.messageBus.emit(message);
          }
        } catch (error) {
          console.error("Failed to parse WebSocket message:", error);
          this.config.messageBus.sendError("Failed to parse message", {
            rawData: event.data,
            error: error instanceof Error ? error.message : "Unknown error",
          });
        }
      };

      this.ws.onopen = () => {
        window.clearTimeout(timeout);
        console.log("WebSocket connected");
        this.isReady = true;
        this.reconnectAttempts = 0;
        this.config.messageBus.setConnected(true);

        const initData = this.config.sessionId
          ? { session_id: this.config.sessionId }
          : {};
        console.log("Sending INIT message with session_id:", this.config.sessionId);
        this.sendMessage(createMessage(MessageType.INIT, initData));

        if (!settled) {
          settled = true;
          resolve(this.ws!);
        }
      };

      this.ws.onclose = (event) => {
        window.clearTimeout(timeout);
        console.log("WebSocket closed:", event.code, event.reason);
        this.isReady = false;
        this.config.messageBus.setConnected(false);

        // If the connection never opened, treat close as a failed connect attempt.
        if (!settled) {
          settled = true;
          reject(new Error(`WebSocket closed before open (code=${event.code}, reason=${event.reason || "none"})`));
          return;
        }

        if (
          event.code !== 1000 &&
          this.reconnectAttempts < this.maxReconnectAttempts
        ) {
          this.scheduleReconnect();
        }
      };

      this.ws.onerror = (error) => {
        console.error("WebSocket error:", error);
        const errorMessage =
          error instanceof Error ? error.message : "WebSocket connection error";
        this.config.messageBus.sendError(errorMessage, { originalError: error });

        fail(new Error(errorMessage));
      };
    });
  }

  private scheduleReconnect(): void {
    this.reconnectAttempts++;
    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);

    console.log(
      `Scheduling reconnect attempt ${this.reconnectAttempts} in ${delay}ms`
    );

    setTimeout(() => {
      if (!this.isReady && !this.disposed) {
        this.connect().catch((error) => {
          console.error("Reconnect failed:", error);
        });
      }
    }, delay);
  }

  private convertRawMessage(rawMessage: unknown): Message | null {
    if (
      !rawMessage ||
      (isRecord(rawMessage) && Object.keys(rawMessage).length === 0)
    ) {
      return null;
    }

    if (!isRecord(rawMessage)) {
      return null;
    }

    // Handle different message formats from the server
    const topType = rawMessage["type"];
    if (typeof topType === "string" && topType) {
      // Check if the raw type is a valid MessageType enum value
      if (Object.values(MessageType).includes(topType as MessageType)) {
        const topData = isRecord(rawMessage["data"]) ? rawMessage["data"] : {};
        const topId = typeof rawMessage["id"] === "string" ? rawMessage["id"] : undefined;
        const topTs = typeof rawMessage["timestamp"] === "number" ? rawMessage["timestamp"] : undefined;
        const topError = rawMessage["error"];
        return createMessage(
          topType as MessageType,
          {
            ...topData,
            text: typeof topData["text"] === "string" ? (topData["text"] as string) : undefined,
            error: topError,
          },
          topId,
          topTs
        );
      }
    }

    // Handle nested data format
    const nestedData = rawMessage["data"];
    if (isRecord(nestedData)) {
      const nestedType = nestedData["type"];
      if (typeof nestedType === "string" && Object.values(MessageType).includes(nestedType as MessageType)) {
        const topId = typeof rawMessage["id"] === "string" ? rawMessage["id"] : undefined;
        const topTs = typeof rawMessage["timestamp"] === "number" ? rawMessage["timestamp"] : undefined;
        return createMessage(
          nestedType as MessageType,
          {
            ...nestedData,
            text:
              (typeof nestedData["text"] === "string" ? (nestedData["text"] as string) : undefined) ??
              (typeof rawMessage["text"] === "string" ? (rawMessage["text"] as string) : undefined),
            error: nestedData["error"] ?? rawMessage["error"],
          },
          topId,
          topTs
        );
      }
    }

    return null;
  }

  public sendMessage(message: Message): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      const wsMessage = {
        type: message.type,
        data: message.data,
        id: message.id,
        timestamp: message.timestamp,
      };

      const messageStr = JSON.stringify(wsMessage);
      console.log("Sending WebSocket message:", messageStr);
      this.ws.send(messageStr);
    } else {
      console.error("WebSocket is not connected");
      throw new Error("WebSocket is not connected");
    }
  }

  public disconnect(): void {
    this.disposed = true;
    if (this.ws) {
      this.ws.close(1000, "Client disconnect");
      this.ws = null;
      this.isReady = false;
    }
  }

  public getConnected(): boolean {
    return this.isReady && this.ws?.readyState === WebSocket.OPEN;
  }
}

export const createWebSocketBus = (
  url: string,
  messageBus: MessageBus,
  sessionId?: string
): WebSocketBus => {
  return new WebSocketBus({ url, messageBus, sessionId });
};
