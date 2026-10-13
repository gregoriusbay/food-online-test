import { useState } from "react";
import { ExternalLink, ImageOff, Maximize, ZoomIn, ZoomOut } from "lucide-react";

const STEPS = [0.5, 0.75, 1, 1.5, 2, 3];

/** Receipt image with zoom; render with `key={src}` so a new source resets it. */
export default function ImageViewer({ src, isPdf }: { src: string | null; isPdf?: boolean }) {
  const [step, setStep] = useState(2);
  const [failed, setFailed] = useState(false);

  if (!src || failed) {
    return (
      <div className="flex h-full min-h-64 flex-col items-center justify-center gap-2 text-slate-400">
        <ImageOff size={36} />
        <p className="text-sm">Image not available</p>
      </div>
    );
  }

  if (isPdf) {
    return <iframe src={src} title="Receipt" className="h-full min-h-96 w-full rounded-b-xl" />;
  }

  const zoom = STEPS[step];
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-1 border-b border-slate-100 px-3 py-2 text-slate-600">
        <button className="rounded p-1.5 hover:bg-slate-100 disabled:opacity-40" onClick={() => setStep(step - 1)} disabled={step === 0} aria-label="Zoom out">
          <ZoomOut size={18} />
        </button>
        <span className="w-12 text-center text-xs tabular-nums">{Math.round(zoom * 100)}%</span>
        <button className="rounded p-1.5 hover:bg-slate-100 disabled:opacity-40" onClick={() => setStep(step + 1)} disabled={step === STEPS.length - 1} aria-label="Zoom in">
          <ZoomIn size={18} />
        </button>
        <button className="rounded p-1.5 hover:bg-slate-100" onClick={() => setStep(2)} aria-label="Fit to panel">
          <Maximize size={18} />
        </button>
        <a href={src} target="_blank" rel="noreferrer" className="ml-auto rounded p-1.5 hover:bg-slate-100" aria-label="Open in new tab">
          <ExternalLink size={18} />
        </a>
      </div>
      <div className="flex-1 overflow-auto bg-slate-100 p-4">
        <img
          src={src}
          alt="Receipt"
          onError={() => setFailed(true)}
          style={{ width: `${zoom * 100}%` }}
          className="mx-auto max-w-none rounded bg-white shadow"
        />
      </div>
    </div>
  );
}
