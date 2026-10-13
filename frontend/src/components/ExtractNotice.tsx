import { AlertTriangle, X } from "lucide-react";
import { dismissExtraction, useExtractStore } from "../lib/extractStore";

/** One-off popup (bottom right, any page) when a background extraction fails.
 *  A successful extraction just appears in the receipts table. */
export default function ExtractNotice() {
  const { job } = useExtractStore();
  if (job?.status !== "error") return null;

  return (
    <div className="fixed bottom-4 right-4 z-50 w-[calc(100%-2rem)] max-w-sm" role="alert">
      <div className="card flex items-start gap-3 p-4 shadow-lg">
        <AlertTriangle size={20} className="mt-0.5 shrink-0 text-red-600" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold">Extraction failed</p>
          <p className="truncate text-sm text-slate-500">{job.fileName}</p>
          <p className="mt-1 text-sm text-red-700">{job.error}</p>
        </div>
        <button onClick={dismissExtraction} className="text-slate-400 hover:text-slate-600" aria-label="Dismiss">
          <X size={18} />
        </button>
      </div>
    </div>
  );
}
