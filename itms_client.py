# itms_client.py
"""Thin HTTP client for the ITMS21+ public API (api.itms21.sk)."""

import re
from datetime import datetime, timezone
from html import unescape
from typing import Any, Optional

import httpx

BASE_URL = "https://api.itms21.sk/public/v1"
TIMEOUT = 30.0


def get(endpoint: str, params: Optional[dict] = None) -> Any:
    """Make a GET request to the ITMS21+ public API."""
    url = f"{BASE_URL}{endpoint}"
    with httpx.Client(timeout=TIMEOUT) as client:
        r = client.get(url, params=params or {})
        r.raise_for_status()
        return r.json()


def get_list(endpoint: str, limit: int = 20, extra_params: Optional[dict] = None) -> list:
    """Fetch a list endpoint, return the items array."""
    params = {"limit": limit}
    if extra_params:
        # Remove None/empty values
        params.update({k: v for k, v in extra_params.items() if v is not None and v != ""})
    data = get(endpoint, params)
    # ITMS21+ wraps lists in {"offset":..., "limit":..., "size":..., "results":[...]}
    if isinstance(data, dict) and "results" in data:
        return data["results"]
    if isinstance(data, list):
        return data
    return []


def strip_html(text) -> str:
    """Strip HTML tags and decode HTML entities from text."""
    if not text:
        return ""
    # Handle lists (e.g. cielovaSkupina can be a list of dicts or strings)
    if isinstance(text, list):
        parts = []
        for item in text:
            if isinstance(item, dict):
                parts.append(item.get("nazov", item.get("nazovSk", str(item))))
            else:
                parts.append(str(item))
        text = "; ".join(parts)
    if not isinstance(text, str):
        return str(text)
    # Decode HTML entities first
    text = unescape(text)
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def format_date(timestamp_ms: Optional[int]) -> str:
    """Convert unix timestamp in milliseconds to a readable date string."""
    if not timestamp_ms:
        return "N/A"
    try:
        dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
        return dt.strftime("%Y-%m-%d")
    except (ValueError, OSError):
        return "N/A"


def format_amount(amount: Optional[float]) -> str:
    """Format EUR amount with thousand separators."""
    if amount is None:
        return "N/A"
    return f"€{amount:,.2f}"


def safe_get(d: Optional[dict], *keys: str, default: str = "N/A") -> Any:
    """Safely navigate nested dict keys."""
    if d is None:
        return default
    current = d
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        else:
            return default
        if current is None:
            return default
    return current
