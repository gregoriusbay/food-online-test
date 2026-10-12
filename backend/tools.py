"""tools.py -- Q&A agent: the LLM picks a tool -> Python runs it -> the result goes back to the LLM.

The LLM never touches the database. It only chooses a tool name + arguments; the functions in
TOOL_FUNCS run the SQL (database.py) or the vector search (search_items).
"""
from __future__ import annotations

import datetime
import json
import time
from typing import Any, Callable

import ollama

import database
import llm
import similarity

AGENT_MODEL = llm.MODEL          # qwen3-vl:8b-instruct supports tool calling
AGENT_N_CTX = 8192
MAX_STEPS = 6                    # max tool-call rounds per question

SYSTEM = """You are an assistant that answers questions about the user's food purchase
history. All data lives in a receipt database and can ONLY be accessed through tools.
Rules:
- Dates use the format YYYY-MM-DD. For relative periods, COPY these ranges (do not compute them yourself):
{date_ranges}
- A date without a year (e.g. "20 June") means the most recent such date up to today.
- Picking a tool: "what did I buy/eat" -> list_items; a specific food or kind of food
  ("hamburger", "coffee") -> search_items; totals/expenses -> spending_summary.
- Never invent numbers. Every number in the answer must come from a tool result.
- search_items searches by meaning and always returns something; ignore results with a
  low score or that are clearly unrelated to the question.
- If a tool returns an error, fix the arguments or use another tool.
- If there is no data, say so plainly.
- Currency is Indonesian Rupiah, written like "Rp 65.000". Answer in the user's language, briefly."""


# --------------------------------------------------------------- vector search tool
def search_items(text: str, start_date: str | None = None, end_date: str | None = None,
                 limit: int = 5) -> list[dict]:
    """Semantic item search: embed the query, load candidate vectors from pgvector (storage
    only), rank them with our own cosine similarity (similarity.py)."""
    query_vec = llm.embed_texts([text], kind="query")[0]
    rows = database.fetch_item_vectors(start_date, end_date)
    if not rows:
        return []
    idx, scores = similarity.top_k(query_vec, [r["embedding"] for r in rows], k=int(limit))
    return [{**{k: v for k, v in rows[i].items() if k != "embedding"}, "score": round(float(s), 3)}
            for i, s in zip(idx, scores)]


# --------------------------------------------------------------- tool definitions
_DATE = {"type": "string", "description": "Date YYYY-MM-DD (inclusive). Leave empty for no limit."}

TOOLS: list[dict] = [
    {"type": "function", "function": {
        "name": "spending_summary",
        "description": "Spending summary: number of receipts, total paid, average per receipt, "
                       "total tax/fee/discount, first & last date. Can be filtered by date & restaurant.",
        "parameters": {"type": "object", "properties": {
            "start_date": _DATE, "end_date": _DATE,
            "restaurant": {"type": "string", "description": "Part of the restaurant name (case-insensitive)."},
        }},
    }},
    {"type": "function", "function": {
        "name": "spending_by_restaurant",
        "description": "Total spending and number of receipts per restaurant, largest first.",
        "parameters": {"type": "object", "properties": {
            "start_date": _DATE, "end_date": _DATE,
            "limit": {"type": "integer", "description": "Number of restaurants (default 10)."},
        }},
    }},
    {"type": "function", "function": {
        "name": "list_items",
        "description": "List the food/drink items bought in a period, with restaurant, date and price. "
                       "Use this for questions like 'what did I eat/buy yesterday'.",
        "parameters": {"type": "object", "properties": {
            "start_date": _DATE, "end_date": _DATE,
            "restaurant": {"type": "string", "description": "Part of the restaurant name."},
            "limit": {"type": "integer", "description": "Max number of items (default 50)."},
        }},
    }},
    {"type": "function", "function": {
        "name": "search_items",
        "description": "Search purchased food/drinks by meaning (e.g. 'coffee', 'sweet drink', "
                       "'hamburger'). Returns name, price, restaurant, date and a similarity score "
                       "(1 = most similar).",
        "parameters": {"type": "object", "properties": {
            "text": {"type": "string", "description": "What to search for."},
            "start_date": _DATE, "end_date": _DATE,
            "limit": {"type": "integer", "description": "Number of results (default 10)."},
        }, "required": ["text"]},
    }},
    {"type": "function", "function": {
        "name": "list_receipts",
        "description": "List receipts (id, restaurant, date, time, subtotal, tax, fee, discount, total), newest first.",
        "parameters": {"type": "object", "properties": {
            "start_date": _DATE, "end_date": _DATE,
            "restaurant": {"type": "string", "description": "Part of the restaurant name."},
            "limit": {"type": "integer", "description": "Number of receipts (default 20)."},
        }},
    }},
    {"type": "function", "function": {
        "name": "get_receipt",
        "description": "Details of one receipt including all its items.",
        "parameters": {"type": "object", "properties": {
            "receipt_id": {"type": "string", "description": "Receipt UUID (from list_receipts)."},
        }, "required": ["receipt_id"]},
    }},
]

TOOL_FUNCS: dict[str, Callable[..., Any]] = {
    "spending_summary": database.spending_summary,
    "spending_by_restaurant": database.spending_by_restaurant,
    "list_items": database.list_items,
    "search_items": search_items,
    "list_receipts": database.list_receipts,
    "get_receipt": database.get_receipt,
}


# --------------------------------------------------------------- tool-calling loop
def _date_ranges(today: datetime.date) -> str:
    """Pre-computed relative date ranges -- an 8B model often gets them wrong on its own."""
    day = datetime.timedelta(days=1)
    month_start = today.replace(day=1)
    last_month_end = month_start - day
    week_start = today - datetime.timedelta(days=today.weekday())        # Monday
    ranges = {
        "today": (today, today),
        "yesterday": (today - day, today - day),
        "last 7 days": (today - 6 * day, today),
        "this week": (week_start, today),
        "last week": (week_start - 7 * day, week_start - day),
        "this month": (month_start, today),
        "last month": (last_month_end.replace(day=1), last_month_end),
        "this year": (today.replace(month=1, day=1), today),
    }
    return "\n".join(f"  {name}: start_date={a.isoformat()} end_date={b.isoformat()}"
                     for name, (a, b) in ranges.items())


def _compact(value: Any) -> Any:
    """Drop null fields: tool results are fed back into the prompt, and on CPU every
    token the model has to read costs time."""
    if isinstance(value, dict):
        return {k: _compact(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_compact(v) for v in value]
    return value


def _seconds(ns: int | None) -> float:
    return round((ns or 0) / 1e9, 2)


def _run_tool(name: str, args: dict) -> Any:
    fn = TOOL_FUNCS.get(name)
    if fn is None:
        return {"error": f"unknown tool: {name}"}
    try:
        return fn(**args)
    except Exception as e:  # noqa: BLE001 -- the error goes back to the model so it can correct itself
        return {"error": f"{type(e).__name__}: {e}"}


def ask(question: str, on_tool: Callable[[str, dict, Any], None] | None = None,
        on_round: Callable[[dict], None] | None = None) -> str:
    """Question -> answer. on_tool(name, args, result) is called for every tool run;
    on_round(timings) once per model call, to see where the time goes."""
    messages: list[Any] = [
        {"role": "system", "content": SYSTEM.format(date_ranges=_date_ranges(datetime.date.today()))},
        {"role": "user", "content": question},
    ]
    for step in range(1, MAX_STEPS + 1):
        resp = ollama.chat(model=AGENT_MODEL, messages=messages, tools=TOOLS, think=False,
                           options={"temperature": 0, "num_ctx": AGENT_N_CTX})
        msg = resp.message
        messages.append(msg)
        timings = {"round": step,
                   "load_s": _seconds(resp.load_duration),           # > 0 = model was (re)loaded
                   "prompt_tokens": resp.prompt_eval_count,          # tokens actually (re)read
                   "prompt_s": _seconds(resp.prompt_eval_duration),
                   "output_tokens": resp.eval_count,
                   "output_s": _seconds(resp.eval_duration),
                   "tools_s": 0.0}

        if msg.tool_calls:
            t0 = time.perf_counter()
            for call in msg.tool_calls:
                name = call.function.name
                args = dict(call.function.arguments or {})
                result = _run_tool(name, args)
                if on_tool:
                    on_tool(name, args, result)
                messages.append({"role": "tool", "tool_name": name,
                                 "content": json.dumps(_compact(result), default=str,
                                                       ensure_ascii=False, separators=(",", ":"))})
            timings["tools_s"] = round(time.perf_counter() - t0, 2)
        if on_round:
            on_round(timings)
        if not msg.tool_calls:                      # the model has answered
            return (msg.content or "").strip()
    raise RuntimeError(f"agent did not answer within {MAX_STEPS} tool-call rounds")
