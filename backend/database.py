"""database.py -- store and read receipts in PostgreSQL. Knows nothing about the model.

Connection from .env: DB_HOST, DB_PORT, DB_USERNAME, DB_PASSWORD, DB_NAME
(or a single DATABASE_URL=postgresql://user:pass@host:port/db, which takes precedence when set)."""
from __future__ import annotations

import datetime
import json
import os
from typing import Any
from uuid import UUID

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

load_dotenv()

# Create the connection to the database
def get_conn() -> psycopg.Connection:
    url = os.getenv("DATABASE_URL")
    if url:
        return psycopg.connect(url)
    return psycopg.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        user=os.getenv("DB_USERNAME"),
        password=os.getenv("DB_PASSWORD"),
        dbname=os.getenv("DB_NAME"),
    )

# --------------------------------------------------------------- conversion
def _to_date(s: Any) -> datetime.date | None:
    if not isinstance(s, str):
        return None
    try:
        return datetime.datetime.strptime(s, "%d/%m/%Y").date()
    except ValueError:
        return None


def _to_time(s: Any) -> datetime.time | None:
    if not isinstance(s, str):
        return None
    try:
        return datetime.datetime.strptime(s, "%H:%M").time()
    except ValueError:
        return None


def _to_num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _to_vector(v: list[float] | None) -> str | None:
    """List of floats -> pgvector literal '[0.1,0.2,...]'. Used with %s::vector,
    so the `pgvector` Python package is not needed."""
    return None if v is None else "[" + ",".join(repr(float(x)) for x in v) + "]"


# --------------------------------------------------------------- write
def _receipt_values(data: dict) -> tuple:
    """(restaurant, purchased_at, purchased_time, subtotal, tax, fee, discount, total_price)."""
    return ((data.get("restaurant") or "")[:255] or None,
            _to_date(data.get("purchased_at")),
            _to_time(data.get("purchased_time")),
            _to_num(data.get("subtotal")),
            _to_num(data.get("tax")),
            _to_num(data.get("fee")),
            _to_num(data.get("discount")),
            _to_num(data.get("total_price")))


def _item_dicts(data: dict, embeddings: list[list[float]] | None) -> list[dict]:
    items = [it for it in (data.get("items") or []) if isinstance(it, dict)]
    if embeddings is not None and len(embeddings) != len(items):
        raise ValueError(f"number of embeddings ({len(embeddings)}) != number of items ({len(items)})")
    return items


def _insert_items(cur: psycopg.Cursor, receipt_id: Any, items: list[dict],
                  embeddings: list[list[float]] | None) -> None:
    if not items:
        return
    cur.executemany(
        "INSERT INTO receipt_items (receipt_id, food_name, line_total, embedding) "
        "VALUES (%s,%s,%s,%s::vector)",
        [(receipt_id,
          (it.get("food_name") or "")[:255],
          _to_num(it.get("line_total")),
          _to_vector(embeddings[i] if embeddings is not None else None))
         for i, it in enumerate(items)],
    )


def save_receipt(data: dict, *, image_path: str, raw_output: dict | None = None,
                 embeddings: list[list[float]] | None = None) -> UUID:
    """Save 1 receipt + its items in ONE transaction. Returns receipts.id.
    data: output of extract.postprocess(). embeddings: 1 vector per item (same order), or None."""
    items = _item_dicts(data, embeddings)
    with get_conn() as conn:                 # commits at the end, rolls back on error
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO receipts (restaurant, purchased_at, purchased_time, subtotal, tax,
                                         fee, discount, total_price, image_path, raw_output)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (*_receipt_values(data), image_path,
                 Jsonb(raw_output) if raw_output is not None else None),
            )
            receipt_id = cur.fetchone()[0]
            _insert_items(cur, receipt_id, items, embeddings)
    return receipt_id


def update_receipt(receipt_id: str, data: dict,
                   embeddings: list[list[float]] | None = None) -> bool:
    """Human correction: overwrite the fields and REPLACE all items, in ONE transaction.
    data has the same format as for save_receipt(). image_path and raw_output (the
    original model output) are kept. Returns False if the receipt does not exist."""
    items = _item_dicts(data, embeddings)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE receipts SET restaurant = %s, purchased_at = %s, purchased_time = %s,
                                       subtotal = %s, tax = %s, fee = %s, discount = %s,
                                       total_price = %s
                   WHERE id = %s""",
                (*_receipt_values(data), receipt_id),
            )
            if cur.rowcount == 0:
                return False
            cur.execute("DELETE FROM receipt_items WHERE receipt_id = %s", (receipt_id,))
            _insert_items(cur, receipt_id, items, embeddings)
    return True


# --------------------------------------------------------------- read (agent tools, plain SQL)
def _filters(start_date: str | None, end_date: str | None,
             restaurant: str | None) -> tuple[str, list[Any]]:
    """WHERE clause for alias r (receipts). Dates 'YYYY-MM-DD', inclusive."""
    clauses: list[str] = []
    params: list[Any] = []
    if start_date:
        clauses.append("r.purchased_at >= %s::date")
        params.append(start_date)
    if end_date:
        clauses.append("r.purchased_at <= %s::date")
        params.append(end_date)
    if restaurant:
        clauses.append("r.restaurant ILIKE %s")
        params.append(f"%{restaurant}%")
    return ("WHERE " + " AND ".join(clauses)) if clauses else "", params


def _fetchall(sql: str, params: list[Any]) -> list[dict]:
    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def spending_summary(start_date: str | None = None, end_date: str | None = None,
                     restaurant: str | None = None) -> dict:
    """Number of receipts, total paid, average, total tax/fee/discount."""
    where, params = _filters(start_date, end_date, restaurant)
    return _fetchall(
        f"""SELECT count(*) AS receipts, sum(total_price) AS total_spent,
                   round(avg(total_price), 2) AS avg_per_receipt,
                   sum(tax) AS total_tax, sum(fee) AS total_fee, sum(discount) AS total_discount,
                   min(purchased_at) AS first_date, max(purchased_at) AS last_date
            FROM receipts r {where}""", params)[0]


def spending_by_restaurant(start_date: str | None = None, end_date: str | None = None,
                           limit: int = 10) -> list[dict]:
    """Total spending & number of receipts per restaurant, largest first."""
    where, params = _filters(start_date, end_date, None)
    return _fetchall(
        f"""SELECT r.restaurant, count(*) AS receipts, sum(r.total_price) AS total_spent
            FROM receipts r {where}
            GROUP BY r.restaurant ORDER BY total_spent DESC NULLS LAST LIMIT %s""",
        params + [max(1, min(int(limit), 50))])


def list_receipts(start_date: str | None = None, end_date: str | None = None,
                  restaurant: str | None = None, limit: int = 20) -> list[dict]:
    """List of receipts, newest first (without raw_output)."""
    where, params = _filters(start_date, end_date, restaurant)
    return _fetchall(
        f"""SELECT r.id, r.restaurant, r.purchased_at, r.purchased_time, r.subtotal, r.tax,
                   r.fee, r.discount, r.total_price
            FROM receipts r {where}
            ORDER BY r.purchased_at DESC NULLS LAST, r.purchased_time DESC NULLS LAST
            LIMIT %s""",
        params + [max(1, min(int(limit), 100))])


def get_receipt(receipt_id: str) -> dict | None:
    """One receipt including its items."""
    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""SELECT id, restaurant, purchased_at, purchased_time, subtotal, tax, fee,
                              discount, total_price
                       FROM receipts WHERE id = %s""", (receipt_id,))
        receipt = cur.fetchone()
        if receipt is None:
            return None
        cur.execute("SELECT food_name, line_total FROM receipt_items WHERE receipt_id = %s",
                    (receipt_id,))
        receipt["items"] = cur.fetchall()
        return receipt


def list_items(start_date: str | None = None, end_date: str | None = None,
               restaurant: str | None = None, limit: int = 50) -> list[dict]:
    """Purchased food items with their restaurant and date, newest first."""
    where, params = _filters(start_date, end_date, restaurant)
    return _fetchall(
        f"""SELECT i.food_name, i.line_total, r.restaurant, r.purchased_at, r.purchased_time
            FROM receipt_items i JOIN receipts r ON r.id = i.receipt_id
            {where}
            ORDER BY r.purchased_at DESC NULLS LAST, r.purchased_time DESC NULLS LAST
            LIMIT %s""",
        params + [max(1, min(int(limit), 200))])


# --------------------------------------------------------------- read (review UI)
# Separate from the agent tools above so the UI can show more columns without
# changing what the LLM sees.
def list_receipts_ui(limit: int = 500) -> list[dict]:
    """All receipts for the review table, most recently uploaded first."""
    return _fetchall(
        """SELECT r.id, r.restaurant, r.purchased_at, r.purchased_time, r.subtotal, r.tax,
                  r.fee, r.discount, r.total_price, r.created_at,
                  (SELECT count(*) FROM receipt_items i WHERE i.receipt_id = r.id) AS item_count
           FROM receipts r
           ORDER BY r.created_at DESC
           LIMIT %s""",
        [max(1, min(int(limit), 1000))])


def get_receipt_ui(receipt_id: str) -> dict | None:
    """One receipt with its items and image path."""
    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""SELECT id, restaurant, purchased_at, purchased_time, subtotal, tax, fee,
                              discount, total_price, created_at, image_path
                       FROM receipts WHERE id = %s""", (receipt_id,))
        receipt = cur.fetchone()
        if receipt is None:
            return None
        cur.execute("SELECT food_name, line_total FROM receipt_items WHERE receipt_id = %s",
                    (receipt_id,))
        receipt["items"] = cur.fetchall()
        return receipt


# --------------------------------------------------------------- vector candidates
def fetch_item_vectors(start_date: str | None = None, end_date: str | None = None) -> list[dict]:
    """Items that have an embedding, with their vector as list[float].
    pgvector only STORES the vectors; the similarity itself is computed in similarity.py.
    psycopg returns the vector column as text '[0.1,0.2,...]', hence json.loads."""
    where, params = _filters(start_date, end_date, None)
    where = f"{where} AND i.embedding IS NOT NULL" if where else "WHERE i.embedding IS NOT NULL"
    rows = _fetchall(
        f"""SELECT i.food_name, i.line_total, r.restaurant, r.purchased_at, r.purchased_time,
                   i.embedding::text AS embedding
            FROM receipt_items i JOIN receipts r ON r.id = i.receipt_id
            {where}""", params)
    for row in rows:
        row["embedding"] = json.loads(row["embedding"])
    return rows
