import type { RawOutput, Receipt, ReceiptItem, UploadResponse } from "../types";

// Flask serialises Postgres values loosely: numeric -> "45000.00", date -> an
// RFC 822 string, and /upload returns "DD/MM/YYYY". Everything is normalised
// here so the rest of the UI only sees numbers, "YYYY-MM-DD" and "HH:MM".

type Json = Record<string, unknown>;

export const isObj = (v: unknown): v is Json =>
  typeof v === "object" && v !== null && !Array.isArray(v);

export function toNum(v: unknown): number | null {
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  if (typeof v === "string" && v.trim() !== "") {
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

export function toIsoDate(v: unknown): string | null {
  if (typeof v !== "string" || !v) return null;
  let m = /^(\d{4})-(\d{2})-(\d{2})/.exec(v);
  if (m) return `${m[1]}-${m[2]}-${m[3]}`;
  m = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(v);
  if (m) return `${m[3]}-${m[2].padStart(2, "0")}-${m[1].padStart(2, "0")}`;
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? null : d.toISOString().slice(0, 10);
}

export function toTime(v: unknown): string | null {
  if (typeof v !== "string") return null;
  const m = /^(\d{1,2}):(\d{2})/.exec(v);
  return m ? `${m[1].padStart(2, "0")}:${m[2]}` : null;
}

const toStr = (v: unknown): string | null => (typeof v === "string" && v ? v : null);

function toItems(v: unknown): ReceiptItem[] {
  if (!Array.isArray(v)) return [];
  return v.filter(isObj).map((it) => ({
    food_name: String(it.food_name ?? ""),
    line_total: toNum(it.line_total),
  }));
}

export function normalizeReceipt(v: unknown): Receipt {
  const o = isObj(v) ? v : {};
  const raw = isObj(o.raw_output) ? (o.raw_output as RawOutput) : null;
  const warnings = Array.isArray(o.warnings) ? o.warnings : raw?.warnings;
  const meta = isObj(o.meta) ? o.meta : raw && isObj(raw.meta) ? raw.meta : null;
  return {
    id: String(o.id ?? o.receipt_id ?? ""),
    restaurant: toStr(o.restaurant),
    purchased_at: toIsoDate(o.purchased_at),
    purchased_time: toTime(o.purchased_time),
    subtotal: toNum(o.subtotal),
    tax: toNum(o.tax),
    fee: toNum(o.fee),
    discount: toNum(o.discount),
    total_price: toNum(o.total_price),
    items: toItems(o.items),
    item_count: toNum(o.item_count) ?? (Array.isArray(o.items) ? o.items.length : null),
    created_at: toStr(o.created_at),
    image_path: toStr(o.image_path),
    warnings: Array.isArray(warnings) ? warnings.map(String) : [],
    meta,
    raw_output: raw,
  };
}

export function receiptFromUpload(res: UploadResponse): Receipt {
  return normalizeReceipt({
    ...res.data,
    id: res.receipt_id,
    warnings: res.warnings,
    meta: res.meta,
  });
}
