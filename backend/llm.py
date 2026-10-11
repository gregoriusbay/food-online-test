"""llm.py -- the MODEL part: config, prompt, schema, page rendering, Ollama calls
(extraction + embeddings). Knows nothing about post-processing or the database."""
from __future__ import annotations

import datetime
import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import ollama
import pymupdf as fitz

# LLM Config
MODEL = "qwen3-vl:8b-instruct"
DPI = 200
MAX_DIM = 1536
MAX_PAGES = 8
N_CTX = 8192
NUM_PREDICT = 8192
NUM_THREAD = 0

# Embedding Config
EMBED_MODEL = "nomic-embed-text"
EMBED_DIM = 768   

# Schema Nullable Format
_NULLABLE_STR = ["string", "null"]
_NULLABLE_NUM = ["number", "null"]

# User Instructions
USER_INSTRUCTION = (
    "Extract the data from the document in the image(s) following the field list, "
    "including every row of the transaction table exactly once."
)

# General rules. The field list + descriptions are appended automatically from SCHEMA (below).
SYSTEM_RULES = """You are a document extraction engine for Food Receipt.
Your output is only ONE JSON object, no markdown. Extract only what is visible; use null if absent.
Numbers: plain JSON numbers, no thousand separators, no currency symbol. Keep real
decimals: "991,145.94" -> 991145.94 ; Indonesian "1.280.000" -> 1280000 ;
"1.345.667" -> 1345667 ; "615,000.00" -> 615000.

dates: ALWAYS CONVERT to DD/MM/YYYY (2-digit day, 2-digit month, 4-digit year),
whatever format is printed. Do not copy the printed format. Indonesian documents are
day-first. Month names (Indonesian or English) become their number.
  "8 Maret 2025" -> "08/03/2025"      "2025-03-08"  -> "08/03/2025"
  "08-Mar-25"    -> "08/03/2025"      "8.3.2025"    -> "08/03/2025"
  "Jakarta, 17 Agustus 2025" -> "17/08/2025"   (drop city; the time goes to purchased_time)
purchased_time: the time printed next to the date, as 24-hour "HH:MM".
  "12.30" -> "12:30"    "7:05 PM" -> "19:05"    "19:05:33" -> "19:05"    none printed -> null

items: one object per food/drink line, no repeats.
- food_name: the food/drink name only. Remove any quantity marker such as
  "2x", "x2", "2 x" from the name.
  "2x Cheese Burger" -> "Cheese Burger"
- line_total: the price printed on that line (the rightmost price), as a plain
  number. Copy it as printed; do NOT multiply or divide it.
  "2x Cheese Burger    Rp 64.000" -> {"food_name": "Cheese Burger", "line_total": 64000}
  "Es Teh Manis        8.000"     -> {"food_name": "Es Teh Manis", "line_total": 8000}
- If a price is crossed out and a lower price is shown next to it, line_total is
  the price actually charged (the one NOT crossed out).
- Option / note lines under an item WITHOUT their own price (e.g. "Level 3",
  "Tanpa es", "Catatan: pedas") are NOT items -- skip them.
  Add-on lines WITH their own price (e.g. "+ Extra Cheese  5.000") ARE separate items.
- Do NOT list summary/fee/payment lines as items, even when they show a Rupiah
  amount: Subtotal, Total, Total Pembayaran, Ongkos Kirim / Ongkir / Delivery Fee,
  Biaya Layanan / Service Fee, Biaya Pemesanan / Order Fee, Biaya Kemasan /
  Packaging Fee, Biaya Aplikasi, Tip, Pajak / PB1 / PPN, Diskon / Promo /
  Voucher / Potongan, and payment method lines (GoPay, OVO, ShopeePay, Cash).
  Those are not food.

tax = Pajak / PB1 / PPN only.
fee = SUM of every other added charge: Ongkir / Delivery Fee, Biaya Layanan / Service
Fee / Service Charge, Biaya Pemesanan / Order Fee, Biaya Kemasan / Packaging Fee,
Biaya Aplikasi, Tip. Positive number, null if none. Tax is NOT a fee.

total_price = the FINAL amount payable: the last figure at the bottom of the footer,
after every intermediate Subtotal, tax, deduction and added charge. Do not
stop at the first total-like line.

Example -- receipt lines:
  "2x Cheese Burger            64.000"
  "   Level: Pedas"
  "Es Teh Manis                 8.000"
  "+ Extra Cheese               5.000"
  "Subtotal                    77.000"
  "Biaya Layanan                3.000"
  "Diskon Promo               -15.000"
  "Total Pembayaran            65.000"
-> items = [{"food_name": "Cheese Burger", "line_total": 64000},
            {"food_name": "Es Teh Manis",  "line_total": 8000},
            {"food_name": "Extra Cheese",  "line_total": 5000}]
-> subtotal = 77000
-> fee = 3000                (Biaya Layanan)
-> discount = 15000          (positive number)
-> total_price = 65000       (the LAST total actually paid, not the subtotal)
   "Level: Pedas" is an option line -> skipped.
   Diskon are fees/discount -> not items."""




SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "restaurant": {
            "type": _NULLABLE_STR,
            "description": "Restaurant / merchant name, usually at the top of the receipt. "
                           "Name only, without branch address.",
        },
        "purchased_at": {
            "type": _NULLABLE_STR,
            "description": "Order date CONVERTED to 'DD/MM/YYYY', date only (the time goes to purchased_time). "
                           "Example: '11 Okt 2026, 12.30' -> '11/10/2026'",
        },
        "purchased_time": {
            "type": _NULLABLE_STR,
            "description": "Order time as 24-hour 'HH:MM'. null if no time is printed. "
                           "Example: '11 Okt 2026, 12.30' -> '12:30'; '7:05 PM' -> '19:05'",
        },
        "items": {
            "type": "array",
            "description": "Every food/drink line ordered, once each. Do NOT include subtotal, "
                           "delivery fee, service fee, discount, or total lines.",
            "items": {
                "type": "object",
                "properties": {
                    "food_name": {
                        "type": "string",
                        "description": "Food/drink name as printed, without quantity prefix "
                                                  "(e.g. '2x Cheese Burger' -> 'Cheese Burger')."},
                    "line_total": {"type": _NULLABLE_NUM,
                                   "description": "Price of this line as printed (rightmost price of the row). "
                                                  "Number only."},
                },
                "required": ["food_name", "line_total"],
            },
        },
        "subtotal": {
            "type": _NULLABLE_NUM,
            "description": "Sum of item prices before fees and discounts. Number only.",
        },
        "tax": {
            "type": _NULLABLE_NUM,
            "description": "Total tax added to the receipt, usually exists after subtotal, just add null if absent."
                            "DISCOUNT AND TAX ARE DIFFERENT",
        },
        "fee": {
            "type": _NULLABLE_NUM,
            "description": "Sum of all added charges other than tax: delivery fee / ongkir, service fee, "
                           "order fee, packaging fee, app fee, tip. POSITIVE number, null if absent.",
        },
        "discount": {
            "type": _NULLABLE_NUM,
            "description": "Total discount / promo / voucher as a POSITIVE number. null if absent."
                            "DISCOUNT AND TAX ARE DIFFERENT",
        },
        "total_price": {
            "type": _NULLABLE_NUM,
            "description": "FINAL amount paid by the customer: the last total on the receipt, "
                           "after fees and discounts. Number only.",
        },
    },
    "required": ["restaurant", "purchased_at", "purchased_time", "items",
                 "subtotal", "tax", "fee", "discount", "total_price"],
}

def _type_label(node: dict) -> str:
    t = node.get("type")
    types = [x for x in (t if isinstance(t, list) else [t]) if x and x != "null"]
    return types[0] if types else "string"


def schema_field_summary(schema: dict) -> str:
    lines: list[str] = []
    for name, node in schema.get("properties", {}).items():
        label = _type_label(node)
        desc = " ".join(node.get("description", "").split())
        if label == "array" and "properties" in node.get("items", {}):
            lines.append(f"- {name} (array): {desc}".rstrip())
            for iname, inode in node["items"]["properties"].items():
                ilabel = _type_label(inode)
                isuffix = f" ({ilabel})" if ilabel != "string" else ""
                idesc = " ".join(inode.get("description", "").split())
                lines.append(f"    - {iname}{isuffix}: {idesc}".rstrip())
        else:
            suffix = f" ({label})" if label != "string" else ""
            lines.append(f"- {name}{suffix}: {desc}".rstrip())
    return "\n".join(lines)


SYSTEM_PROMPT = f"{SYSTEM_RULES}\n\nFields to extract (with their meaning):\n{schema_field_summary(SCHEMA)}"

# --------------------------------------------------------------- result types
class LLMError(RuntimeError):
    """The model did not return usable JSON. `raw` = raw output (for debugging)."""

    def __init__(self, msg: str, raw: str = ""):
        super().__init__(msg)
        self.raw = raw


@dataclass
class LLMResult:
    data: dict
    raw_text: str
    meta: dict
    warnings: list[str] = field(default_factory=list)


# --------------------------------------------------------------- functions
def render_pages(path: Path, dpi: int = DPI, max_dim: int = MAX_DIM,
                 max_pages: int = MAX_PAGES) -> list[bytes]:
    """PDF or image (png/jpg/tiff/bmp) -> list of PNG bytes, longest side capped at max_dim."""
    try:
        doc = fitz.open(str(path))
    except Exception as e:  # noqa: BLE001
        raise LLMError(f"failed to open file: {e}") from e

    pages: list[bytes] = []
    for i in range(min(len(doc), max_pages)):
        page = doc[i]
        long_side = max(page.rect.width, page.rect.height) or 1.0
        scale = min(dpi / 72.0, max_dim / long_side)
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale))  # pyright: ignore[reportAttributeAccessIssue]
        pages.append(pix.tobytes("png"))
    if not pages:
        raise LLMError("no page could be rendered")
    return pages


def extract_json(text: str) -> str:
    text = text.strip()
    fence = re.search(r"```(?:json)?[ \t]*\r?\n(.+?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if 0 <= start < end else text

def embed_texts(texts: list[str], kind: str = "document") -> list[list[float]]:
    """Text -> EMBED_DIM vectors. kind="document" when storing (food names),
    kind="query" when searching (questions). nomic-embed-text requires these prefixes."""
    if not texts:
        return []
    prefix = "search_document: " if kind == "document" else "search_query: "
    resp = ollama.embed(model=EMBED_MODEL, input=[prefix + t for t in texts])
    vecs = [list(v) for v in resp.embeddings]
    if any(len(v) != EMBED_DIM for v in vecs):
        raise LLMError(f"embedding dimension is {len(vecs[0])}, expected {EMBED_DIM} (check EMBED_MODEL)")
    return vecs

def run_llm(path: Path, *, model: str = MODEL, dpi: int = DPI, max_dim: int = MAX_DIM,
            max_pages: int = MAX_PAGES, n_ctx: int = N_CTX, num_predict: int = NUM_PREDICT,
            num_thread: int = NUM_THREAD, num_gpu: int = -1, think: bool = False,
            use_schema: bool = True,
            on_token: Callable[[str], None] | None = None) -> LLMResult:
    """Render document -> call model -> raw JSON dict (NOT post-processed yet).
    on_token: callback for every text chunk (CLI: print; UI: progress bar/streaming)."""
    images = render_pages(Path(path), dpi, max_dim, max_pages)

    options: dict[str, Any] = {"temperature": 0, "num_ctx": n_ctx, "num_predict": num_predict}
    if num_thread > 0:
        options["num_thread"] = num_thread
    if num_gpu >= 0:
        options["num_gpu"] = num_gpu

    user = USER_INSTRUCTION
    if not use_schema:
        user += "\n\nOutput ONLY a single valid JSON object, no markdown, no commentary."

    parts: list[str] = []
    think_parts: list[str] = []
    final = None
    t0 = time.time()
    for chunk in ollama.chat(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user, "images": images},
        ],
        format=SCHEMA if use_schema else None,
        options=options,
        think=think,
        stream=True,
    ):
        piece = chunk.message.content
        if piece:
            parts.append(piece)
            if on_token:
                on_token(piece)
        tpiece = getattr(chunk.message, "thinking", None)
        if tpiece:
            think_parts.append(tpiece)
        if chunk.done:
            final = chunk
    dur = time.time() - t0

    prompt_tok = getattr(final, "prompt_eval_count", None)
    output_tok = getattr(final, "eval_count", None)
    done_reason = getattr(final, "done_reason", None)

    warnings: list[str] = []
    if done_reason == "length":
        warnings.append(f"output hit the num_predict limit ({num_predict}); JSON may be truncated")
    if prompt_tok and prompt_tok >= n_ctx - 64:
        warnings.append(f"prompt ({prompt_tok} tokens) is close to n_ctx ({n_ctx}); context may be truncated")

    raw = "".join(parts).strip()
    from_thinking = False
    if not raw:                       # qwen3-vl template bug: the answer lands in the thinking channel
        raw = "".join(think_parts).strip()
        from_thinking = bool(raw)

    meta = {
        "model": model,
        "run_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "duration_s": round(dur, 1),
        "tok_per_s": round(output_tok / dur, 1) if output_tok and dur else None,
        "prompt_tok": prompt_tok,
        "output_tok": output_tok,
        "done_reason": done_reason,
        "num_gpu": num_gpu,
        "pages": len(images),
        "img_sha": [hashlib.sha1(b).hexdigest()[:10] for b in images],
        "json_from_thinking": from_thinking,
    }

    if not raw:
        raise LLMError("model returned empty text (try think=True, use_schema=False, or another model)")
    try:
        data = json.loads(extract_json(raw))
    except json.JSONDecodeError as e:
        raise LLMError("model did not return valid JSON", raw=raw) from e
    if not isinstance(data, dict):
        raise LLMError("JSON output is not an object", raw=raw)
    return LLMResult(data=data, raw_text=raw, meta=meta, warnings=warnings)
