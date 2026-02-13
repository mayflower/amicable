import { UserX } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface SessionClaimedModalProps {
  claimedByEmail?: string;
  onDismiss: () => void;
  className?: string;
}

export function SessionClaimedModal({
  claimedByEmail,
  onDismiss,
  className,
}: SessionClaimedModalProps) {
  return (
    <div
      className={cn(
        "fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm",
        className
      )}
    >
      <div className="bg-white rounded-lg shadow-xl max-w-sm w-full mx-4 overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="bg-red-50 border-b border-red-100 px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-red-100 flex items-center justify-center">
              <UserX className="w-5 h-5 text-red-600" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900">
                Session ended
              </h2>
              <p className="text-sm text-gray-600">
                Another user took over this project
              </p>
            </div>
          </div>
        </div>

        {/* Content */}
        <div className="px-6 py-5 space-y-4">
          <p className="text-gray-700">
            Your editing session was taken over
            {claimedByEmail && (
              <>
                {" "}
                by <span className="font-medium text-gray-900">{claimedByEmail}</span>
              </>
            )}
            . You'll be redirected to the project list.
          </p>

          <Button onClick={onDismiss} className="w-full">
            Go to projects
          </Button>
        </div>
      </div>
    </div>
  );
}
