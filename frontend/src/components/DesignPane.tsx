import { Button } from "@/components/ui/button";
import type { DesignState } from "@/types/design";
import { Loader2 } from "lucide-react";

type DesignPaneProps = {
  state: DesignState | null;
  loading: boolean;
  batchStarting: boolean;
  iterating: boolean;
  batchProgress: number;
  error: string | null;
  canGenerate: boolean;
  onGenerate: () => void;
  onAccept: (approachId: string) => void;
  onContinue: () => void;
  onStop: () => void;
};

const imageSrc = (mimeType: string, b64: string) => `data:${mimeType};base64,${b64}`;

export const DesignPane = ({
  state,
  loading,
  batchStarting,
  iterating,
  batchProgress,
  error,
  canGenerate,
  onGenerate,
  onAccept,
  onContinue,
  onStop,
}: DesignPaneProps) => {
  return (
    <div className="h-full min-h-0 overflow-auto bg-card">
      <div className="p-6 flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-base font-semibold">Design Concepts</div>
            <div className="text-xs text-muted-foreground">
              Generate two layout directions from the current preview screenshot.
            </div>
          </div>
          <Button
            onClick={onGenerate}
            disabled={!canGenerate || loading || iterating}
          >
            {loading ? "Generating..." : "Generate Concepts"}
          </Button>
        </div>

        {error ? (
          <div className="border border-red-400 rounded-md p-3 text-sm text-destructive">
            {error}
          </div>
        ) : null}

        {state ? (
          <div className="text-xs text-muted-foreground">
            Viewport: {state.viewport_width}x{state.viewport_height}
            {" • "}
            Iterations: {state.total_iterations}
          </div>
        ) : null}

        {batchStarting && !iterating ? (
          <div className="border border-border rounded-md p-3 bg-muted/30 flex items-center gap-2 text-sm">
            <Loader2 size={14} className="animate-spin" />
            <span>Design batch started. Preparing first iteration...</span>
          </div>
        ) : null}

        {iterating ? (
          <div className="border border-border rounded-md p-3 bg-muted/30 flex items-center gap-2 text-sm">
            <Loader2 size={14} className="animate-spin" />
            <span>
              Applying selected design. Batch progress: {batchProgress}/5
            </span>
          </div>
        ) : null}

        {state?.pending_continue_decision ? (
          <div className="border border-border rounded-md p-4 bg-muted/30">
            <div className="font-medium text-sm">Continue refining?</div>
            <div className="text-xs text-muted-foreground mt-1">
              Completed 5 iterations. Continue with 5 more or stop.
            </div>
            <div className="mt-3 flex gap-2">
              <Button onClick={onContinue} disabled={loading || iterating}>
                Continue (5 more)
              </Button>
              <Button
                variant="secondary"
                onClick={onStop}
                disabled={loading || iterating}
              >
                Good enough
              </Button>
            </div>
          </div>
        ) : null}

        {!state?.approaches?.length ? (
          <div className="border border-dashed border-border rounded-md p-6 text-sm text-muted-foreground">
            No concepts yet. Generate concepts to start design exploration.
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {state.approaches.map((approach) => {
              const selected = state.selected_approach_id === approach.approach_id;
              return (
                <div
                  key={approach.approach_id}
                  className="border border-border rounded-md bg-background overflow-hidden flex flex-col"
                >
                  <div className="p-3 flex flex-col gap-2">
                    <div className="font-medium text-sm">{approach.title}</div>
                    <div className="text-xs text-muted-foreground">
                      {approach.rationale}
                    </div>
                  </div>
                  <div className="aspect-video bg-muted/20 flex items-center justify-center">
                    {approach.image_base64 ? (
                      <img
                        src={imageSrc(approach.mime_type, approach.image_base64)}
                        alt={approach.title}
                        className="w-full h-full object-cover"
                      />
                    ) : (
                      <div className="text-xs text-muted-foreground">
                        No preview image
                      </div>
                    )}
                  </div>
                  <div className="p-3 flex flex-col gap-2">
                    <Button
                      onClick={() => onAccept(approach.approach_id)}
                      disabled={loading || iterating}
                      variant={selected ? "secondary" : "default"}
                    >
                      {selected ? "Selected" : "Accept this design"}
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
