#!/usr/bin/env python3
"""
ITMS21+ Document Downloader
============================
Downloads all call documents from the Slovak EU Funds portal (ITMS21+).

For each open call (výzva), this script:
1. Fetches the call list from the ITMS21+ Open Data API
2. Navigates to the portal page for each call
3. Expands the "Doplňujúce informácie a dokumenty" accordion
4. Downloads all ZIP/PDF files listed in that section
5. Saves files into ./downloads/{call_code}/{filename}

Usage:
    python3 download_itms_docs.py                  # Download all open calls
    python3 download_itms_docs.py --id 3165         # Download a single call by ID
    python3 download_itms_docs.py --limit 5         # Download first 5 calls only
    python3 download_itms_docs.py --dry-run         # List calls without downloading

Requires:
    pip install playwright httpx
    playwright install chromium
"""

import argparse
import asyncio
import os
import re
import sys
import time
from pathlib import Path

import httpx
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

# ─── Configuration ───────────────────────────────────────────────────────────

API_BASE = "https://api.itms21.sk/public/v1"
PORTAL_BASE = "https://portal.itms21.sk"
DOWNLOAD_DIR = Path("./downloads")
DELAY_BETWEEN_CALLS = 2  # seconds between processing calls
DOWNLOAD_TIMEOUT = 60000  # ms to wait for each download
PAGE_LOAD_TIMEOUT = 60000  # ms to wait for page load
ACCORDION_WAIT = 3000  # ms to wait after clicking accordion


# ─── API Functions ───────────────────────────────────────────────────────────

def fetch_open_calls(limit: int = -1) -> list[dict]:
    """Fetch all open (non-closed) calls from the ITMS21+ API."""
    params = {
        "limit": limit,
        "vyhlasena": "true",
        "zrusena": "false",
    }
    url = f"{API_BASE}/vyzva"
    print(f"Fetching calls from API: {url}")
    with httpx.Client(timeout=30) as client:
        r = client.get(url, params=params)
        r.raise_for_status()
        data = r.json()

    results = data.get("results", [])
    print(f"API returned {len(results)} calls (total in system: {data.get('size', '?')})")
    return results


def fetch_single_call(call_id: int) -> dict | None:
    """Fetch a single call by ID from the API."""
    url = f"{API_BASE}/vyzva/id/{call_id}"
    with httpx.Client(timeout=30) as client:
        r = client.get(url)
        r.raise_for_status()
        return r.json()


# ─── Filename Sanitization ──────────────────────────────────────────────────

def sanitize_filename(name: str) -> str:
    """Make a string safe for use as a filename/directory name."""
    # Replace problematic characters
    name = name.replace("/", "-").replace("\\", "-")
    name = re.sub(r'[<>:"|?*]', "_", name)
    # Collapse multiple spaces/underscores
    name = re.sub(r"\s+", " ", name).strip()
    # Limit length
    if len(name) > 200:
        name = name[:200]
    return name


# ─── Download Logic ──────────────────────────────────────────────────────────

async def download_call_documents(page, call_id: int, call_code: str, output_dir: Path) -> list[str]:
    """
    Navigate to a call's portal page, expand the documents section,
    and download all files.

    Returns a list of downloaded filenames.
    """
    url = f"{PORTAL_BASE}/vyhlasena-vyzva/?id={call_id}"
    downloaded = []

    try:
        await page.goto(url, wait_until="networkidle", timeout=PAGE_LOAD_TIMEOUT)
    except PlaywrightTimeout:
        print(f"    WARNING: Page load timed out, attempting to continue...")
        # Page may still be usable even if networkidle wasn't reached

    # Accept cookies if the banner appears (first visit only)
    try:
        cookie_btn = page.locator("button:has-text('Odmietnuť voliteľné cookies')")
        if await cookie_btn.is_visible(timeout=2000):
            await cookie_btn.click()
            await page.wait_for_timeout(500)
    except Exception:
        pass

    # Find and click the "Doplňujúce informácie a dokumenty" accordion button
    accordion_btn = page.locator(
        "button.govuk-accordion__section-button:has-text('Doplňujúce informácie a dokumenty')"
    )

    try:
        await accordion_btn.wait_for(state="visible", timeout=15000)
    except PlaywrightTimeout:
        print(f"    WARNING: 'Doplňujúce informácie a dokumenty' accordion not found")
        return []

    # Check if already expanded
    expanded = await accordion_btn.get_attribute("aria-expanded")
    if expanded != "true":
        await accordion_btn.click()
        await page.wait_for_timeout(ACCORDION_WAIT)

    # Extract file info: each <li> contains "filename <button>Stiahnuť</button>"
    file_info = await page.evaluate("""() => {
        const btns = document.querySelectorAll("button.govuk-accordion__section-button");
        let targetSection = null;
        for (const btn of btns) {
            if (btn.textContent?.includes('Doplňujúce')) {
                targetSection = btn.closest('.govuk-accordion__section');
                break;
            }
        }
        if (!targetSection) return [];

        const items = targetSection.querySelectorAll('li');
        return Array.from(items).map((li, idx) => {
            const btn = li.querySelector('button');
            if (!btn || !btn.textContent?.includes('Stiahnuť')) return null;
            const filename = li.textContent?.replace('Stiahnuť', '').trim();
            return {index: idx, filename: filename};
        }).filter(x => x !== null);
    }""")

    if not file_info:
        print(f"    No downloadable files found")
        return []

    print(f"    Found {len(file_info)} files to download")

    # Get a reference to the download buttons inside the section
    # We need to re-locate them each time since the page state may change
    section_locator = page.locator(
        "button.govuk-accordion__section-button:has-text('Doplňujúce informácie a dokumenty')"
    ).locator("xpath=ancestor::div[contains(@class, 'govuk-accordion__section')]").first

    download_buttons = section_locator.locator("li button:has-text('Stiahnuť')")
    btn_count = await download_buttons.count()

    for i in range(btn_count):
        info = file_info[i] if i < len(file_info) else {"filename": f"unknown_file_{i}"}
        raw_filename = info["filename"]
        safe_filename = sanitize_filename(raw_filename)

        if not safe_filename:
            safe_filename = f"document_{i}"

        dest_path = output_dir / safe_filename

        # Skip if already downloaded
        if dest_path.exists() and dest_path.stat().st_size > 0:
            print(f"    [{i+1}/{btn_count}] SKIP (exists): {safe_filename}")
            downloaded.append(safe_filename)
            continue

        try:
            async with page.expect_download(timeout=DOWNLOAD_TIMEOUT) as download_info:
                await download_buttons.nth(i).click()

            download = await download_info.value

            # Use the suggested filename from the server if available
            suggested = download.suggested_filename
            if suggested and suggested != "download":
                safe_filename = sanitize_filename(suggested)
                dest_path = output_dir / safe_filename

            # Wait for the download to complete
            await download.save_as(str(dest_path))

            size = dest_path.stat().st_size
            print(f"    [{i+1}/{btn_count}] OK: {safe_filename} ({size:,} bytes)")
            downloaded.append(safe_filename)

        except PlaywrightTimeout:
            print(f"    [{i+1}/{btn_count}] TIMEOUT: {safe_filename}")
        except Exception as e:
            print(f"    [{i+1}/{btn_count}] ERROR: {safe_filename} — {e}")

        # Small delay between downloads
        await page.wait_for_timeout(500)

    return downloaded


# ─── Main ────────────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="Download ITMS21+ call documents")
    parser.add_argument("--id", type=int, help="Download documents for a single call ID")
    parser.add_argument("--limit", type=int, default=-1, help="Limit number of calls to process")
    parser.add_argument("--dry-run", action="store_true", help="List calls without downloading")
    parser.add_argument("--headed", action="store_true", help="Run browser in headed mode (visible)")
    args = parser.parse_args()

    # Fetch calls
    if args.id:
        call_data = fetch_single_call(args.id)
        if not call_data:
            print(f"Call with ID {args.id} not found")
            sys.exit(1)
        calls = [call_data]
    else:
        calls = fetch_open_calls(limit=args.limit)

    if not calls:
        print("No calls to process")
        sys.exit(0)

    print(f"\n{'='*60}")
    print(f"ITMS21+ Document Downloader")
    print(f"{'='*60}")
    print(f"Calls to process: {len(calls)}")
    print(f"Download directory: {DOWNLOAD_DIR.resolve()}")
    print(f"{'='*60}\n")

    if args.dry_run:
        print("DRY RUN — listing calls only:\n")
        for i, call in enumerate(calls):
            code = call.get("kod", "N/A")
            name = call.get("nazovSk", "N/A")
            call_id = call.get("id", "N/A")
            docs = call.get("dokument", [])
            print(f"  [{i+1}] ID={call_id} Code={code}")
            print(f"       Name: {name[:100]}")
            print(f"       Documents in API: {len(docs) if docs else 0}")
        print(f"\nTotal: {len(calls)} calls")
        return

    # Create download directory
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    # Launch browser
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=not args.headed,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = await browser.new_context(
            accept_downloads=True,
            viewport={"width": 1280, "height": 2000},
        )
        page = await context.new_page()

        total_files = 0
        total_calls_with_docs = 0
        failed_calls = []
        start_time = time.time()

        for i, call in enumerate(calls):
            call_id = call.get("id")
            call_code = call.get("kod", f"unknown_{call_id}")
            call_name = call.get("nazovSk", "N/A")

            print(f"\n[{i+1}/{len(calls)}] Processing: {call_code}")
            print(f"    Name: {call_name[:100]}")
            print(f"    URL: {PORTAL_BASE}/vyhlasena-vyzva/?id={call_id}")

            # Create output directory for this call
            safe_code = sanitize_filename(call_code)
            call_dir = DOWNLOAD_DIR / safe_code
            call_dir.mkdir(parents=True, exist_ok=True)

            try:
                downloaded = await download_call_documents(page, call_id, call_code, call_dir)

                if downloaded:
                    total_files += len(downloaded)
                    total_calls_with_docs += 1
                else:
                    # Remove empty directory
                    try:
                        call_dir.rmdir()
                    except OSError:
                        pass

            except Exception as e:
                print(f"    FATAL ERROR: {e}")
                failed_calls.append((call_code, str(e)))

            # Delay between calls to avoid hammering the server
            if i < len(calls) - 1:
                await asyncio.sleep(DELAY_BETWEEN_CALLS)

        await browser.close()

    # ─── Summary ─────────────────────────────────────────────────────────────
    elapsed = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"DOWNLOAD COMPLETE")
    print(f"{'='*60}")
    print(f"Calls processed:    {len(calls)}")
    print(f"Calls with docs:    {total_calls_with_docs}")
    print(f"Total files:        {total_files}")
    print(f"Failed calls:       {len(failed_calls)}")
    print(f"Time elapsed:       {elapsed:.1f}s")
    print(f"Download directory: {DOWNLOAD_DIR.resolve()}")

    if failed_calls:
        print(f"\nFailed calls:")
        for code, err in failed_calls:
            print(f"  - {code}: {err}")

    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
