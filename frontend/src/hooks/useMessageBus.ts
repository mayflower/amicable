import { useState, useEffect, useRef, useCallback } from "react";
import { MessageBus } from "../services/messageBus";
import { WebSocketBus, createWebSocketBus } from "../services/websocketBus";
import type { Message, PermissionMode, ThinkingLevel } from "../types/messages";
import { MessageType } from "../types/messages";

interface UseMessageBusConfig {
  wsUrl: string;
  sessionId?: string;
  permissionMode?: PermissionMode;
  thinkingLevel?: ThinkingLevel;
  handlers?: {
    [K in MessageType]?: (message: Message) => void;
  };
  onConnect?: () => void;
  onDisconnect?: () => void;
  onError?: (error: string) => void;
}

interface UseMessageBusReturn {
  isConnecting: boolean;
  isConnected: boolean;
  error: string | null;
  connect: () => Promise<void>;
  disconnect: () => void;
  send: (type: MessageType, payload: Record<string, unknown>) => void;
}

export const useMessageBus = ({
  wsUrl,
  sessionId,
  permissionMode,
  thinkingLevel,
  handlers = {},
  onConnect,
  onDisconnect,
  onError,
}: UseMessageBusConfig): UseMessageBusReturn => {
  const [isConnecting, setIsConnecting] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const messageBusRef = useRef<MessageBus | null>(null);
  const webSocketRef = useRef<WebSocketBus | null>(null);
  const handlersRef = useRef(handlers);
  const isConnectingRef = useRef(false);
  const lastConnectParamsRef = useRef<{
    wsUrl: string;
    sessionId?: string;
    permissionMode?: PermissionMode;
    thinkingLevel?: ThinkingLevel;
  } | null>(null);

  // Keep latest callbacks without forcing MessageBus recreation.
  const onConnectRef = useRef(onConnect);
  const onDisconnectRef = useRef(onDisconnect);
  const onErrorRef = useRef(onError);

  useEffect(() => {
    onConnectRef.current = onConnect;
  }, [onConnect]);

  useEffect(() => {
    onDisconnectRef.current = onDisconnect;
  }, [onDisconnect]);

  useEffect(() => {
    onErrorRef.current = onError;
  }, [onError]);

  // Update handlers ref when handlers change
  useEffect(() => {
    handlersRef.current = handlers;
  }, [handlers]);

  // Initialize message bus
  useEffect(() => {
    messageBusRef.current = new MessageBus({
      onMessage: (message) => {
        console.log("MessageBus received:", message);

        // Call the specific handler for this message type if it exists
        const handler = handlersRef.current[message.type];
        if (handler) {
          try {
            handler(message);
          } catch (error) {
            console.error(`Error in handler for ${message.type}:`, error);
            onErrorRef.current?.(`Handler error for ${message.type}: ${error}`);
          }
        } else {
          // Default handling for unhandled message types
          console.log(
            `No handler registered for message type: ${message.type}`
          );
        }
      },
      onError: (errorMsg) => {
        console.error("MessageBus error:", errorMsg);
        setError(errorMsg);
        onErrorRef.current?.(errorMsg);
      },
      onConnect: () => {
        console.log("MessageBus connected");
        setIsConnected(true);
        setIsConnecting(false);
        isConnectingRef.current = false;
        setError(null);
        onConnectRef.current?.();
      },
      onDisconnect: () => {
        console.log("MessageBus disconnected");
        setIsConnected(false);
        setIsConnecting(false);
        isConnectingRef.current = false;
        onDisconnectRef.current?.();
      },
    });

    return () => {
      messageBusRef.current?.clear();
    };
  }, []);

  const connect = useCallback(async () => {
    if (!messageBusRef.current) {
      throw new Error("MessageBus not initialized");
    }

    // Prevent multiple simultaneous connection attempts
    if (isConnectingRef.current) {
      console.log("Connection already in progress, skipping...");
      return;
    }

    const nextParams = { wsUrl, sessionId, permissionMode, thinkingLevel };
    const prevParams = lastConnectParamsRef.current;
    const sameParams =
      prevParams &&
      prevParams.wsUrl === nextParams.wsUrl &&
      prevParams.sessionId === nextParams.sessionId &&
      prevParams.permissionMode === nextParams.permissionMode &&
      prevParams.thinkingLevel === nextParams.thinkingLevel;

    if (isConnected && webSocketRef.current && sameParams) {
      console.log("Already connected with same parameters, skipping...");
      return;
    }

    // Disconnect existing connection first
    if (webSocketRef.current) {
      console.log("Disconnecting existing connection before reconnecting...");
      webSocketRef.current.disconnect();
      webSocketRef.current = null;
    }

    isConnectingRef.current = true;
    setIsConnecting(true);
    setError(null);

    try {
      console.log(
        "Creating new WebSocket connection with sessionId:",
        sessionId
      );
      webSocketRef.current = createWebSocketBus(
        wsUrl,
        messageBusRef.current,
        sessionId,
        permissionMode,
        thinkingLevel
      );
      lastConnectParamsRef.current = nextParams;
      await webSocketRef.current.connect();
    } catch (err) {
      console.error("Failed to connect:", err);
      setIsConnecting(false);
      setIsConnected(false);
      isConnectingRef.current = false;
      setError(err instanceof Error ? err.message : "Failed to connect");
    }
  }, [wsUrl, sessionId, permissionMode, thinkingLevel, isConnected]);

  const disconnect = useCallback(() => {
    if (webSocketRef.current) {
      webSocketRef.current.disconnect();
      webSocketRef.current = null;
    }
    isConnectingRef.current = false;
    setIsConnecting(false);
    setIsConnected(false);
  }, []);

  const send = useCallback(
    (type: MessageType, payload: Record<string, unknown> = {}) => {
      if (isConnected && webSocketRef.current) {
        try {
          const message = {
            type,
            data: {
              ...payload,
              ...(sessionId && { session_id: sessionId }),
            },
            timestamp: Date.now(),
          };
          console.log("Sending message:", message);
          webSocketRef.current.sendMessage(message);
        } catch (err) {
          console.error("Failed to send message:", err);
          setError("Failed to send message. Please check your connection.");
        }
      } else {
        setError("Not connected to Workspace.");
      }
    },
    [isConnected, sessionId]
  );

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (webSocketRef.current) {
        webSocketRef.current.disconnect();
      }
      isConnectingRef.current = false;
    };
  }, []);

  // Reconnect when connection parameters change (but only if we were previously connected).
  useEffect(() => {
    if (!isConnected || !webSocketRef.current) return;
    console.log("Connection parameters changed, reconnecting...");
    connect().catch((e) => console.error("Reconnect failed:", e));
  }, [wsUrl, sessionId, permissionMode, thinkingLevel, isConnected, connect]);

  return {
    isConnecting,
    isConnected,
    error,
    connect,
    disconnect,
    send,
  };
};
