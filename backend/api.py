from __future__ import annotations

import uuid
from pathlib import Path

from flask import Flask, jsonify, request

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
    app.run(debug=True)
