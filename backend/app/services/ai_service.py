"""
ai_service.py
-------------
AI pipeline service for the Estatio property management platform.

Responsibilities:
  - Document classification and data extraction (Gemini Vision)
  - Natural-language query translation to MongoDB aggregations
  - Property performance insight generation
  - Predictive maintenance need forecasting
  - Invoice line-item description drafting

Integration:
  - Primary AI backend: Google Gemini (google.generativeai)
  - Retry logic: tenacity (exponential back-off, 3 attempts)
  - Graceful fallback when GEMINI_API_KEY is not set

MongoDB collections used:
  documents             - DocumentDB
  work_orders           - WorkOrderDB
  invoices              - InvoiceDB
  journal_entries       - JournalEntryDB
  properties            - PropertyDB
  preventive_maintenance- PreventiveMaintenanceDB
"""

from __future__ import annotations

import asyncio
import base64
import json
import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog
from motor.motor_asyncio import AsyncIOMotorDatabase

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Gemini client initialisation (lazy, with graceful degradation)
# ---------------------------------------------------------------------------

_gemini_model: Optional[Any] = None
_gemini_vision_model: Optional[Any] = None
_GEMINI_AVAILABLE = False

try:
    import google.generativeai as genai

    from app.core.config import settings

    if settings.GEMINI_API_KEY:
        genai.configure(api_key=settings.GEMINI_API_KEY)
        _gemini_model = genai.GenerativeModel("gemini-1.5-flash")
        _gemini_vision_model = genai.GenerativeModel("gemini-1.5-flash")
        _GEMINI_AVAILABLE = True
        log.info("Gemini AI initialised", model="gemini-1.5-flash")
    else:
        log.warning("GEMINI_API_KEY not set; AI features will use fallback responses")
except ImportError:
    log.warning("google-generativeai not installed; AI features disabled")
except Exception as _exc:
    log.warning("Failed to initialise Gemini", error=str(_exc))

# ---------------------------------------------------------------------------
# Retry decorator (tenacity)
# ---------------------------------------------------------------------------

try:
    from tenacity import (
        AsyncRetrying,
        retry_if_exception_type,
        stop_after_attempt,
        wait_exponential,
    )

    _TENACITY_AVAILABLE = True
except ImportError:
    _TENACITY_AVAILABLE = False
    log.warning("tenacity not installed; retry logic disabled")


async def _with_retry(coro_fn, *args, **kwargs) -> Any:
    """
    Execute an async coroutine function with exponential back-off retries.

    Falls back to a single attempt if tenacity is not installed.
    Retries on any Exception up to 3 times with 2-10 s back-off.
    """
    if not _TENACITY_AVAILABLE:
        return await coro_fn(*args, **kwargs)

    last_exc: Optional[Exception] = None
    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    ):
        with attempt:
            return await coro_fn(*args, **kwargs)
    # This line is unreachable but satisfies type checkers.
    raise last_exc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _round2(value: float) -> float:
    return round(value, 2)


def _safe_json(text: str) -> Optional[Dict[str, Any]]:
    """
    Attempt to extract and parse the first JSON object found in ``text``.
    Strips markdown code fences if present.
    """
    text = text.strip()
    # Strip markdown fences
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    # Extract first {...} block
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None


async def _gemini_generate(prompt: str, image_data: Optional[bytes] = None) -> str:
    """
    Send a text (or multimodal) prompt to Gemini and return the text response.

    Raises RuntimeError when Gemini is not available.
    """
    if not _GEMINI_AVAILABLE:
        raise RuntimeError("Gemini not available")

    if image_data is not None:
        # Multimodal: include raw image bytes

        image_part = {
            "mime_type": "application/octet-stream",
            "data": base64.b64encode(image_data).decode(),
        }
        response = await asyncio.to_thread(
            _gemini_vision_model.generate_content, [prompt, image_part]
        )
    else:
        response = await asyncio.to_thread(_gemini_model.generate_content, prompt)

    return response.text


# ---------------------------------------------------------------------------
# Document classification
# ---------------------------------------------------------------------------


async def classify_document(
    document_content: bytes,
    filename: str,
) -> Dict[str, Any]:
    """
    Use Gemini Vision to classify a document, extract key data fields, and
    generate a concise summary.

    Parameters:
        document_content - raw bytes of the uploaded file
        filename         - original filename (used for MIME-type hints)

    Returns:
        {
            "category": str,               # DocumentCategory value
            "confidence": float,           # 0.0-1.0
            "summary": str,
            "extracted_data": {
                ...                        # document-type specific fields
            },
            "tags": list[str],
            "fallback_used": bool,
        }
    """
    logger = log.bind(action="classify_document", filename=filename)
    logger.info("Classifying document")

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    is_pdf = ext == "pdf"
    is_image = ext in ("jpg", "jpeg", "png", "gif", "webp", "tiff")

    prompt = f"""You are an expert property management document classifier.

Analyse the following document (filename: {filename}) and return a JSON object with EXACTLY these fields:

{{
  "category": "<one of: lease, invoice, receipt, insurance, inspection, permit, hoa, maintenance, legal, tax, financial, vendor_contract, photo, other>",
  "confidence": <float between 0.0 and 1.0>,
  "summary": "<2-3 sentence description of what this document is>",
  "tags": ["<tag1>", "<tag2>", ...],
  "extracted_data": {{
    "date": "<ISO date if found>",
    "amount": <float or null>,
    "party_names": ["<name1>", ...],
    "property_address": "<address if found or null>",
    "document_number": "<invoice/permit/policy number if found or null>",
    "expiry_date": "<ISO date if found or null>",
    "key_terms": ["<term1>", ...]
  }}
}}

Return ONLY the JSON object, no surrounding text."""

    fallback_used = False
    result: Dict[str, Any] = {
        "category": "other",
        "confidence": 0.5,
        "summary": f"Document '{filename}' uploaded for review.",
        "extracted_data": {
            "date": None,
            "amount": None,
            "party_names": [],
            "property_address": None,
            "document_number": None,
            "expiry_date": None,
            "key_terms": [],
        },
        "tags": [],
        "fallback_used": False,
    }

    try:
        # Only pass raw bytes for image/PDF types; for text pass without bytes
        image_bytes = document_content if (is_pdf or is_image) else None
        raw_text = await _with_retry(_gemini_generate, prompt, image_bytes)
        parsed = _safe_json(raw_text)
        if parsed:
            result["category"] = parsed.get("category", "other")
            result["confidence"] = float(parsed.get("confidence", 0.5))
            result["summary"] = parsed.get("summary", result["summary"])
            result["tags"] = parsed.get("tags", [])
            result["extracted_data"] = parsed.get(
                "extracted_data", result["extracted_data"]
            )
        else:
            logger.warning("Gemini returned non-JSON response, using defaults")
            fallback_used = True
    except Exception as exc:
        logger.warning("Gemini classification failed, using fallback", error=str(exc))
        fallback_used = True

    result["fallback_used"] = fallback_used

    # Heuristic category override based on filename when Gemini is unavailable
    if fallback_used:
        fname_lower = filename.lower()
        if "lease" in fname_lower or "rental_agreement" in fname_lower:
            result["category"] = "lease"
        elif "invoice" in fname_lower:
            result["category"] = "invoice"
        elif "insurance" in fname_lower or "policy" in fname_lower:
            result["category"] = "insurance"
        elif "inspection" in fname_lower:
            result["category"] = "inspection"
        elif "receipt" in fname_lower:
            result["category"] = "receipt"

    logger.info(
        "Document classified",
        category=result["category"],
        confidence=result["confidence"],
        fallback=fallback_used,
    )
    return result


# ---------------------------------------------------------------------------
# Natural-language query
# ---------------------------------------------------------------------------

# Query-type patterns used to route NL queries to the right MongoDB pipeline
_QUERY_ROUTING_PATTERNS: List[tuple[str, str]] = [
    (r"spend|spent|cost|expense", "expenses"),
    (r"revenue|income|earn|rent collected", "revenue"),
    (r"invoice|bill|outstanding|owed", "invoices"),
    (r"maintenance|repair|work order", "maintenance"),
    (r"payment|paid|received", "payments"),
    (r"balance|owe|outstanding", "balance"),
    (r"property|properties", "properties"),
]


def _route_query(query: str) -> str:
    ql = query.lower()
    for pattern, category in _QUERY_ROUTING_PATTERNS:
        if re.search(pattern, ql):
            return category
    return "general"


async def _build_aggregation_pipeline(
    db: AsyncIOMotorDatabase,
    query: str,
    user_id: str,
) -> tuple[str, List[Dict[str, Any]], str]:
    """
    Use Gemini to translate a natural-language query into a MongoDB aggregation
    pipeline for the most relevant collection.

    Returns (collection_name, pipeline, explanation).
    """
    query_type = _route_query(query)

    # Contextual collection + schema hints per query type
    schema_hints = {
        "expenses": (
            "work_orders",
            "Fields: property_id, category, status, actual_cost (float), "
            "completed_date (ISO date string), created_at (datetime)",
        ),
        "revenue": (
            "invoices",
            "Fields: owner_id, property_id, status, total_amount (float), "
            "amount_paid (float), billing_period_start, billing_period_end, "
            "issue_date, created_at",
        ),
        "invoices": (
            "invoices",
            "Fields: owner_id, property_id, invoice_number, status, "
            "total_amount, balance_due, due_date, sent_at",
        ),
        "maintenance": (
            "work_orders",
            "Fields: property_id, category, priority, status, actual_cost, "
            "approved_amount, created_at, completed_date",
        ),
        "payments": (
            "payments",
            "Fields: invoice_id, owner_id, property_id, amount (float), "
            "payment_date (ISO date string), payment_method, created_at",
        ),
        "balance": (
            "invoices",
            "Fields: owner_id, property_id, balance_due (float), status, due_date",
        ),
    }

    collection, schema = schema_hints.get(query_type, ("invoices", ""))
    today = date.today().isoformat()

    prompt = f"""You are a MongoDB query expert for a property management system.

User query: "{query}"
Today's date: {today}
User ID (for scoping): {user_id}
Target collection: {collection}
Schema: {schema}

Translate the user's query into a MongoDB aggregation pipeline (JSON array).
Also write a one-sentence explanation of what the pipeline does.

Rules:
1. Use $match to filter by owner_id = "{user_id}" when the query is user-specific.
2. Use $group to aggregate; always include "_id" in $group.
3. Use date comparisons as ISO string comparisons where dates are stored as strings.
4. Keep the pipeline simple (2-4 stages max).
5. The final $group should produce a "result" or "total" field with the answer.

Return ONLY valid JSON in this format:
{{
  "collection": "{collection}",
  "pipeline": [ ... ],
  "explanation": "..."
}}"""

    try:
        raw = await _with_retry(_gemini_generate, prompt)
        parsed = _safe_json(raw)
        if parsed and "pipeline" in parsed:
            return (
                parsed.get("collection", collection),
                parsed["pipeline"],
                parsed.get("explanation", ""),
            )
    except Exception as exc:
        log.warning("Gemini pipeline generation failed", error=str(exc))

    # Fallback: static pipeline based on query_type
    fallback_pipelines: Dict[str, tuple[str, List[Dict[str, Any]], str]] = {
        "expenses": (
            "work_orders",
            [
                {"$match": {"status": "completed"}},
                {
                    "$group": {
                        "_id": "$category",
                        "total": {"$sum": "$actual_cost"},
                        "count": {"$sum": 1},
                    }
                },
                {"$sort": {"total": -1}},
            ],
            "Total actual cost of completed work orders grouped by category.",
        ),
        "revenue": (
            "invoices",
            [
                {"$match": {"owner_id": user_id}},
                {
                    "$group": {
                        "_id": "$status",
                        "total": {"$sum": "$total_amount"},
                        "count": {"$sum": 1},
                    }
                },
            ],
            "Total invoice amounts grouped by status for this owner.",
        ),
        "balance": (
            "invoices",
            [
                {
                    "$match": {
                        "owner_id": user_id,
                        "status": {"$in": ["sent", "viewed", "partial", "overdue"]},
                    }
                },
                {
                    "$group": {
                        "_id": None,
                        "total_outstanding": {"$sum": "$balance_due"},
                    }
                },
            ],
            "Total outstanding invoice balance for this owner.",
        ),
    }
    ft = fallback_pipelines.get(
        query_type,
        (
            "invoices",
            [{"$match": {"owner_id": user_id}}, {"$count": "total"}],
            "Total invoice count for this owner.",
        ),
    )
    return ft


async def answer_query(
    db: AsyncIOMotorDatabase,
    user_id: str,
    query: str,
) -> Dict[str, Any]:
    """
    Answer a natural-language query about the user's property data.

    Examples:
      - "How much did I spend on HVAC this year?"
      - "What is my total outstanding balance?"
      - "List my top 3 most expensive work orders"

    Steps:
      1. Route the query to the most relevant MongoDB collection.
      2. Use Gemini to generate a MongoDB aggregation pipeline.
      3. Execute the pipeline and return the raw results.
      4. Use Gemini to produce a human-readable answer.

    Returns:
        {
            "query": str,
            "answer": str,              # natural-language answer
            "data": list,               # raw aggregation results
            "collection": str,
            "fallback_used": bool,
        }
    """
    logger = log.bind(action="answer_query", user_id=user_id)
    logger.info("Processing NL query", query=query)

    collection, pipeline, explanation = await _build_aggregation_pipeline(
        db, query, user_id
    )
    fallback_used = not _GEMINI_AVAILABLE

    data: List[Dict[str, Any]] = []
    try:
        coll = getattr(db, collection)
        async for row in coll.aggregate(pipeline):
            # Convert ObjectId and datetime values to strings for serialisation
            serialisable: Dict[str, Any] = {}
            for k, v in row.items():
                if hasattr(v, "__str__") and not isinstance(
                    v, (int, float, bool, str, list, dict)
                ):
                    serialisable[k] = str(v)
                else:
                    serialisable[k] = v
            data.append(serialisable)
    except Exception as exc:
        logger.error("Aggregation pipeline failed", error=str(exc))
        data = []

    # Generate a human-readable answer from the data
    answer = "I was unable to find a clear answer. Please try rephrasing your question."

    if data:
        data_summary = json.dumps(data[:10], default=str)
        answer_prompt = f"""You are a helpful property management assistant.

User asked: "{query}"
Database returned: {data_summary}

Write a concise, friendly answer (1-3 sentences) that directly answers the user's question
using the data above. Include specific numbers where relevant. Do not use markdown."""

        try:
            answer = await _with_retry(_gemini_generate, answer_prompt)
            answer = answer.strip()
        except Exception as exc:
            logger.warning(
                "Gemini answer generation failed, using fallback", error=str(exc)
            )
            fallback_used = True
            # Build a basic answer from the raw data
            if data:
                if len(data) == 1 and "_id" in data[0]:
                    vals = {k: v for k, v in data[0].items() if k != "_id"}
                    answer = "Here are your results: " + ", ".join(
                        f"{k}: {v}" for k, v in vals.items()
                    )
                else:
                    answer = f"Found {len(data)} results for your query."
    elif not data:
        answer = "No data was found matching your query for the specified period."

    logger.info("Query answered", collection=collection, result_count=len(data))
    return {
        "query": query,
        "answer": answer,
        "data": data,
        "collection": collection,
        "explanation": explanation,
        "fallback_used": fallback_used,
    }


# ---------------------------------------------------------------------------
# Property performance insight
# ---------------------------------------------------------------------------


async def generate_insight(
    db: AsyncIOMotorDatabase,
    property_id: str,
) -> Dict[str, Any]:
    """
    Generate an AI insight report about a property's financial and maintenance
    performance.

    Collects the last 90 days of invoices, payments, and work orders, then
    asks Gemini to identify trends, anomalies, and recommendations.

    Returns:
        {
            "property_id": str,
            "generated_at": str,
            "insight": str,
            "metrics": { ... },
            "recommendations": list[str],
            "fallback_used": bool,
        }
    """
    logger = log.bind(action="generate_insight", property_id=property_id)
    logger.info("Generating property insight")

    ninety_days_ago = (datetime.utcnow() - timedelta(days=90)).isoformat()

    # Gather metrics in parallel
    async def _get_invoices() -> List[Dict[str, Any]]:
        docs = []
        async for inv in db.invoices.find(
            {"property_id": property_id, "created_at": {"$gte": ninety_days_ago}},
            {
                "total_amount": 1,
                "amount_paid": 1,
                "balance_due": 1,
                "status": 1,
                "due_date": 1,
            },
        ):
            docs.append(inv)
        return docs

    async def _get_work_orders() -> List[Dict[str, Any]]:
        docs = []
        async for wo in db.work_orders.find(
            {"property_id": property_id, "created_at": {"$gte": ninety_days_ago}},
            {
                "category": 1,
                "status": 1,
                "actual_cost": 1,
                "approved_amount": 1,
                "priority": 1,
                "created_at": 1,
                "completed_date": 1,
            },
        ):
            docs.append(wo)
        return docs

    async def _get_property() -> Optional[Dict[str, Any]]:
        return await db.properties.find_one(
            {"_id": property_id},
            {
                "name": 1,
                "property_type": 1,
                "monthly_rent": 1,
                "status": 1,
                "purchase_price": 1,
                "current_value": 1,
            },
        )

    invoices, work_orders, property_doc = await asyncio.gather(
        _get_invoices(), _get_work_orders(), _get_property()
    )

    # Compute summary metrics
    total_invoiced = _round2(sum(float(i.get("total_amount", 0)) for i in invoices))
    total_collected = _round2(sum(float(i.get("amount_paid", 0)) for i in invoices))
    total_outstanding = _round2(sum(float(i.get("balance_due", 0)) for i in invoices))
    overdue_count = sum(1 for i in invoices if i.get("status") == "overdue")

    total_wo = len(work_orders)
    open_wo = sum(
        1
        for wo in work_orders
        if wo.get("status") not in ("completed", "closed", "cancelled")
    )
    total_maintenance_cost = _round2(
        sum(float(wo.get("actual_cost") or 0) for wo in work_orders)
    )
    emergency_wo = sum(1 for wo in work_orders if wo.get("priority") == "emergency")

    metrics: Dict[str, Any] = {
        "period_days": 90,
        "total_invoiced": total_invoiced,
        "total_collected": total_collected,
        "total_outstanding": total_outstanding,
        "collection_rate_pct": _round2(
            (total_collected / total_invoiced * 100) if total_invoiced else 0.0
        ),
        "overdue_invoices": overdue_count,
        "total_work_orders": total_wo,
        "open_work_orders": open_wo,
        "total_maintenance_cost": total_maintenance_cost,
        "emergency_work_orders": emergency_wo,
    }

    prop_name = property_doc.get("name", property_id) if property_doc else property_id
    insight = "Insufficient data for AI insight generation."
    recommendations: List[str] = []
    fallback_used = False

    prompt = f"""You are an expert property manager reviewing a 90-day performance report.

Property: {prop_name}
Period: Last 90 days

Key Metrics:
- Total Invoiced: ${total_invoiced:,.2f}
- Total Collected: ${total_collected:,.2f}
- Collection Rate: {metrics["collection_rate_pct"]}%
- Outstanding Balance: ${total_outstanding:,.2f}
- Overdue Invoices: {overdue_count}
- Work Orders: {total_wo} total, {open_wo} open, {emergency_wo} emergency
- Maintenance Cost: ${total_maintenance_cost:,.2f}

Provide:
1. A concise 2-3 paragraph insight about this property's performance.
2. 2-4 specific, actionable recommendations.

Return a JSON object with this structure:
{{
  "insight": "<2-3 paragraphs>",
  "recommendations": ["<action 1>", "<action 2>", ...]
}}

Return ONLY the JSON object."""

    try:
        raw = await _with_retry(_gemini_generate, prompt)
        parsed = _safe_json(raw)
        if parsed:
            insight = parsed.get("insight", insight)
            recommendations = parsed.get("recommendations", [])
        else:
            fallback_used = True
    except Exception as exc:
        logger.warning("Gemini insight generation failed", error=str(exc))
        fallback_used = True

    if fallback_used:
        # Rule-based fallback insights
        parts: List[str] = []
        if metrics["collection_rate_pct"] < 80:
            parts.append(
                f"Collection rate is {metrics['collection_rate_pct']}%, which is below target. "
                "Consider following up on outstanding balances immediately."
            )
            recommendations.append("Send payment reminders for all overdue invoices.")
        if emergency_wo > 0:
            parts.append(
                f"There have been {emergency_wo} emergency work order(s) in the past 90 days. "
                "Consider reviewing preventive maintenance schedules to reduce reactive repairs."
            )
            recommendations.append(
                "Review and update preventive maintenance schedules."
            )
        if open_wo > 3:
            parts.append(
                f"{open_wo} work orders are currently open. "
                "Ensure all are assigned to vendors and progressing."
            )
            recommendations.append(
                "Follow up on all open work orders with assigned vendors."
            )
        if not parts:
            parts.append(
                f"Property {prop_name} has a {metrics['collection_rate_pct']}% collection rate "
                f"with {total_wo} work orders in the past 90 days."
            )
        insight = " ".join(parts)

    logger.info(
        "Insight generated",
        property_id=property_id,
        fallback=fallback_used,
        recommendation_count=len(recommendations),
    )
    return {
        "property_id": property_id,
        "property_name": prop_name,
        "generated_at": datetime.utcnow().isoformat(),
        "insight": insight,
        "metrics": metrics,
        "recommendations": recommendations,
        "fallback_used": fallback_used,
    }


# ---------------------------------------------------------------------------
# Predictive maintenance
# ---------------------------------------------------------------------------


async def predict_maintenance(
    db: AsyncIOMotorDatabase,
    property_id: str,
) -> Dict[str, Any]:
    """
    Predict upcoming maintenance needs for a property based on:
      - Historical work order patterns (frequency and cost per category)
      - Preventive maintenance schedules with upcoming due dates
      - Seasonal patterns (basic heuristics)

    Returns:
        {
            "property_id": str,
            "generated_at": str,
            "predictions": [
                {
                    "category": str,
                    "likelihood": "high" | "medium" | "low",
                    "estimated_cost": float | None,
                    "predicted_within_days": int,
                    "reasoning": str,
                }
            ],
            "upcoming_preventive": [ ... ],
            "fallback_used": bool,
        }
    """
    logger = log.bind(action="predict_maintenance", property_id=property_id)
    logger.info("Predicting maintenance needs")

    one_year_ago = (datetime.utcnow() - timedelta(days=365)).isoformat()
    today = date.today()

    # Gather historical work orders
    history: List[Dict[str, Any]] = []
    async for wo in db.work_orders.find(
        {
            "property_id": property_id,
            "status": "completed",
            "created_at": {"$gte": one_year_ago},
        },
        {"category": 1, "actual_cost": 1, "completed_date": 1, "created_at": 1},
    ):
        history.append(wo)

    # Compute frequency and average cost per category
    category_stats: Dict[str, Dict[str, Any]] = {}
    for wo in history:
        cat = wo.get("category", "general")
        if cat not in category_stats:
            category_stats[cat] = {"count": 0, "total_cost": 0.0, "dates": []}
        category_stats[cat]["count"] += 1
        category_stats[cat]["total_cost"] += float(wo.get("actual_cost") or 0)
        if wo.get("completed_date"):
            category_stats[cat]["dates"].append(str(wo["completed_date"]))

    # Compute average recurrence interval per category
    recurrence: Dict[str, Optional[float]] = {}
    for cat, stats in category_stats.items():
        dates = sorted(stats["dates"])
        if len(dates) >= 2:
            date_objects = [date.fromisoformat(d) for d in dates]
            gaps = [
                (date_objects[i + 1] - date_objects[i]).days
                for i in range(len(date_objects) - 1)
            ]
            recurrence[cat] = sum(gaps) / len(gaps)
        else:
            recurrence[cat] = None

    # Upcoming preventive maintenance (due in next 90 days)
    ninety_days = (today + timedelta(days=90)).isoformat()
    upcoming_preventive: List[Dict[str, Any]] = []
    async for pm in db.preventive_maintenance.find(
        {
            "property_id": property_id,
            "is_active": True,
            "next_due_date": {"$lte": ninety_days},
        },
        {
            "title": 1,
            "category": 1,
            "next_due_date": 1,
            "estimated_cost": 1,
            "frequency": 1,
        },
    ):
        days_until = (date.fromisoformat(str(pm["next_due_date"])) - today).days
        upcoming_preventive.append(
            {
                "title": pm.get("title", ""),
                "category": pm.get("category", ""),
                "due_date": str(pm["next_due_date"]),
                "days_until_due": days_until,
                "estimated_cost": pm.get("estimated_cost"),
                "frequency": pm.get("frequency", ""),
            }
        )

    predictions: List[Dict[str, Any]] = []
    fallback_used = False

    # Prepare a summary for Gemini
    history_summary = json.dumps(
        [
            {
                "category": cat,
                "occurrences_last_year": stats["count"],
                "avg_cost": _round2(
                    stats["total_cost"] / stats["count"] if stats["count"] else 0
                ),
                "avg_recurrence_days": recurrence.get(cat),
            }
            for cat, stats in category_stats.items()
        ],
        default=str,
    )

    preventive_summary = json.dumps(upcoming_preventive[:10], default=str)

    prompt = f"""You are an expert property maintenance predictor.

Property ID: {property_id}
Today: {today.isoformat()}

Historical work order patterns (last 12 months):
{history_summary}

Scheduled preventive maintenance due in next 90 days:
{preventive_summary}

Based on this data, predict the top maintenance issues likely to arise in the next 90 days.

Return a JSON object with this structure:
{{
  "predictions": [
    {{
      "category": "<maintenance category>",
      "likelihood": "<high|medium|low>",
      "estimated_cost": <float or null>,
      "predicted_within_days": <int>,
      "reasoning": "<brief explanation>"
    }}
  ]
}}

Include 3-6 predictions. Base predictions on historical frequency, seasonal factors,
and preventive schedule data.
Return ONLY the JSON object."""

    try:
        raw = await _with_retry(_gemini_generate, prompt)
        parsed = _safe_json(raw)
        if parsed and "predictions" in parsed:
            predictions = parsed["predictions"]
        else:
            fallback_used = True
    except Exception as exc:
        logger.warning("Gemini prediction failed, using fallback", error=str(exc))
        fallback_used = True

    if fallback_used:
        # Rule-based predictions from historical recurrence
        for cat, stats in category_stats.items():
            avg_interval = recurrence.get(cat)
            if avg_interval and avg_interval <= 90:
                avg_cost = _round2(
                    stats["total_cost"] / stats["count"] if stats["count"] else 0
                )
                predictions.append(
                    {
                        "category": cat,
                        "likelihood": "high" if avg_interval <= 45 else "medium",
                        "estimated_cost": avg_cost,
                        "predicted_within_days": int(avg_interval),
                        "reasoning": (
                            f"This category occurred {stats['count']} time(s) last year "
                            f"with an average interval of {int(avg_interval)} days."
                        ),
                    }
                )

        # Add upcoming preventive maintenance as high-likelihood predictions
        for pm in upcoming_preventive:
            if not any(p["category"] == pm["category"] for p in predictions):
                predictions.append(
                    {
                        "category": pm["category"],
                        "likelihood": "high"
                        if pm["days_until_due"] <= 14
                        else "medium",
                        "estimated_cost": pm.get("estimated_cost"),
                        "predicted_within_days": pm["days_until_due"],
                        "reasoning": (
                            f"Preventive maintenance scheduled: {pm['title']} "
                            f"(due {pm['due_date']})."
                        ),
                    }
                )

    # Sort by likelihood (high → medium → low) then by days
    likelihood_order = {"high": 0, "medium": 1, "low": 2}
    predictions.sort(
        key=lambda p: (
            likelihood_order.get(p.get("likelihood", "low"), 3),
            p.get("predicted_within_days", 999),
        )
    )

    logger.info(
        "Maintenance predictions generated",
        property_id=property_id,
        prediction_count=len(predictions),
        fallback=fallback_used,
    )
    return {
        "property_id": property_id,
        "generated_at": datetime.utcnow().isoformat(),
        "predictions": predictions,
        "upcoming_preventive": upcoming_preventive,
        "history_summary": [
            {
                "category": cat,
                "occurrences": stats["count"],
                "avg_cost": _round2(
                    stats["total_cost"] / stats["count"] if stats["count"] else 0
                ),
            }
            for cat, stats in category_stats.items()
        ],
        "fallback_used": fallback_used,
    }


# ---------------------------------------------------------------------------
# Draft invoice description
# ---------------------------------------------------------------------------


async def draft_invoice_description(
    property_id: str,
    billing_period: str,
    line_items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Use Gemini to suggest clear, professional invoice line-item descriptions.

    Parameters:
        property_id    - str property identifier
        billing_period - human-readable period, e.g. "March 2026"
        line_items     - list of dicts with at least "description" and "amount" keys

    Returns:
        {
            "property_id": str,
            "billing_period": str,
            "suggested_items": [
                {
                    "original": str,
                    "suggested": str,
                    "amount": float,
                }
            ],
            "invoice_summary": str,     # brief overall description for the invoice
            "fallback_used": bool,
        }
    """
    logger = log.bind(action="draft_invoice_description", property_id=property_id)
    logger.info("Drafting invoice descriptions", item_count=len(line_items))

    items_text = "\n".join(
        f"- {item.get('description', 'Unnamed item')}: ${float(item.get('amount', 0)):.2f}"
        for item in line_items
    )

    prompt = f"""You are a professional property manager drafting clear invoice descriptions.

Property ID: {property_id}
Billing Period: {billing_period}

Line items:
{items_text}

For each line item, suggest a clearer, more professional description.
Also write a brief overall invoice summary (1 sentence).

Return a JSON object with this structure:
{{
  "suggested_items": [
    {{
      "original": "<original description>",
      "suggested": "<improved description>",
      "amount": <float>
    }}
  ],
  "invoice_summary": "<one sentence summary>"
}}

Return ONLY the JSON object."""

    fallback_used = False
    suggested_items: List[Dict[str, Any]] = []
    invoice_summary = f"Invoice for property management services - {billing_period}."

    try:
        raw = await _with_retry(_gemini_generate, prompt)
        parsed = _safe_json(raw)
        if parsed:
            suggested_items = parsed.get("suggested_items", [])
            invoice_summary = parsed.get("invoice_summary", invoice_summary)
        else:
            fallback_used = True
    except Exception as exc:
        logger.warning(
            "Gemini description drafting failed, using originals", error=str(exc)
        )
        fallback_used = True

    if fallback_used or not suggested_items:
        # Return the original descriptions unchanged
        suggested_items = [
            {
                "original": item.get("description", ""),
                "suggested": item.get("description", ""),
                "amount": float(item.get("amount", 0)),
            }
            for item in line_items
        ]
        fallback_used = True

    logger.info(
        "Invoice descriptions drafted",
        item_count=len(suggested_items),
        fallback=fallback_used,
    )
    return {
        "property_id": property_id,
        "billing_period": billing_period,
        "suggested_items": suggested_items,
        "invoice_summary": invoice_summary,
        "fallback_used": fallback_used,
    }
