"""database.py -- store and read receipts in PostgreSQL. Knows nothing about the model.

Connection from .env: DB_HOST, DB_PORT, DB_USERNAME, DB_PASSWORD, DB_NAME
(or a single DATABASE_URL=postgresql://user:pass@host:port/db, which takes precedence when set)."""
from __future__ import annotations

import datetime
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
def save_receipt(data: dict, *, image_path: str, raw_output: dict | None = None,
                 embeddings: list[list[float]] | None = None) -> UUID:
    """Save 1 receipt + its items in ONE transaction. Returns receipts.id.
    data: output of extract.postprocess(). embeddings: 1 vector per item (same order), or None."""
    items = [it for it in (data.get("items") or []) if isinstance(it, dict)]
    if embeddings is not None and len(embeddings) != len(items):
        raise ValueError(f"number of embeddings ({len(embeddings)}) != number of items ({len(items)})")

    with get_conn() as conn:                 # commits at the end, rolls back on error
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO receipts (restaurant, purchased_at, purchased_time, subtotal, tax,
                                         fee, discount, total_price, image_path, raw_output)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                ((data.get("restaurant") or "")[:255] or None,
                 _to_date(data.get("purchased_at")),
                 _to_time(data.get("purchased_time")),
                 _to_num(data.get("subtotal")),
                 _to_num(data.get("tax")),
                 _to_num(data.get("fee")),
                 _to_num(data.get("discount")),
                 _to_num(data.get("total_price")),
                 image_path,
                 Jsonb(raw_output) if raw_output is not None else None),
            )
            receipt_id = cur.fetchone()[0]

            if items:
                cur.executemany(
                    "INSERT INTO receipt_items (receipt_id, food_name, line_total, embedding) "
                    "VALUES (%s,%s,%s,%s::vector)",
                    [(receipt_id,
                      (it.get("food_name") or "")[:255],
                      _to_num(it.get("line_total")),
                      _to_vector(embeddings[i] if embeddings is not None else None))
                     for i, it in enumerate(items)],
                )
    return receipt_id


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
