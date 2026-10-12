import type { Receipt } from "../types";

const idr = new Intl.NumberFormat("id-ID", {
  style: "currency",
  currency: "IDR",
  minimumFractionDigits: 0,
  maximumFractionDigits: 2,
});

export const formatMoney = (n: number | null | undefined): string =>
  n == null ? "—" : idr.format(n);

export function formatDate(iso: string | null): string {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

/** Mirrors the schema: a NULL date/total means the extraction needs a human look. */
export const needsReview = (r: Receipt): boolean =>
  !r.restaurant || !r.purchased_at || r.total_price == null;
