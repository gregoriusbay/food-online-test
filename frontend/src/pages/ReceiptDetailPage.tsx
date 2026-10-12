import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import {
  AlertTriangle,
  ArrowLeft,
  Check,
  Copy,
  Download,
  Loader2,
  Plus,
  RotateCcw,
  Save,
  Trash2,
} from "lucide-react";
import { api, errorMessage } from "../api";
import { formatDate } from "../lib/format";
import { receiptFromUpload, toApiInput } from "../lib/normalize";
import type { Receipt, ReceiptFields, ReceiptInput, UploadResponse } from "../types";
import ImageViewer from "../components/ImageViewer";

interface LocationState {
  upload?: UploadResponse;
  file?: File;
}

type MoneyField = "subtotal" | "tax" | "fee" | "discount" | "total_price";

const MONEY_FIELDS: [MoneyField, string][] = [
  ["subtotal", "Subtotal"],
  ["tax", "Tax"],
  ["fee", "Fees & delivery"],
  ["discount", "Discount"],
  ["total_price", "Total paid"],
];

// Form values are strings so half-typed numbers ("12.") don't get mangled.
type FormState = { [K in keyof ReceiptFields]: string } & {
  items: { food_name: string; line_total: string }[];
};

const str = (n: number | null) => (n == null ? "" : String(n));

function toForm(r: Receipt): FormState {
  return {
    restaurant: r.restaurant ?? "",
    purchased_at: r.purchased_at ?? "",
    purchased_time: r.purchased_time ?? "",
    subtotal: str(r.subtotal),
    tax: str(r.tax),
    fee: str(r.fee),
    discount: str(r.discount),
    total_price: str(r.total_price),
    items: r.items.map((it) => ({ food_name: it.food_name, line_total: str(it.line_total) })),
  };
}

function num(v: string): number | null {
  if (v.trim() === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function fromForm(f: FormState): ReceiptInput {
  return {
    restaurant: f.restaurant.trim() || null,
    purchased_at: f.purchased_at || null,
    purchased_time: f.purchased_time || null,
    subtotal: num(f.subtotal),
    tax: num(f.tax),
    fee: num(f.fee),
    discount: num(f.discount),
    total_price: num(f.total_price),
    items: f.items
      .filter((it) => it.food_name.trim() !== "" || it.line_total.trim() !== "")
      .map((it) => ({ food_name: it.food_name.trim(), line_total: num(it.line_total) })),
  };
}

export default function ReceiptDetailPage() {
  const { id = "" } = useParams();
  return <ReceiptDetail key={id} id={id} />;
}

function ReceiptDetail({ id }: { id: string }) {
  const state = (useLocation().state ?? {}) as LocationState;
  const upload = state.upload?.receipt_id === id ? state.upload : undefined;

  const [receipt, setReceipt] = useState<Receipt | null>(() => (upload ? receiptFromUpload(upload) : null));
  const [form, setForm] = useState<FormState | null>(() => (receipt ? toForm(receipt) : null));
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<{ ok: boolean; text: string } | null>(null);
  const [tab, setTab] = useState<"fields" | "json">("fields");
  const touched = useRef(false);

  // Right after an upload, show the local file; otherwise ask the backend for the image.
  // (Not revoked: StrictMode would revoke it before the second mount.)
  const [localImage] = useState(() => (upload && state.file ? URL.createObjectURL(state.file) : null));
  const imageSrc = localImage ?? api.imageUrl(id);
  const isPdf =
    (upload && state.file?.type === "application/pdf") ||
    !!receipt?.image_path?.toLowerCase().endsWith(".pdf");

  useEffect(() => {
    let cancelled = false;
    api
      .getReceipt(id)
      .then((r) => {
        if (cancelled) return;
        // Keep warnings/meta from the upload response when GET doesn't return them.
        setReceipt((prev) => ({
          ...r,
          warnings: r.warnings.length ? r.warnings : (prev?.warnings ?? []),
          meta: r.meta ?? prev?.meta ?? null,
        }));
        setForm((prev) => (prev && touched.current ? prev : toForm(r)));
      })
      .catch((e) => !cancelled && setLoadError(e))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [id]);

  const draft = useMemo(() => (form ? fromForm(form) : null), [form]);
  const baseline = useMemo(() => (receipt ? JSON.stringify(fromForm(toForm(receipt))) : ""), [receipt]);
  const dirty = draft !== null && JSON.stringify(draft) !== baseline;

  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const edit = (patch: Partial<FormState>) => {
    touched.current = true;
    setNotice(null);
    setForm((f) => (f ? { ...f, ...patch } : f));
  };

  const editItem = (i: number, patch: Partial<FormState["items"][number]>) =>
    form && edit({ items: form.items.map((it, j) => (j === i ? { ...it, ...patch } : it)) });

  async function save() {
    if (!draft || !receipt) return;
    setSaving(true);
    setNotice(null);
    try {
      const saved = await api.updateReceipt(id, draft);
      const next: Receipt = saved
        ? { ...receipt, ...saved, warnings: receipt.warnings, meta: saved.meta ?? receipt.meta, raw_output: saved.raw_output ?? receipt.raw_output }
        : { ...receipt, ...draft, item_count: draft.items.length };
      setReceipt(next);
      setForm(toForm(next));
      touched.current = false;
      setNotice({ ok: true, text: "Changes saved" });
    } catch (e) {
      setNotice({ ok: false, text: `Could not save: ${errorMessage(e)}` });
    } finally {
      setSaving(false);
    }
  }

  function reset() {
    if (!receipt) return;
    touched.current = false;
    setNotice(null);
    setForm(toForm(receipt));
  }

  if (!receipt || !form || !draft) {
    return (
      <div className="mx-auto max-w-6xl space-y-4">
        <BackLink />
        <div className="card flex flex-col items-center gap-3 px-4 py-16 text-center">
          {loading ? (
            <Loader2 className="animate-spin text-brand-700" size={28} />
          ) : (
            <>
              <AlertTriangle className="text-amber-500" size={32} />
              <p className="text-sm text-slate-600">Could not load this receipt: {errorMessage(loadError)}</p>
            </>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <BackLink />
          <h1 className="mt-2 truncate text-2xl font-bold">{receipt.restaurant ?? "Untitled receipt"}</h1>
          <p className="text-sm text-slate-500">
            {formatDate(receipt.purchased_at)}
            {receipt.purchased_time && ` · ${receipt.purchased_time}`} · ID {id.slice(0, 8)}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {notice && (
            <span className={`flex items-center gap-1 text-sm ${notice.ok ? "text-emerald-600" : "text-red-600"}`}>
              {notice.ok ? <Check size={16} /> : <AlertTriangle size={16} />}
              {notice.text}
            </span>
          )}
          <button className="btn-secondary" onClick={reset} disabled={!dirty || saving}>
            <RotateCcw size={16} /> Reset
          </button>
          <button className="btn-primary" onClick={save} disabled={!dirty || saving}>
            {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />} Save
          </button>
        </div>
      </div>

      {loadError != null && (
        <p className="rounded-lg bg-amber-50 px-4 py-2 text-sm text-amber-800">
          Showing the result returned by the upload. Could not load the saved version: {errorMessage(loadError)}
        </p>
      )}

      <div className="grid gap-4 lg:h-[calc(100vh-12rem)] lg:grid-cols-2">
        <section className="card flex min-h-[420px] flex-col overflow-hidden">
          <ImageViewer key={imageSrc} src={imageSrc} isPdf={isPdf} />
        </section>

        <section className="card flex min-h-[420px] flex-col overflow-hidden">
          <div className="flex gap-1 border-b border-slate-100 px-3 pt-2">
            {(["fields", "json"] as const).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium ${
                  tab === t ? "border-brand-900 text-brand-900" : "border-transparent text-slate-500 hover:text-slate-700"
                }`}
              >
                {t === "fields" ? "Fields" : "JSON"}
              </button>
            ))}
          </div>

          <div className="flex-1 overflow-y-auto p-5">
            {tab === "fields" ? (
              <FieldsForm form={form} draft={draft} warnings={receipt.warnings} edit={edit} editItem={editItem} />
            ) : (
              <JsonTab receipt={receipt} draft={draft} id={id} />
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

function BackLink() {
  return (
    <Link to="/receipts" className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-brand-700">
      <ArrowLeft size={16} /> All receipts
    </Link>
  );
}

interface FieldsFormProps {
  form: FormState;
  draft: ReceiptInput;
  warnings: string[];
  edit: (patch: Partial<FormState>) => void;
  editItem: (i: number, patch: Partial<FormState["items"][number]>) => void;
}

function FieldsForm({ form, draft, warnings, edit, editItem }: FieldsFormProps) {
  return (
    <div className="space-y-6">
      {warnings.length > 0 && (
        <div className="rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-800">
          <p className="mb-1 flex items-center gap-1 font-medium">
            <AlertTriangle size={16} /> Extraction warnings
          </p>
          <ul className="list-disc space-y-0.5 pl-5">
            {warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="grid grid-cols-2 gap-4">
        <div className="col-span-2">
          <label className="label" htmlFor="restaurant">Restaurant</label>
          <input id="restaurant" className="input" value={form.restaurant} onChange={(e) => edit({ restaurant: e.target.value })} />
        </div>
        <div>
          <label className="label" htmlFor="date">Purchase date</label>
          <input id="date" type="date" className="input" value={form.purchased_at} onChange={(e) => edit({ purchased_at: e.target.value })} />
        </div>
        <div>
          <label className="label" htmlFor="time">Time</label>
          <input id="time" type="time" className="input" value={form.purchased_time} onChange={(e) => edit({ purchased_time: e.target.value })} />
        </div>
      </div>

      <div>
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-sm font-semibold">Items ({draft.items.length})</h3>
          <button
            className="inline-flex items-center gap-1 text-sm font-medium text-brand-700 hover:text-brand-900"
            onClick={() => edit({ items: [...form.items, { food_name: "", line_total: "" }] })}
          >
            <Plus size={16} /> Add item
          </button>
        </div>
        <div className="overflow-hidden rounded-lg border border-slate-200">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="w-8 px-3 py-2 font-medium">#</th>
                <th className="px-1 py-2 font-medium">Food</th>
                <th className="w-36 px-1 py-2 text-right font-medium">Line total</th>
                <th className="w-10" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {form.items.map((it, i) => (
                <tr key={i}>
                  <td className="px-3 text-slate-400">{i + 1}</td>
                  <td className="px-1 py-1">
                    <input className="input border-transparent" value={it.food_name} placeholder="Item name" onChange={(e) => editItem(i, { food_name: e.target.value })} />
                  </td>
                  <td className="px-1 py-1">
                    <input className="input border-transparent text-right tabular-nums" type="number" step="any" value={it.line_total} onChange={(e) => editItem(i, { line_total: e.target.value })} />
                  </td>
                  <td className="pr-2 text-center">
                    <button
                      className="rounded p-1 text-slate-400 hover:bg-red-50 hover:text-red-600"
                      onClick={() => edit({ items: form.items.filter((_, j) => j !== i) })}
                      aria-label={`Remove item ${i + 1}`}
                    >
                      <Trash2 size={16} />
                    </button>
                  </td>
                </tr>
              ))}
              {form.items.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-3 py-6 text-center text-slate-400">No items</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        {MONEY_FIELDS.map(([key, label]) => (
          <div key={key} className={key === "total_price" ? "col-span-2" : ""}>
            <label className="label" htmlFor={key}>{label}</label>
            <input
              id={key}
              type="number"
              step="any"
              className={`input text-right tabular-nums ${key === "total_price" ? "font-semibold" : ""}`}
              value={form[key]}
              onChange={(e) => edit({ [key]: e.target.value } as Partial<FormState>)}
            />
          </div>
        ))}
      </div>
    </div>
  );
}

function JsonTab({ receipt, draft, id }: { receipt: Receipt; draft: ReceiptInput; id: string }) {
  const [view, setView] = useState<"result" | "raw">("result");
  const [copied, setCopied] = useState(false);

  const result = { receipt_id: id, ...toApiInput(draft), warnings: receipt.warnings, meta: receipt.meta };
  const value = view === "result" ? result : receipt.raw_output;
  const text = value == null ? "" : JSON.stringify(value, null, 2);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard blocked (e.g. non-secure context); nothing useful to do */
    }
  }

  function download() {
    const url = URL.createObjectURL(new Blob([text], { type: "application/json" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `receipt-${id.slice(0, 8)}${view === "raw" ? "-raw" : ""}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="flex h-full flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="inline-flex rounded-lg bg-slate-100 p-0.5 text-sm">
          {(["result", "raw"] as const).map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              className={`rounded-md px-3 py-1 ${view === v ? "bg-white font-medium shadow-sm" : "text-slate-500"}`}
            >
              {v === "result" ? "Result" : "Raw model output"}
            </button>
          ))}
        </div>
        <button className="btn-secondary ml-auto px-3 py-1.5" onClick={copy} disabled={!text}>
          {copied ? <Check size={16} /> : <Copy size={16} />} {copied ? "Copied" : "Copy"}
        </button>
        <button className="btn-secondary px-3 py-1.5" onClick={download} disabled={!text}>
          <Download size={16} /> Download
        </button>
      </div>
      {text ? (
        <pre className="flex-1 overflow-auto rounded-lg bg-slate-900 p-4 text-xs leading-relaxed text-slate-100">{text}</pre>
      ) : (
        <p className="rounded-lg bg-slate-50 px-4 py-8 text-center text-sm text-slate-500">
          Raw output isn't available. Return <code>raw_output</code> from GET /receipts/:id to show it here.
        </p>
      )}
    </div>
  );
}
