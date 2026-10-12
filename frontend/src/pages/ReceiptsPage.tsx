import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AlertTriangle, ChevronRight, Plus, RefreshCw, ScanLine, Search } from "lucide-react";
import { api, errorMessage } from "../api";
import { formatDate, formatMoney, needsReview } from "../lib/format";
import type { Receipt } from "../types";
import UploadModal from "../components/UploadModal";

export default function ReceiptsPage() {
  const navigate = useNavigate();
  const [receipts, setReceipts] = useState<Receipt[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [query, setQuery] = useState("");
  const [showUpload, setShowUpload] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .listReceipts()
      .then((r) => !cancelled && setReceipts(r))
      .catch((e) => !cancelled && setError(e));
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  const reload = () => {
    setReceipts(null);
    setError(null);
    setReloadKey((k) => k + 1);
  };

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (receipts ?? []).filter((r) => !q || (r.restaurant ?? "").toLowerCase().includes(q));
  }, [receipts, query]);

  const stats = useMemo(() => {
    const list = receipts ?? [];
    return {
      count: list.length,
      spent: list.reduce((s, r) => s + (r.total_price ?? 0), 0),
      review: list.filter(needsReview).length,
    };
  }, [receipts]);

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Extracted receipts</h1>
          <p className="text-sm text-slate-500">
            Upload a receipt, then review and correct what the model extracted.
          </p>
        </div>
        <button className="btn-primary" onClick={() => setShowUpload(true)}>
          <Plus size={18} /> Extract receipt
        </button>
      </div>

      {receipts && receipts.length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <Stat label="Receipts" value={String(stats.count)} />
          <Stat label="Total spent" value={formatMoney(stats.spent)} />
          <Stat label="Needs review" value={String(stats.review)} warn={stats.review > 0} />
        </div>
      )}

      <div className="card overflow-hidden">
        <div className="flex items-center gap-3 border-b border-slate-100 p-4">
          <div className="relative flex-1 sm:max-w-xs">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              className="input pl-9"
              placeholder="Search restaurant"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <button className="btn-secondary ml-auto px-3" onClick={reload} aria-label="Refresh">
            <RefreshCw size={16} />
          </button>
        </div>

        {error ? (
          <div className="flex flex-col items-center gap-3 px-4 py-16 text-center">
            <AlertTriangle className="text-amber-500" size={32} />
            <p className="text-sm text-slate-600">Could not load receipts: {errorMessage(error)}</p>
            <button className="btn-secondary" onClick={reload}>Try again</button>
          </div>
        ) : receipts === null ? (
          <div className="space-y-3 p-4">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="h-10 animate-pulse rounded bg-slate-100" />
            ))}
          </div>
        ) : receipts.length === 0 ? (
          <div className="flex flex-col items-center gap-3 px-4 py-16 text-center">
            <ScanLine size={36} className="text-slate-300" />
            <p className="font-medium">No receipts yet</p>
            <p className="text-sm text-slate-500">Extract your first receipt to see it here.</p>
            <button className="btn-primary" onClick={() => setShowUpload(true)}>
              <Plus size={18} /> Extract receipt
            </button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-4 py-3 font-medium">Restaurant</th>
                  <th className="px-4 py-3 font-medium">Purchased</th>
                  <th className="px-4 py-3 text-right font-medium">Items</th>
                  <th className="px-4 py-3 text-right font-medium">Total</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="w-10" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {visible.map((r) => (
                  <tr
                    key={r.id}
                    onClick={() => navigate(`/receipts/${r.id}`)}
                    className="cursor-pointer hover:bg-slate-50"
                  >
                    <td className="px-4 py-3 font-medium">
                      <Link to={`/receipts/${r.id}`} onClick={(e) => e.stopPropagation()} className="hover:text-brand-700">
                        {r.restaurant ?? <span className="italic text-slate-400">Unknown</span>}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {formatDate(r.purchased_at)}
                      {r.purchased_time && <span className="text-slate-400"> · {r.purchased_time}</span>}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums text-slate-600">{r.item_count ?? "—"}</td>
                    <td className="px-4 py-3 text-right font-medium tabular-nums">{formatMoney(r.total_price)}</td>
                    <td className="px-4 py-3">
                      {needsReview(r) ? (
                        <span className="rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700">Needs review</span>
                      ) : (
                        <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700">Extracted</span>
                      )}
                    </td>
                    <td className="pr-4 text-slate-300">
                      <ChevronRight size={18} />
                    </td>
                  </tr>
                ))}
                {visible.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-4 py-10 text-center text-slate-500">
                      No receipts match “{query}”.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {showUpload && <UploadModal onClose={() => setShowUpload(false)} />}
    </div>
  );
}

function Stat({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className="card px-5 py-4">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-1 text-2xl font-semibold tabular-nums ${warn ? "text-amber-600" : ""}`}>{value}</p>
    </div>
  );
}
