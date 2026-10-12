from __future__ import annotations

import datetime
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

from flask import Flask, abort, jsonify, make_response, request, send_file

import tools
import database
import extract
import llm

UPLOAD_DIR = Path(__file__).resolve().parent / "uploads"
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".pdf"}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024     # 10 MB
app.json.ensure_ascii = False


def _embed_items(items: list[dict], warnings: list[str]) -> list[list[float]] | None:
    """Embed food names. On failure (e.g. model not pulled) -> None + warning;
    the receipt is still saved, with NULL embeddings."""
    if not items:
        return None
    try:
        return llm.embed_texts([it["food_name"] for it in items], kind="document")
    except Exception as e:  # noqa: BLE001
        warnings.append(f"embedding failed ({type(e).__name__}: {e}); items saved without embeddings")
        return None


@app.route("/upload", methods=["POST"])
def upload():
    f = request.files.get("file")
    if f is None or not f.filename:
        return jsonify(error="field 'file' (multipart/form-data) is required"), 400
    ext = Path(f.filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        return jsonify(error=f"file type '{ext}' is not supported; use {', '.join(sorted(ALLOWED_EXT))}"), 400

    UPLOAD_DIR.mkdir(exist_ok=True)
    path = UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"     # random name: safe from path traversal & collisions
    f.save(path)
    try:
        result = llm.run_llm(path)
        data, warnings = extract.postprocess(result.data)
        warnings = result.warnings + warnings
        embeddings = _embed_items(data["items"], warnings)
        raw_output = {"raw_text": result.raw_text, "parsed": result.data,
                      "meta": result.meta, "warnings": warnings}
        receipt_id = database.save_receipt(data, image_path=str(path), raw_output=raw_output,
                                           embeddings=embeddings)
    except llm.LLMError as e:                          # model gave no usable JSON -> file is discarded
        path.unlink(missing_ok=True)
        return jsonify(error=str(e), raw=e.raw[:2000] or None), 422
    except Exception as e:  # noqa: BLE001
        path.unlink(missing_ok=True)
        return jsonify(error=f"{type(e).__name__}: {e}"), 500
    return jsonify(filename=f.filename, receipt_id=str(receipt_id), data=data,
                   warnings=warnings, meta=result.meta), 201


# --------------------------------------------------------------- receipts (review UI)
MONEY_FIELDS = ("subtotal", "tax", "fee", "discount", "total_price")


def _jsonable(value: Any) -> Any:
    """DB row -> JSON in the same formats /upload returns (DD/MM/YYYY, HH:MM, numbers)."""
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, datetime.datetime):        # created_at; check before date (subclass)
        return value.isoformat()
    if isinstance(value, datetime.date):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, datetime.time):
        return value.strftime("%H:%M")
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def _not_found(what: str = "receipt not found"):
    abort(make_response(jsonify(error=what), 404))


def _receipt_or_404(receipt_id: str) -> dict:
    try:
        uuid.UUID(receipt_id)
    except ValueError:
        _not_found()
    receipt = database.get_receipt_ui(receipt_id)
    if receipt is None:
        _not_found()
    return receipt


def _parse_correction(body: Any) -> tuple[dict | None, str | None]:
    """Validate a PATCH body. Returns (data for database.update_receipt, None) or (None, error).
    Empty values are allowed (= unknown); malformed ones are rejected instead of silently
    becoming NULL."""
    if not isinstance(body, dict):
        return None, "a JSON object body is required"

    restaurant = body.get("restaurant")
    if restaurant is not None and not isinstance(restaurant, str):
        return None, "'restaurant' must be a string or null"

    date, time = body.get("purchased_at") or None, body.get("purchased_time") or None
    if date is not None and database._to_date(date) is None:
        return None, "'purchased_at' must be DD/MM/YYYY or null"
    if time is not None and database._to_time(time) is None:
        return None, "'purchased_time' must be HH:MM or null"

    data: dict = {"restaurant": (restaurant or "").strip() or None,
                  "purchased_at": date, "purchased_time": time}
    for key in MONEY_FIELDS:
        v = body.get(key)
        if v is not None and database._to_num(v) is None:
            return None, f"'{key}' must be a number or null"
        data[key] = v

    data["items"], error = _parse_items(body.get("items") or [])
    return (None, error) if error else (data, None)


def _parse_items(items: Any) -> tuple[list[dict], str | None]:
    if not isinstance(items, list):
        return [], "'items' must be a list"
    parsed = []
    for i, it in enumerate(items, 1):
        name = it.get("food_name") if isinstance(it, dict) else None
        if not isinstance(name, str) or not name.strip():
            return [], f"item {i}: 'food_name' is required"
        line_total = it.get("line_total")
        if line_total is not None and database._to_num(line_total) is None:
            return [], f"item {i}: 'line_total' must be a number or null"
        parsed.append({"food_name": name.strip(), "line_total": line_total})
    return parsed, None


@app.route("/receipts", methods=["GET"])
def receipts_list():
    return jsonify(_jsonable(database.list_receipts_ui()))


@app.route("/receipts/<receipt_id>", methods=["GET"])
def receipts_get(receipt_id: str):
    return jsonify(_jsonable(_receipt_or_404(receipt_id)))


@app.route("/receipts/<receipt_id>/image", methods=["GET"])
def receipts_image(receipt_id: str):
    path = Path(_receipt_or_404(receipt_id)["image_path"])   # written by /upload, not user input
    if not path.is_file():
        _not_found("image file not found")
    return send_file(path)


@app.route("/receipts/<receipt_id>", methods=["PATCH"])
def receipts_update(receipt_id: str):
    _receipt_or_404(receipt_id)
    data, error = _parse_correction(request.get_json(silent=True))
    if error:
        return jsonify(error=error), 400

    warnings: list[str] = []
    embeddings = _embed_items(data["items"], warnings)   # names may have changed -> re-embed
    try:
        database.update_receipt(receipt_id, data, embeddings=embeddings)
    except Exception as e:  # noqa: BLE001
        return jsonify(error=f"{type(e).__name__}: {e}"), 500
    receipt = _jsonable(database.get_receipt_ui(receipt_id))
    if warnings:                                           # e.g. embedding failed
        receipt["warnings"] = warnings
    return jsonify(receipt)


@app.route("/ask", methods=["POST"])
def ask():
    body = request.get_json(silent=True) or {}
    question = (request.form.get("question") or body.get("question") or "").strip()
    if not question:
        return jsonify(error="field 'question' is required (form or JSON)"), 400

    tool_calls: list[dict] = []
    try:
        answer = tools.ask(question, on_tool=lambda name, args, _res: tool_calls.append(
            {"tool": name, "args": args}))
    except Exception as e:  # noqa: BLE001
        return jsonify(error=f"{type(e).__name__}: {e}", tool_calls=tool_calls), 500
    return jsonify(question=question, answer=answer, tool_calls=tool_calls)


if __name__ == "__main__":
    # No reloader: it restarts on unrelated file changes
    app.run(debug=True, use_reloader=False)
