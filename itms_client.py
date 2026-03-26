# itms_client.py
"""Async HTTP client for the ITMS21+ public API with local cache fallback.

When the API (api.itms21.sk) is unreachable (e.g. from US-based Railway servers),
falls back to pre-cached JSON files in the ./cache/ directory. The cache is
generated locally where the API is reachable and committed to the repo.
"""

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://api.itms21.sk/public/v1"
TIMEOUT = httpx.Timeout(connect=15.0, read=60.0, write=10.0, pool=15.0)
CACHE_DIR = Path(__file__).parent / "cache"

MAX_RETRIES = 2
RETRY_DELAYS = [2, 4]

# Track whether API is reachable — avoid retrying every call if first one fails
_api_reachable: Optional[bool] = None

# Async client
_async_client: Optional[httpx.AsyncClient] = None


def _get_async_client() -> httpx.AsyncClient:
    global _async_client
    if _async_client is None or _async_client.is_closed:
        _async_client = httpx.AsyncClient(
            timeout=TIMEOUT,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            headers={
                "Accept": "application/json",
                "User-Agent": "ITMS21-MCP-Server/1.0",
            },
            follow_redirects=True,
        )
    return _async_client


# ─── Cache mapping ───────────────────────────────────────────────
# Maps (endpoint, key_params) → cache filename
# This lets us serve cached data for the most common queries

def _cache_key(endpoint: str, params: Optional[dict] = None) -> Optional[str]:
    """Determine which cache file to use for a given request, if any."""
    p = params or {}

    # /vyzva list (open calls)
    if endpoint == "/vyzva" and p.get("ajUkoncene") == "false":
        return "vyzva_open"

    # /vyzva detail
    if endpoint.startswith("/vyzva/id/"):
        call_id = endpoint.split("/")[-1]
        return f"vyzva_detail_{call_id}"

    # /planovanavyzva list
    if endpoint == "/planovanavyzva":
        return "planovanavyzva"

    # /zonfp list — by call ID
    if endpoint == "/zonfp" and "vyzvaId" in p:
        vid = p["vyzvaId"]
        return f"zonfp_call_{vid}"

    # /zonfp list — approved (general)
    if endpoint == "/zonfp" and p.get("schvalena") == "true":
        return "zonfp_approved"

    # /zonfp detail
    if endpoint.startswith("/zonfp/id/"):
        app_id = endpoint.split("/")[-1]
        return f"zonfp_detail_{app_id}"

    # /projekt list — by call ID
    if endpoint == "/projekt" and "vyzvaId" in p:
        vid = p["vyzvaId"]
        return f"projekt_call_{vid}"

    # /program list
    if endpoint == "/program":
        return "program"

    # /specifickycielprogramu list
    if endpoint == "/specifickycielprogramu":
        return "specifickycielprogramu"

    return None


def _load_cache(cache_name: str) -> Optional[Any]:
    """Load a cached JSON file if it exists."""
    path = CACHE_DIR / f"{cache_name}.json"
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            logger.info(f"Cache hit: {cache_name}")
            return data
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Cache read failed for {cache_name}: {e}")
    return None


def _filter_cached_results(items: list, params: dict) -> list:
    """Apply query filters to cached data (client-side filtering)."""
    results = items

    # kod = substring match on item code
    kod = params.get("kod", "")
    if kod:
        results = [i for i in results if kod.lower() in i.get("kod", "").lower()]

    # program = match on programme code
    prog = params.get("program", "")
    if prog:
        results = [i for i in results
                   if i.get("program", {}).get("kod", "") == prog]

    # opravnenyZiadatel = match on kodZdroj of eligible applicants
    oz = params.get("opravnenyZiadatel", "")
    if oz:
        results = [i for i in results
                   if any(z.get("kod", "") == oz for z in i.get("ziadatel", []))]

    # miestoRealizacie = match on region kod
    mr = params.get("miestoRealizacie", "")
    if mr:
        results = [i for i in results
                   if any(m.get("kod", "") == mr for m in i.get("miestoRealizacie", []))]

    # specifickyCielProgramuId = match on specific objective ID
    sc_id = params.get("specifickyCielProgramuId", "")
    if sc_id:
        sc_id_int = int(sc_id)
        results = [i for i in results
                   if any(sc.get("id") == sc_id_int
                          for sc in i.get("specifickyCielProgramu", []))]

    # vyzvaId = match on call ID (for zonfp/projekt)
    vyzva_id = params.get("vyzvaId", "")
    if vyzva_id:
        vid = int(vyzva_id)
        results = [i for i in results
                   if i.get("vyzva", {}).get("id") == vid]

    # ziadatel = substring on applicant name (for zonfp)
    ziadatel = params.get("ziadatel", "")
    if ziadatel:
        results = [i for i in results
                   if ziadatel.lower() in i.get("ziadatel", {}).get("nazov", "").lower()]

    # prijimatel = substring on beneficiary name (for projekt)
    prijimatel = params.get("prijimatel", "")
    if prijimatel:
        results = [i for i in results
                   if prijimatel.lower() in i.get("prijimatel", {}).get("nazov", "").lower()]

    # miestorealizacie = substring on region name (for projekt)
    mr2 = params.get("miestorealizacie", "")
    if mr2:
        results = [i for i in results
                   if any(mr2.lower() in m.get("nazovSk", "").lower()
                          for m in i.get("miestoRealizacie", []))]

    # vrealizacii filter
    if params.get("vrealizacii") == "true":
        # Already filtered in cache, but just in case
        pass

    # schvalena filter
    if params.get("schvalena") == "true":
        results = [i for i in results if i.get("schvalena")]

    return results


async def get(endpoint: str, params: Optional[dict] = None) -> Any:
    """Fetch from API with cache fallback."""
    global _api_reachable
    url = f"{BASE_URL}{endpoint}"
    p = params or {}

    # If API was already unreachable, go straight to cache
    if _api_reachable is False:
        return _get_from_cache_or_raise(endpoint, p)

    # Try the live API
    client = _get_async_client()
    last_exc = None

    for attempt in range(MAX_RETRIES):
        try:
            r = await client.get(url, params=p)
            r.raise_for_status()
            _api_reachable = True
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
                logger.warning(
                    f"ITMS21+ API unreachable after {MAX_RETRIES} attempts, "
                    f"switching to cache: {url}"
                )
                _api_reachable = False
        except httpx.HTTPStatusError as e:
            logger.error(f"ITMS21+ API HTTP {e.response.status_code}: {url}")
            raise

    # API failed — try cache
    return _get_from_cache_or_raise(endpoint, p)


def _get_from_cache_or_raise(endpoint: str, params: dict) -> Any:
    """Try to serve from cache, raise if no cache available."""
    cache_name = _cache_key(endpoint, params)
    if cache_name:
        data = _load_cache(cache_name)
        if data is not None:
            return data

    raise httpx.ConnectTimeout(
        f"ITMS21+ API unreachable and no cache available for {endpoint}"
    )


async def get_list(endpoint: str, limit: int = 20, extra_params: Optional[dict] = None) -> list:
    """Fetch a list endpoint with cache-aware filtering."""
    params = {"limit": limit}
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None and v != ""})

    data = await get(endpoint, params)

    # Extract results array
    if isinstance(data, dict) and "results" in data:
        items = data["results"]
    elif isinstance(data, list):
        items = data
    else:
        items = []

    # If serving from cache, we need to apply filters client-side
    # (cache contains ALL records, not filtered)
    if _api_reachable is False and items:
        items = _filter_cached_results(items, params)

    # Apply limit
    if limit > 0 and len(items) > limit:
        items = items[:limit]

    return items


# === Utility functions ===

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
