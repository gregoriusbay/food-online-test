export interface ReceiptItem {
  food_name: string;
  line_total: number | null;
}

/** Editable receipt fields. In the UI dates are "YYYY-MM-DD" (for <input type="date">);
 *  on the wire they are "DD/MM/YYYY" (see toApiInput). Times are "HH:MM". */
export interface ReceiptFields {
  restaurant: string | null;
  purchased_at: string | null;
  purchased_time: string | null;
  subtotal: number | null;
  tax: number | null;
  fee: number | null;
  discount: number | null;
  total_price: number | null;
}

/** Body of PATCH /receipts/:id (after toApiInput). */
export interface ReceiptInput extends ReceiptFields {
  items: ReceiptItem[];
}

/** A receipt as the UI uses it; optional fields depend on what the endpoint returns. */
export interface Receipt extends ReceiptInput {
  id: string;
  item_count: number | null;
  created_at: string | null;
  image_path: string | null;
}

/** Response of POST /upload. `data` dates are "DD/MM/YYYY" (extract.postprocess). */
export interface UploadResponse {
  filename: string;
  receipt_id: string;
  data: ReceiptInput;
}

export interface ToolCall {
  tool: string;
  args: Record<string, unknown>;
}

export interface AskResponse {
  question: string;
  answer: string;
  tool_calls: ToolCall[];
}
