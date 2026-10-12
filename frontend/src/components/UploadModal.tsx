import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { FileText, Loader2, UploadCloud, X } from "lucide-react";
import { api, errorMessage } from "../api";

// Must match ALLOWED_EXT in backend/api.py.
const ACCEPTED = [".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".pdf"];

export default function UploadModal({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => () => {
    if (preview) URL.revokeObjectURL(preview);
  }, [preview]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !busy) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onClose]);

  function pick(f: File | undefined) {
    if (!f) return;
    const ext = f.name.slice(f.name.lastIndexOf(".")).toLowerCase();
    if (!ACCEPTED.includes(ext)) {
      setError(`"${ext}" is not supported. Use ${ACCEPTED.join(", ")}.`);
      return;
    }
    setError(null);
    setFile(f);
    setPreview(f.type.startsWith("image/") ? URL.createObjectURL(f) : null);
  }

  async function extract() {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.upload(file);
      // The detail page shows this result (and the local image) right away,
      // even before GET /receipts/:id is available.
      navigate(`/receipts/${res.receipt_id}`, { state: { upload: res, file } });
    } catch (e) {
      setError(errorMessage(e));
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="card w-full max-w-lg">
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
          <h2 className="font-semibold">Extract a receipt</h2>
          <button onClick={onClose} disabled={busy} className="text-slate-400 hover:text-slate-600" aria-label="Close">
            <X size={20} />
          </button>
        </div>

        <div className="space-y-4 p-5">
          <div
            role="button"
            tabIndex={0}
            onClick={() => !busy && inputRef.current?.click()}
            onKeyDown={(e) => e.key === "Enter" && !busy && inputRef.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              if (!busy) pick(e.dataTransfer.files[0]);
            }}
            className={`flex min-h-48 cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed p-4 text-center transition-colors ${
              dragging ? "border-brand-600 bg-brand-50" : "border-slate-300 hover:border-brand-600"
            }`}
          >
            {preview ? (
              <img src={preview} alt="Selected receipt" className="max-h-60 rounded object-contain" />
            ) : file ? (
              <FileText size={40} className="text-slate-400" />
            ) : (
              <>
                <UploadCloud size={40} className="text-slate-400" />
                <p className="text-sm text-slate-600">
                  <span className="font-medium text-brand-700">Choose a file</span> or drag it here
                </p>
                <p className="text-xs text-slate-400">JPG, PNG, BMP, TIFF or PDF · max 10 MB</p>
              </>
            )}
            {file && <p className="truncate text-sm text-slate-600">{file.name}</p>}
          </div>
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPTED.join(",")}
            className="hidden"
            onChange={(e) => pick(e.target.files?.[0])}
          />

          {busy && (
            <p className="flex items-center gap-2 rounded-lg bg-brand-50 px-3 py-2 text-sm text-brand-900">
              <Loader2 size={16} className="animate-spin" />
              Reading the receipt… this can take a few minutes on CPU.
            </p>
          )}
          {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
        </div>

        <div className="flex justify-end gap-2 border-t border-slate-100 px-5 py-4">
          <button className="btn-secondary" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button className="btn-primary" onClick={extract} disabled={!file || busy}>
            {busy && <Loader2 size={16} className="animate-spin" />}
            Extract
          </button>
        </div>
      </div>
    </div>
  );
}
