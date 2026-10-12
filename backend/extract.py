"""extract.py -- POST-PROCESSING of the model output (pure functions, no Ollama/DB, easy to test).

Flow: llm.run_llm() -> raw dict -> postprocess() -> clean dict -> database.save_receipt()
"""
from __future__ import annotations

import copy
import datetime
import re
from decimal import Decimal
from typing import Any

NUM_FIELDS = ("subtotal", "tax", "fee", "discount", "total_price")
TOLERANCE = 1.0          # Rupiah difference still treated as a match (summary-row detection)


# --------------------------------------------------------------- dates
# Month names as printed on receipts (Indonesian + English) -> month number.
_MONTHS = {
    "jan": 1, "januari": 1, "january": 1,
    "feb": 2, "februari": 2, "pebruari": 2, "february": 2, "peb": 2,
    "mar": 3, "maret": 3, "march": 3,
    "apr": 4, "april": 4,
    "mei": 5, "may": 5,
    "jun": 6, "juni": 6, "june": 6,
    "jul": 7, "juli": 7, "july": 7,
    "agu": 8, "agt": 8, "agus": 8, "agust": 8, "agustus": 8, "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "okt": 10, "oct": 10, "oktober": 10, "october": 10,
    "nov": 11, "nop": 11, "november": 11, "nopember": 11,
    "des": 12, "dec": 12, "desember": 12, "december": 12,
}
_MONTH_RE = "|".join(sorted(_MONTHS, key=len, reverse=True))
_DATE_OK_RE = re.compile(r"\d{2}/\d{2}/\d{4}")


def _mk_date(d: int, m: int, y: int) -> str | None:
    if y < 100:
        y += 2000
    if m > 12 and d <= 12:          # probably US MM/DD format -> swap
        d, m = m, d
    try:
        return datetime.date(y, m, d).strftime("%d/%m/%Y")
    except ValueError:
        return None


def normalize_date(s: Any) -> Any:
    """'8 Maret 2025', '2025-03-08', '08-Mar-25', '8.3.2025' -> '08/03/2025'.
    If parsing fails, the original string is returned (so it is not silently lost)."""
    if not isinstance(s, str) or not s.strip():
        return s
    t = s.strip().lower()

    # YYYY-MM-DD / YYYY/MM/DD
    m = re.search(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b", t)
    if m:
        return _mk_date(int(m[3]), int(m[2]), int(m[1])) or s

    # DD-MM-YYYY / DD/MM/YY / DD.MM.YYYY / DD MM YYYY
    m = re.search(r"\b(\d{1,2})[-/. ](\d{1,2})[-/. ](\d{4}|\d{2})\b", t)
    if m:
        return _mk_date(int(m[1]), int(m[2]), int(m[3])) or s

    # DD MonthName YYYY  (8 Maret 2025, 08-Mar-25, 17 Agustus 2025)
    m = re.search(rf"\b(\d{{1,2}})[\s\-./]*({_MONTH_RE})\.?[a-z]*[\s\-./,]*(\d{{4}}|\d{{2}})\b", t)
    if m:
        return _mk_date(int(m[1]), _MONTHS[m[2]], int(m[3])) or s

    # MonthName DD, YYYY  (March 8, 2025)
    m = re.search(rf"\b({_MONTH_RE})\.?[a-z]*\s+(\d{{1,2}}),?\s+(\d{{4}})\b", t)
    if m:
        return _mk_date(int(m[2]), _MONTHS[m[1]], int(m[3])) or s
    return s


# --------------------------------------------------------------- time
# HH:MM / HH.MM / HH:MM:SS, optional AM/PM. The lookbehind/lookahead keep parts of a
# date from matching, e.g. "08.03" inside "08.03.2025".
_TIME_RE = re.compile(
    r"(?<![\d.:/-])(\d{1,2})[:.](\d{2})(?:[:.]\d{2})?(?!\d|[.:/-]\d)"
    r"(?:\s*([ap])\.?\s*m\.?)?",
    re.IGNORECASE,
)


def split_time(s: Any) -> tuple[str | None, Any]:
    """Find a time in a string. Returns ('HH:MM' 24h | None, string without the time part).
    '11 Okt 2026, 12.30' -> ('12:30', '11 Okt 2026,')   '7:05 PM' -> ('19:05', '')"""
    if not isinstance(s, str):
        return None, s
    for m in _TIME_RE.finditer(s):
        h, mi, ampm = int(m[1]), int(m[2]), (m[3] or "").lower()
        if ampm == "p" and h < 12:
            h += 12
        elif ampm == "a" and h == 12:
            h = 0
        if h < 24 and mi < 60:
            rest = (s[:m.start()] + s[m.end():]).strip()
            return f"{h:02d}:{mi:02d}", rest
    return None, s


# --------------------------------------------------------------- numbers
def _as_float(v: Any) -> float | None:
    """Number from the model -> float. Strings handle Indonesian & English formats:
    '64.000' -> 64000, '1.280.000' -> 1280000, '991,145.94' -> 991145.94,
    '64000.0' -> 64000.0, '15,5' -> 15.5, 'Rp -15.000' -> -15000."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float, Decimal)):
        return float(v)
    if not isinstance(v, str):
        return None
    s = re.sub(r"[^0-9.,\-]", "", v)
    if not re.search(r"\d", s):
        return None
    if "." in s and "," in s:                     # the last separator is the decimal one
        dec, thou = (".", ",") if s.rfind(".") > s.rfind(",") else (",", ".")
        s = s.replace(thou, "").replace(dec, ".")
    elif "." in s or "," in s:
        sep = "." if "." in s else ","
        if re.fullmatch(rf"-?\d{{1,3}}(?:\{sep}\d{{3}})+", s):   # thousands pattern
            s = s.replace(sep, "")
        else:
            s = s.replace(sep, ".")
    try:
        return float(s)
    except ValueError:
        return None


# --------------------------------------------------------------- items
_QTY_PREFIX_RE = re.compile(r"^\s*\d+\s*[xX×](?=\s)\s*")      # "2x Cheese Burger", "2 x ..."
_QTY_SUFFIX_RE = re.compile(r"\s+[xX×]\s*\d+\s*$")           # "Cheese Burger x2"
_BULLET_RE = re.compile(r"^\s*[+•*]\s*")                     # "+ Extra Cheese" (add-on)


def strip_qty(name: str) -> str:
    name = _BULLET_RE.sub("", name)
    return _QTY_SUFFIX_RE.sub("", _QTY_PREFIX_RE.sub("", name)).strip()


def drop_summary_rows(items: list[dict], subtotal: float | None = None,
                      total_price: float | None = None) -> list[dict]:
    """Drop rows with an empty name, and a leftover 'total' row: one whose line_total equals
    subtotal/total_price AND the sum of all other rows. The second condition matters: a receipt
    with a 50.000 burger + a free 0 iced tea and a 50.000 total must NOT lose the burger."""
    kept = [it for it in items if it.get("food_name")]

    targets = [t for t in (subtotal, total_price) if t is not None]
    if len(kept) > 2 and targets:
        for it in list(kept):
            lt = it.get("line_total")
            if lt is None or not any(abs(lt - t) <= TOLERANCE for t in targets):
                continue
            others = sum(o.get("line_total") or 0 for o in kept if o is not it)
            if abs(others - lt) <= TOLERANCE:
                kept.remove(it)
                break
    return kept


# --------------------------------------------------------------- pipeline
def postprocess(raw: dict) -> dict:
    """Raw dict from llm.run_llm() -> clean dict ready for database.save_receipt.
    The input is not modified (it is copied) so the raw output can still be stored in raw_output."""
    data = copy.deepcopy(raw)

    # restaurant
    name = data.get("restaurant")
    data["restaurant"] = name if isinstance(name, str) else None

    # time: use purchased_time; if empty, the model may have put the time inside purchased_at
    time_in_date, date_without_time = split_time(data.get("purchased_at"))
    time_value, _ = split_time(data.get("purchased_time"))
    if time_value is None and time_in_date is not None:
        time_value = time_in_date
    data["purchased_time"] = time_value

    # date: DD/MM/YYYY, failure -> NULL
    date_value = normalize_date(date_without_time if time_in_date is not None else data.get("purchased_at"))
    data["purchased_at"] = (date_value if isinstance(date_value, str) and _DATE_OK_RE.fullmatch(date_value)
                            else None)

    # header numbers
    for k in NUM_FIELDS:
        data[k] = _as_float(data.get(k))
    for k in ("fee", "discount"):                 # always positive
        if data[k] is not None and data[k] < 0:
            data[k] = -data[k]

    # items
    items: list[dict] = []
    for it in data.get("items") or []:
        if not isinstance(it, dict):
            continue
        items.append({
            "food_name": strip_qty(str(it.get("food_name") or "")),
            "line_total": _as_float(it.get("line_total")),
        })
    data["items"] = drop_summary_rows(items, data["subtotal"], data["total_price"])
    return data
