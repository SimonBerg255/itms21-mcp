# itms_client.py
"""Thin async HTTP client for the ITMS21+ public API (api.itms21.sk)."""

import asyncio
import logging
import re
from datetime import datetime, timezone
from html import unescape
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://api.itms21.sk/public/v1"
# Very generous connect timeout — the Slovak gov API is slow to accept
# connections from non-EU servers (Railway is US-based)
TIMEOUT = httpx.Timeout(connect=60.0, read=120.0, write=10.0, pool=60.0)

MAX_RETRIES = 3
RETRY_DELAYS = [2, 5, 10]  # seconds between retries

# Async client for use in the MCP server (non-blocking)
_async_client: Optional[httpx.AsyncClient] = None


def _get_async_client() -> httpx.AsyncClient:
    """Get or create the async HTTP client (lazy init)."""
    global _async_client
    if _async_client is None or _async_client.is_closed:
        _async_client = httpx.AsyncClient(
            timeout=TIMEOUT,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            headers={
                "Accept": "application/json",
                "User-Agent": "ITMS21-MCP-Server/1.0 (EU Funds Intelligence)",
            },
            follow_redirects=True,
        )
    return _async_client


async def get(endpoint: str, params: Optional[dict] = None) -> Any:
    """Make an async GET request to the ITMS21+ public API with retries."""
    url = f"{BASE_URL}{endpoint}"
    client = _get_async_client()
    last_exc = None

    for attempt in range(MAX_RETRIES):
        try:
            r = await client.get(url, params=params or {})
            r.raise_for_status()
            return r.json()
        except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError) as e:
            last_exc = e
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAYS[attempt]
                logger.warning(
                    f"ITMS21+ API attempt {attempt+1}/{MAX_RETRIES} failed "
                    f"({type(e).__name__}), retrying in {delay}s: {url}"
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    f"ITMS21+ API failed after {MAX_RETRIES} attempts: {url} — {e}"
                )
        except httpx.HTTPStatusError as e:
            # Don't retry 4xx errors
            logger.error(f"ITMS21+ API HTTP {e.response.status_code}: {url}")
            raise

    raise last_exc


async def get_list(endpoint: str, limit: int = 20, extra_params: Optional[dict] = None) -> list:
    """Fetch a list endpoint, return the items array."""
    params = {"limit": limit}
    if extra_params:
        # Remove None/empty values
        params.update({k: v for k, v in extra_params.items() if v is not None and v != ""})
    data = await get(endpoint, params)
    # ITMS21+ wraps lists in {"offset":..., "limit":..., "size":..., "results":[...]}
    if isinstance(data, dict) and "results" in data:
        return data["results"]
    if isinstance(data, list):
        return data
    return []


# === Sync wrappers for test_tools.py (NOT used by the MCP server) ===
_sync_client: Optional[httpx.Client] = None


def _get_sync_client() -> httpx.Client:
    global _sync_client
    if _sync_client is None or _sync_client.is_closed:
        _sync_client = httpx.Client(
            timeout=TIMEOUT,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            headers={"Accept": "application/json"},
            follow_redirects=True,
        )
    return _sync_client


def get_sync(endpoint: str, params: Optional[dict] = None) -> Any:
    """Synchronous GET for testing only."""
    url = f"{BASE_URL}{endpoint}"
    r = _get_sync_client().get(url, params=params or {})
    r.raise_for_status()
    return r.json()


def get_list_sync(endpoint: str, limit: int = 20, extra_params: Optional[dict] = None) -> list:
    """Synchronous get_list for testing only."""
    params = {"limit": limit}
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None and v != ""})
    data = get_sync(endpoint, params)
    if isinstance(data, dict) and "results" in data:
        return data["results"]
    if isinstance(data, list):
        return data
    return []


# === Utility functions (unchanged) ===

def strip_html(text) -> str:
    """Strip HTML tags and decode HTML entities from text."""
    if not text:
        return ""
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
    text = unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
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
