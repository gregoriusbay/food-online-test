import { useNavigate } from "react-router-dom";
import { AlertTriangle, CheckCircle2, X } from "lucide-react";
import { dismissExtraction, useExtractStore } from "../lib/extractStore";

/** One-off popup (bottom right, any page) when a background extraction finishes or fails.
 *  Gone after Review or ×; there is no notification history. */
export default function ExtractNotice() {
  const navigate = useNavigate();
  const { job } = useExtractStore();
  if (!job || job.status === "running") return null;

  const done = job.status === "done";
  return (
    <div className="fixed bottom-4 right-4 z-50 w-[calc(100%-2rem)] max-w-sm" role="status">
      <div className="card flex items-start gap-3 p-4 shadow-lg">
        {done ? (
          <CheckCircle2 size={20} className="mt-0.5 shrink-0 text-emerald-600" />
        ) : (
          <AlertTriangle size={20} className="mt-0.5 shrink-0 text-red-600" />
        )}
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold">{done ? "Receipt extracted" : "Extraction failed"}</p>
          <p className="truncate text-sm text-slate-500">{job.fileName}</p>
          {!done && <p className="mt-1 text-sm text-red-700">{job.error}</p>}
          {done && (
            <button
              className="btn-primary mt-3 px-3 py-1.5"
              onClick={() => {
                // Hand over the result and local file so the review page shows them immediately.
                navigate(`/receipts/${job.upload.receipt_id}`, { state: { upload: job.upload, file: job.file } });
                dismissExtraction();
              }}
            >
              Review
            </button>
          )}
        </div>
        <button onClick={dismissExtraction} className="text-slate-400 hover:text-slate-600" aria-label="Dismiss">
          <X size={18} />
        </button>
      </div>
    </div>
  );
}
