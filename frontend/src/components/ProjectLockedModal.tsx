import { useState } from "react";
import { AlertTriangle, ArrowLeft, UserCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface ProjectLockedModalProps {
  lockedByEmail: string;
  lockedAt?: string;
  onTakeOver: () => void;
  onGoBack: () => void;
  className?: string;
}

export function ProjectLockedModal({
  lockedByEmail,
  lockedAt,
  onTakeOver,
  onGoBack,
  className,
}: ProjectLockedModalProps) {
  const [confirmTakeover, setConfirmTakeover] = useState(false);

  const formatLockedTime = (isoString?: string) => {
    if (!isoString) return null;
    try {
      const date = new Date(isoString);
      return date.toLocaleTimeString(undefined, {
        hour: "numeric",
        minute: "2-digit",
      });
    } catch {
      return null;
    }
  };

  const lockedTime = formatLockedTime(lockedAt);

  return (
    <div
      className={cn(
        "fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm",
        className
      )}
    >
      <div className="bg-white rounded-lg shadow-xl max-w-md w-full mx-4 overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="bg-amber-50 border-b border-amber-100 px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-amber-100 flex items-center justify-center">
              <UserCheck className="w-5 h-5 text-amber-600" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900">
                Project in use
              </h2>
              <p className="text-sm text-gray-600">
                Someone else is currently editing
              </p>
            </div>
          </div>
        </div>

        {/* Content */}
        <div className="px-6 py-5 space-y-4">
          <p className="text-gray-700">
            This project is being edited by{" "}
            <span className="font-medium text-gray-900">{lockedByEmail}</span>
            {lockedTime && (
              <span className="text-gray-500"> since {lockedTime}</span>
            )}
            .
          </p>

          {!confirmTakeover ? (
            <div className="flex flex-col sm:flex-row gap-3 pt-2">
              <Button
                variant="outline"
                onClick={onGoBack}
                className="flex-1 gap-2"
              >
                <ArrowLeft className="w-4 h-4" />
                Go back
              </Button>
              <Button
                variant="default"
                onClick={() => setConfirmTakeover(true)}
                className="flex-1"
              >
                Take over session
              </Button>
            </div>
          ) : (
            <div className="space-y-3 pt-2">
              <div className="flex items-start gap-2 p-3 bg-amber-50 rounded-md border border-amber-200">
                <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
                <p className="text-sm text-amber-800">
                  Taking over will disconnect{" "}
                  <span className="font-medium">{lockedByEmail}</span> from the
                  project. They may lose unsaved changes.
                </p>
              </div>
              <div className="flex flex-col sm:flex-row gap-3">
                <Button
                  variant="outline"
                  onClick={() => setConfirmTakeover(false)}
                  className="flex-1"
                >
                  Cancel
                </Button>
                <Button
                  variant="destructive"
                  onClick={onTakeOver}
                  className="flex-1"
                >
                  Take over anyway
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
