import type { AskResponse, Receipt, ReceiptInput, UploadResponse } from "./types";
import { isObj, normalizeReceipt, toApiInput } from "./lib/normalize";

// Same-origin prefix: nginx (prod) and the Vite proxy (dev) strip it before
// forwarding to Flask, so /api/receipts reaches the route /receipts.
const BASE = "/api";

export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(message: string, status: number, body: unknown) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(BASE + path, init);
  } catch {
    throw new ApiError("Cannot reach the backend. Is it running?", 0, null);
  }
  const text = await res.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }
  if (!res.ok) {
    const message =
      isObj(body) && typeof body.error === "string"
        ? body.error
        : `${res.status} ${res.statusText}`.trim();
    throw new ApiError(message, res.status, body);
  }
  return body as T;
}

const json = (method: string, data: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(data),
});

export const api = {
  /** GET /receipts -> Receipt[] (or { receipts: [...] }). */
  async listReceipts(): Promise<Receipt[]> {
    const body = await request<unknown>("/receipts");
    const rows = Array.isArray(body) ? body : isObj(body) ? body.receipts : [];
    return Array.isArray(rows) ? rows.map(normalizeReceipt) : [];
  },

  /** GET /receipts/:id -> receipt with items (raw_output / image_path optional). */
  async getReceipt(id: string): Promise<Receipt> {
    return normalizeReceipt(await request<unknown>(`/receipts/${encodeURIComponent(id)}`));
  },

  /** PATCH /receipts/:id (dates sent as "DD/MM/YYYY"). Returns the saved receipt, or null if the body is empty. */
  async updateReceipt(id: string, input: ReceiptInput): Promise<Receipt | null> {
    const body = await request<unknown>(
      `/receipts/${encodeURIComponent(id)}`,
      json("PATCH", toApiInput(input)),
    );
    return isObj(body) && (body.id || body.receipt_id) ? normalizeReceipt(body) : null;
  },

  imageUrl: (id: string) => `${BASE}/receipts/${encodeURIComponent(id)}/image`,

  upload(file: File): Promise<UploadResponse> {
    const form = new FormData();
    form.append("file", file);
    return request<UploadResponse>("/upload", { method: "POST", body: form });
  },

  ask(question: string): Promise<AskResponse> {
    return request<AskResponse>("/ask", json("POST", { question }));
  },
};

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) {
    // A 404/405 without a JSON `error` means Flask has no such route at all.
    const hasError = isObj(e.body) && typeof e.body.error === "string";
    if (!hasError && (e.status === 404 || e.status === 405)) {
      return `${e.message}: this endpoint is not available in the backend yet.`;
    }
    return e.message;
  }
  return e instanceof Error ? e.message : String(e);
}
