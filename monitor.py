import asyncio
import os
import re
import sys
import time
from pathlib import Path

from playwright.async_api import (
    async_playwright,
    TimeoutError as PlaywrightTimeoutError,
)


# ============================================================================
# CONFIGURATION
# ============================================================================

URL = os.getenv(
    "CALCULATOR_URL",
    "https://www.posta.ba/kalkulator-cijena/",
)

CALCULATOR_IFRAME_URL_PART = (
    "bhpwebout.posta.ba/KalkulatorCijena_WEB_app"
)

PAGE_FILE = Path("page.html")
IFRAME_FILE = Path("iframe.html")
IFRAME_TEXT_FILE = Path("iframe.txt")
COUNTRIES_FILE = Path("countries.txt")
RESULTS_FILE = Path("calculator-results.txt")

DIAGNOSTIC_FILE = Path("diagnostic.txt")
DIAGNOSTIC_HTML_FILE = Path("diagnostic.html")
DIAGNOSTIC_PNG_FILE = Path("diagnostic.png")

# Keep the individual operations short.
NAVIGATION_TIMEOUT = 30_000
NORMAL_TIMEOUT = 5_000
SHORT_TIMEOUT = 1_500

# Hard upper bound for the entire monitor.
TOTAL_TIMEOUT = 120_000

# Per-destination timeout.
DESTINATION_TIMEOUT = 5_000

# Small delay after selecting a destination, allowing ASP.NET/DevExpress
# callbacks to update the calculator.
AFTER_SELECTION_DELAY = 400


# ============================================================================
# HELPERS
# ============================================================================

def section(title):
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def save_text(path, text):
    try:
        text = text or ""
        path.write_text(text, encoding="utf-8")
        print(f"Saved {path} ({len(text):,} bytes)")
    except Exception as exc:
        print(f"Could not save {path}: {exc}")


async def safe_content(page):
    try:
        return await page.content()
    except Exception:
        return ""


async def safe_screenshot(page, path=DIAGNOSTIC_PNG_FILE):
    try:
        await page.screenshot(
            path=str(path),
            full_page=True,
        )
        print(f"Saved {path}")
    except Exception as exc:
        print(f"Could not save screenshot: {exc}")


async def frame_content(frame):
    try:
        return await frame.content()
    except Exception:
        return ""


def clean_text(value):
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_for_compare(value):
    value = clean_text(value)
    return value.casefold()


def is_placeholder_country(text):
    lowered = normalize_for_compare(text)

    return lowered in {
        "",
        "odredišna zemlja",
        "odredisna zemlja",
        "izaberite",
        "odaberite",
        "select",
        "select country",
    }


# ============================================================================
# CALCULATOR FRAME
# ============================================================================

async def find_calculator_frame(page):
    section("LOCATING CALCULATOR IFRAME")

    frames = page.frames

    print(f"Number of frames: {len(frames)}")

    for index, frame in enumerate(frames):
        try:
            frame_url = frame.url
        except Exception:
            frame_url = ""

        print(f"Checking frame {index}: {frame_url}")

        if CALCULATOR_IFRAME_URL_PART.lower() in frame_url.lower():
            print(f"FOUND CALCULATOR FRAME: {index}")
            print(f"Calculator URL: {frame_url}")
            return frame

    print("URL match not found. Inspecting frame HTML...")

    for index, frame in enumerate(frames):
        html = await frame_content(frame)

        if not html:
            continue

        lower = html.lower()

        if (
            "kalkulator cijena" in lower
            and (
                "ddlunobpitez" in lower
                or "ddlmeobpioderdiste" in lower
                or "međunarodni promet" in lower
                or "medunarodni promet" in lower
            )
        ):
            print(f"FOUND calculator by HTML: frame {index}")
            print(f"Calculator URL: {frame.url}")
            return frame

    return None


async def wait_for_calculator_frame(page, timeout_ms=15_000):
    deadline = (
        asyncio.get_running_loop().time()
        + timeout_ms / 1000
    )

    while asyncio.get_running_loop().time() < deadline:
        frame = await find_calculator_frame(page)

        if frame is not None:
            return frame

        await page.wait_for_timeout(500)

    return None


# ============================================================================
# DIAGNOSTICS
# ============================================================================

async def save_calculator_diagnostics(frame):
    html = await frame_content(frame)
    save_text(IFRAME_FILE, html)

    try:
        text = await frame.locator("body").inner_text(
            timeout=NORMAL_TIMEOUT
        )
    except Exception:
        text = ""

    save_text(IFRAME_TEXT_FILE, text)

    return html, text


async def build_diagnostic(page, frame=None, extra=""):
    section("CREATING DIAGNOSTICS")

    page_html = await safe_content(page)
    save_text(DIAGNOSTIC_HTML_FILE, page_html)

    parts = [
        "JP BH POŠTA CALCULATOR DIAGNOSTIC",
        "",
        f"URL: {URL}",
        f"Page URL: {page.url}",
        "",
        f"Frame count: {len(page.frames)}",
    ]

    for index, frame_item in enumerate(page.frames):
        try:
            frame_url = frame_item.url
        except Exception:
            frame_url = ""

        parts.append(
            f"FRAME {index}: {frame_url}"
        )

    if frame is not None:
        frame_html = await frame_content(frame)

        parts.extend([
            "",
            f"CALCULATOR FRAME URL: {frame.url}",
            f"CALCULATOR FRAME HTML LENGTH: {len(frame_html)}",
        ])

        try:
            body_text = await frame.locator(
                "body"
            ).inner_text(timeout=3000)
        except Exception:
            body_text = ""

        parts.extend([
            "",
            "CALCULATOR FRAME TEXT:",
            body_text[:30000],
        ])

        try:
            select_count = await frame.locator(
                "select"
            ).count()
        except Exception:
            select_count = 0

        parts.append(
            f"SELECT COUNT: {select_count}"
        )

        try:
            input_count = await frame.locator(
                "input"
            ).count()
        except Exception:
            input_count = 0

        parts.append(
            f"INPUT COUNT: {input_count}"
        )

    if extra:
        parts.extend([
            "",
            "ADDITIONAL ERROR:",
            extra,
        ])

    save_text(
        DIAGNOSTIC_FILE,
        "\n".join(parts),
    )

    await safe_screenshot(page)


# ============================================================================
# INTERNATIONAL TAB
# ============================================================================

async def activate_international(frame):
    section("ACTIVATING MEĐUNARODNI PROMET")

    # First check whether international content is already active.
    existing_select = await find_country_select(
        frame,
        quiet=True,
    )

    if existing_select is not None:
        print(
            "International calculator already appears to be active."
        )
        return True

    selectors = [
        "text=Međunarodni promet",
        "text=Medjunarodni promet",
    ]

    for selector in selectors:
        try:
            candidates = frame.locator(selector)
            count = await candidates.count()

            print(
                f"Selector {selector!r}: {count} candidate(s)"
            )

            for i in range(count):
                candidate = candidates.nth(i)

                try:
                    if not await candidate.is_visible():
                        continue
                except Exception:
                    continue

                try:
                    tag = await candidate.evaluate(
                        "(el) => el.tagName"
                    )
                except Exception:
                    tag = "?"

                try:
                    outer = await candidate.evaluate(
                        "(el) => el.outerHTML"
                    )
                except Exception:
                    outer = ""

                print(
                    f"Visible candidate #{i}: "
                    f"tag={tag}"
                )
                print(
                    f"HTML: {outer[:1000]}"
                )

                # Try the actual text element first.
                try:
                    await candidate.click(
                        timeout=NORMAL_TIMEOUT,
                        force=True,
                    )
                except Exception as exc:
                    print(
                        f"Direct click failed: {exc}"
                    )

                    # Try nearby clickable ancestors.
                    clicked = False

                    ancestor_selectors = [
                        "xpath=ancestor::a[1]",
                        "xpath=ancestor::td[1]",
                        "xpath=ancestor::*[@role='tab'][1]",
                        "xpath=ancestor::div[1]",
                    ]

                    for ancestor_selector in ancestor_selectors:
                        try:
                            ancestor = candidate.locator(
                                ancestor_selector
                            )

                            if await ancestor.count():
                                await ancestor.first.click(
                                    timeout=SHORT_TIMEOUT,
                                    force=True,
                                )
                                clicked = True
                                break
                        except Exception:
                            pass

                    if not clicked:
                        # Last resort: JavaScript click.
                        try:
                            await candidate.evaluate(
                                "(el) => el.click()"
                            )
                        except Exception as js_exc:
                            print(
                                "JavaScript click failed: "
                                f"{js_exc}"
                            )
                            continue

                await frame.page.wait_for_timeout(800)

                # Verify that the click actually did something.
                select = await wait_for_country_select(
                    frame,
                    timeout_ms=5_000,
                )

                if select is not None:
                    print(
                        "International calculator activated."
                    )
                    return True

    return False


# ============================================================================
# COUNTRY SELECT
# ============================================================================

async def find_country_select(frame, quiet=False):
    if not quiet:
        section("LOCATING COUNTRY DROPDOWN")

    selects = frame.locator("select")

    try:
        count = await selects.count()
    except Exception:
        return None

    if not quiet:
        print(f"Number of select elements: {count}")

    country_markers = [
        "Afganistan",
        "Albanija",
        "Alžir",
        "Australija",
        "Austrija",
        "Belgija",
        "Bosna i Hercegovina",
        "Hrvatska",
        "Japan",
        "Njemačka",
        "Njemacka",
        "Sjedinjene Americke Države",
        "Sjedinjene Američke Države",
        "United States",
        "Velika Britanija",
    ]

    for i in range(count):
        select = selects.nth(i)

        try:
            select_id = await select.get_attribute("id")
            select_name = await select.get_attribute("name")
            text = await select.inner_text()

            option_count = await select.locator(
                "option"
            ).count()

            score = sum(
                1
                for marker in country_markers
                if marker.casefold() in text.casefold()
            )

            if not quiet:
                print()
                print(f"SELECT #{i}")
                print(f"  id   = {select_id}")
                print(f"  name = {select_name}")
                print(f"  option count = {option_count}")
                print(f"  marker score = {score}")
                print(f"  text = {text[:1000]}")

            if score >= 2:
                print(
                    f"COUNTRY SELECT FOUND: #{i}"
                )
                return select

            if option_count >= 20:
                print(
                    "COUNTRY SELECT FOUND by option count: "
                    f"#{i} ({option_count} options)"
                )
                return select

        except Exception as exc:
            if not quiet:
                print(
                    f"Error inspecting select #{i}: {exc}"
                )

    return None


async def wait_for_country_select(
    frame,
    timeout_ms=10_000,
):
    deadline = (
        asyncio.get_running_loop().time()
        + timeout_ms / 1000
    )

    while asyncio.get_running_loop().time() < deadline:
        select = await find_country_select(
            frame,
            quiet=True,
        )

        if select is not None:
            return select

        await frame.page.wait_for_timeout(300)

    return None


# ============================================================================
# RAW DESTINATIONS
# ============================================================================

async def extract_destination_options(select):
    section("EXTRACTING DESTINATION OPTIONS")

    options = select.locator("option")
    count = await options.count()

    print(
        f"Destination option count: {count}"
    )

    destinations = []

    for i in range(count):
        option = options.nth(i)

        try:
            text = clean_text(
                await option.inner_text()
            )

            value = await option.get_attribute(
                "value"
            )

            disabled = await option.is_disabled()

            if is_placeholder_country(text):
                continue

            item = {
                "name": text,
                "value": value or "",
                "disabled": bool(disabled),
            }

            destinations.append(item)

            print(
                f"[{len(destinations):03d}] "
                f"{text} "
                f"(value={value}, "
                f"disabled={disabled})"
            )

        except Exception as exc:
            print(
                f"Could not read option {i}: {exc}"
            )

    return destinations


def save_countries(destinations):
    section("SAVING RAW DESTINATIONS")

    lines = []

    for item in destinations:
        suffix = ""

        if item["disabled"]:
            suffix = " [DISABLED OPTION]"

        lines.append(
            f"{item['name']}{suffix}"
        )

    text = "\n".join(lines)

    if text:
        text += "\n"

    save_text(
        COUNTRIES_FILE,
        text,
    )

    print(
        f"Saved {len(destinations)} raw destination "
        f"options to {COUNTRIES_FILE}"
    )


# ============================================================================
# CALCULATOR RESPONSE DETECTION
# ============================================================================

def classify_calculator_text(text):
    """
    This is deliberately conservative.

    The monitor must NOT say AVAILABLE merely because a country appears
    in the dropdown.

    We look for explicit calculator failure/unavailability messages first.
    Otherwise we return UNKNOWN unless the calculator visibly produces
    a price/result.

    This allows calculator-results.txt to distinguish:
      AVAILABLE
      UNAVAILABLE
      UNDETERMINED
      ERROR
    """

    normalized = clean_text(text)
    lower = normalized.casefold()

    unavailable_markers = [
        "nije moguće",
        "nije moguce",
        "nije dostupno",
        "nije dostupna",
        "nije dostupna usluga",
        "usluga nije dostupna",
        "pošiljke se ne primaju",
        "posiljke se ne primaju",
        "ne može se poslati",
        "ne moze se poslati",
        "nema cijene",
        "nema cijena",
        "nije moguće izračunati",
        "nije moguce izracunati",
        "nije moguće izracunati",
        "za ovu zemlju",
        "za odredišnu zemlju",
        "za odredisnu zemlju",
        "not available",
        "unavailable",
        "service unavailable",
        "not accepted",
        "cannot be sent",
    ]

    for marker in unavailable_markers:
        if marker in lower:
            return "UNAVAILABLE", marker

    # Price/result indicators.
    price_markers = [
        "cijena",
        "cijene",
        "iznos",
        "km",
        "eur",
        "€",
        "rezultat",
        "ukupno",
    ]

    has_price_marker = any(
        marker in lower
        for marker in price_markers
    )

    # Look for decimal/number patterns near common currency/result
    # terminology.
    number_patterns = [
        r"\b\d+[.,]\d{2}\b",
        r"\b\d+\s*km\b",
        r"\b\d+\s*eur\b",
        r"\b\d+\s*€\b",
    ]

    has_number = any(
        re.search(pattern, lower)
        for pattern in number_patterns
    )

    if has_price_marker and has_number:
        return "AVAILABLE", "price/result detected"

    return "UNDETERMINED", "no explicit availability result detected"


# ============================================================================
# DESTINATION TESTING
# ============================================================================

async def get_frame_text(frame):
    try:
        return await frame.locator(
            "body"
        ).inner_text(
            timeout=SHORT_TIMEOUT
        )
    except Exception:
        return ""


async def snapshot_controls(frame):
    """
    Capture enough state to detect whether selecting a destination caused
    the calculator to change.
    """

    result = {
        "text": "",
        "inputs": [],
        "buttons": [],
    }

    result["text"] = await get_frame_text(frame)

    try:
        inputs = frame.locator("input")
        count = await inputs.count()

        for i in range(min(count, 100)):
            inp = inputs.nth(i)

            try:
                result["inputs"].append({
                    "id": await inp.get_attribute("id"),
                    "name": await inp.get_attribute("name"),
                    "value": await inp.input_value(),
                    "type": await inp.get_attribute("type"),
                })
            except Exception:
                pass
    except Exception:
        pass

    try:
        buttons = frame.locator(
            "input[type='button'], "
            "input[type='submit'], "
            "button"
        )

        count = await buttons.count()

        for i in range(min(count, 100)):
            button = buttons.nth(i)

            try:
                result["buttons"].append({
                    "id": await button.get_attribute("id"),
                    "value": await button.get_attribute("value"),
                    "text": clean_text(
                        await button.inner_text()
                    ),
                })
            except Exception:
                pass
    except Exception:
        pass

    return result


async def locate_calculate_button(frame):
    """
    Find the calculator's actual button.

    The page text in previous runs contained:
        Izračunn/h1>

    so we intentionally do not rely on a fixed ASP.NET ID.
    """

    candidates = []

    # Text-based buttons.
    for text in [
        "Izračun",
        "Izracun",
        "Izračunaj",
        "Izracunaj",
    ]:
        try:
            locator = frame.get_by_text(
                text,
                exact=False,
            )

            count = await locator.count()

            for i in range(count):
                item = locator.nth(i)

                try:
                    if await item.is_visible():
                        candidates.append(item)
                except Exception:
                    pass
        except Exception:
            pass

    # Common ASP.NET/HTML button controls.
    try:
        controls = frame.locator(
            "input[type='button'], "
            "input[type='submit'], "
            "button"
        )

        count = await controls.count()

        for i in range(count):
            item = controls.nth(i)

            try:
                if not await item.is_visible():
                    continue

                value = (
                    await item.get_attribute("value")
                    or ""
                )

                text = clean_text(
                    await item.inner_text()
                )

                combined = (
                    f"{value} {text}"
                ).casefold()

                if (
                    "izrač" in combined
                    or "izrac" in combined
                ):
                    candidates.append(item)

            except Exception:
                pass
    except Exception:
        pass

    return candidates[0] if candidates else None


async def test_destination(
    frame,
    select,
    destination,
):
    """
    Test ONE destination.

    The result is deliberately conservative.

    A country being present in the select does not mean the service
    is available.

    We select it, wait for any callback/update, optionally click the
    calculator button, then inspect the resulting calculator state.
    """

    name = destination["name"]
    value = destination["value"]

    started = time.monotonic()

    try:
        async def operation():
            # Re-read the select because ASP.NET/DevExpress can replace
            # DOM nodes during callbacks.
            current_select = await find_country_select(
                frame,
                quiet=True,
            )

            if current_select is None:
                raise RuntimeError(
                    "Country select disappeared."
                )

            # Make sure the requested value still exists.
            option = current_select.locator(
                "option"
            ).filter(
                has_text=name
            )

            # Prefer exact value selection.
            if value:
                try:
                    await current_select.select_option(
                        value=value,
                        timeout=SHORT_TIMEOUT,
                    )
                except Exception:
                    await current_select.select_option(
                        label=name,
                        timeout=SHORT_TIMEOUT,
                    )
            else:
                await current_select.select_option(
                    label=name,
                    timeout=SHORT_TIMEOUT,
                )

            await frame.page.wait_for_timeout(
                AFTER_SELECTION_DELAY
            )

            # Capture the state after selecting the country.
            text_after_selection = (
                await get_frame_text(frame)
            )

            status, reason = classify_calculator_text(
                text_after_selection
            )

            # If selection itself already produced an explicit
            # unavailable message, do not click anything else.
            if status == "UNAVAILABLE":
                return {
                    "status": status,
                    "reason": reason,
                    "text": text_after_selection,
                }

            # If no result is visible yet, try the calculate button.
            button = await locate_calculate_button(
                frame
            )

            if button is not None:
                try:
                    await button.click(
                        timeout=SHORT_TIMEOUT,
                        force=True,
                    )

                    await frame.page.wait_for_timeout(
                        AFTER_SELECTION_DELAY
                    )

                    text_after_calculation = (
                        await get_frame_text(frame)
                    )

                    status, reason = (
                        classify_calculator_text(
                            text_after_calculation
                        )
                    )

                    return {
                        "status": status,
                        "reason": reason,
                        "text": text_after_calculation,
                    }

                except Exception as exc:
                    return {
                        "status": "UNDETERMINED",
                        "reason": (
                            "calculate button failed: "
                            f"{type(exc).__name__}"
                        ),
                        "text": text_after_selection,
                    }

            return {
                "status": status,
                "reason": reason,
                "text": text_after_selection,
            }

        result = await asyncio.wait_for(
            operation(),
            timeout=DESTINATION_TIMEOUT / 1000,
        )

        elapsed = time.monotonic() - started

        result["seconds"] = round(
            elapsed,
            2,
        )

        return result

    except asyncio.TimeoutError:
        return {
            "status": "ERROR",
            "reason": "destination timeout",
            "text": "",
            "seconds": round(
                time.monotonic() - started,
                2,
            ),
        }

    except Exception as exc:
        return {
            "status": "ERROR",
            "reason": (
                f"{type(exc).__name__}: {exc}"
            ),
            "text": "",
            "seconds": round(
                time.monotonic() - started,
                2,
            ),
        }


# ============================================================================
# RESULTS FILE
# ============================================================================

def write_results(
    destinations,
    results,
    started_at,
):
    section("WRITING CALCULATOR RESULTS")

    available = [
        r for r in results
        if r["status"] == "AVAILABLE"
    ]

    unavailable = [
        r for r in results
        if r["status"] == "UNAVAILABLE"
    ]

    undetermined = [
        r for r in results
        if r["status"] == "UNDETERMINED"
    ]

    errors = [
        r for r in results
        if r["status"] == "ERROR"
    ]

    lines = []

    lines.append(
        "JP BH POŠTA CALCULATOR RESULTS"
    )
    lines.append(
        "=" * 70
    )
    lines.append(
        f"URL: {URL}"
    )
    lines.append(
        f"Started: {started_at}"
    )
    lines.append(
        f"Total destination options: {len(destinations)}"
    )
    lines.append(
        f"Tested: {len(results)}"
    )
    lines.append(
        f"AVAILABLE: {len(available)}"
    )
    lines.append(
        f"UNAVAILABLE: {len(unavailable)}"
    )
    lines.append(
        f"UNDETERMINED: {len(undetermined)}"
    )
    lines.append(
        f"ERROR: {len(errors)}"
    )
    lines.append("")

    lines.append(
        "AVAILABLE DESTINATIONS"
    )
    lines.append(
        "=" * 70
    )

    for result in available:
        lines.append(
            f"{result['name']} "
            f"[value={result['value']}] "
            f"({result['reason']})"
        )

    lines.append("")
    lines.append(
        "UNAVAILABLE DESTINATIONS"
    )
    lines.append(
        "=" * 70
    )

    for result in unavailable:
        lines.append(
            f"{result['name']} "
            f"[value={result['value']}] "
            f"({result['reason']})"
        )

    lines.append("")
    lines.append(
        "UNDETERMINED DESTINATIONS"
    )
    lines.append(
        "=" * 70
    )

    for result in undetermined:
        lines.append(
            f"{result['name']} "
            f"[value={result['value']}] "
            f"({result['reason']})"
        )

    lines.append("")
    lines.append(
        "ERRORS"
    )
    lines.append(
        "=" * 70
    )

    for result in errors:
        lines.append(
            f"{result['name']} "
            f"[value={result['value']}] "
            f"({result['reason']})"
        )

    lines.append("")
    lines.append(
        "DETAILS"
    )
    lines.append(
        "=" * 70
    )

    for result in results:
        lines.append("")
        lines.append(
            f"DESTINATION: {result['name']}"
        )
        lines.append(
            f"VALUE: {result['value']}"
        )
        lines.append(
            f"STATUS: {result['status']}"
        )
        lines.append(
            f"REASON: {result['reason']}"
        )
        lines.append(
            f"SECONDS: {result.get('seconds', '')}"
        )

        text = clean_text(
            result.get("text", "")
        )

        if text:
            lines.append(
                "CALCULATOR TEXT:"
            )
            lines.append(
                text[:5000]
            )

    save_text(
        RESULTS_FILE,
        "\n".join(lines) + "\n",
    )

    print()
    print(
        f"AVAILABLE: {len(available)}"
    )
    print(
        f"UNAVAILABLE: {len(unavailable)}"
    )
    print(
        f"UNDETERMINED: {len(undetermined)}"
    )
    print(
        f"ERROR: {len(errors)}"
    )
    print(
        f"Output file: {RESULTS_FILE}"
    )

    return {
        "available": available,
        "unavailable": unavailable,
        "undetermined": undetermined,
        "errors": errors,
    }


# ============================================================================
# MAIN
# ============================================================================

async def main():
    started_at = time.strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    section("JP BH POŠTA CALCULATOR MONITOR")

    print(f"URL: {URL}")
    print(
        f"Global timeout: {TOTAL_TIMEOUT / 1000:.0f} seconds"
    )

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-gpu",
            ],
        )

        context = await browser.new_context(
            viewport={
                "width": 1440,
                "height": 1200,
            },
            locale="hr-HR",
        )

        page = await context.new_page()

        page.set_default_timeout(
            NORMAL_TIMEOUT
        )

        page.set_default_navigation_timeout(
            NAVIGATION_TIMEOUT
        )

        calculator_frame = None

        try:
            await asyncio.wait_for(
                monitor(page, started_at),
                timeout=TOTAL_TIMEOUT / 1000,
            )

        except asyncio.TimeoutError:
            raise RuntimeError(
                f"Global monitor timeout exceeded "
                f"({TOTAL_TIMEOUT / 1000:.0f} seconds)."
            )

        except Exception as exc:
            section("MONITOR FAILED")

            print(
                f"{type(exc).__name__}: {exc}"
            )

            try:
                await build_diagnostic(
                    page,
                    calculator_frame,
                    extra=(
                        f"{type(exc).__name__}: {exc}"
                    ),
                )
            except Exception as diagnostic_exc:
                print(
                    "Diagnostic creation failed: "
                    f"{diagnostic_exc}"
                )

            raise

        finally:
            try:
                await context.close()
            except Exception:
                pass

            try:
                await browser.close()
            except Exception:
                pass


# ============================================================================
# MONITOR IMPLEMENTATION
# ============================================================================

async def monitor(page, started_at):
    calculator_frame = None

    try:
        # ------------------------------------------------------------------
        # MAIN PAGE
        # ------------------------------------------------------------------

        section("OPENING MAIN PAGE")

        response = None

        try:
            response = await page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=NAVIGATION_TIMEOUT,
            )

        except PlaywrightTimeoutError as exc:
            print(
                "WARNING: page.goto() timed out while waiting "
                "for domcontentloaded."
            )
            print(
                "The page may nevertheless have loaded. "
                "Continuing."
            )
            print(str(exc))

        if response is not None:
            try:
                print(
                    f"HTTP status: {response.status}"
                )
            except Exception:
                pass

        print(
            f"Final URL: {page.url}"
        )

        try:
            print(
                f"Page title: {await page.title()}"
            )
        except Exception:
            pass

        page_html = await safe_content(page)

        save_text(
            PAGE_FILE,
            page_html,
        )

        # Give iframe creation a short opportunity.
        await page.wait_for_timeout(500)

        # ------------------------------------------------------------------
        # IFRAME
        # ------------------------------------------------------------------

        calculator_frame = (
            await wait_for_calculator_frame(
                page,
                timeout_ms=15_000,
            )
        )

        if calculator_frame is None:
            raise RuntimeError(
                "Could not locate the BH Pošta calculator iframe."
            )

        # ------------------------------------------------------------------
        # INITIAL IFRAME DIAGNOSTICS
        # ------------------------------------------------------------------

        section("SAVING CALCULATOR IFRAME")

        await save_calculator_diagnostics(
            calculator_frame
        )

        # ------------------------------------------------------------------
        # INTERNATIONAL CALCULATOR
        # ------------------------------------------------------------------

        section("CHECKING INITIAL CALCULATOR")

        country_select = await find_country_select(
            calculator_frame
        )

        if country_select is None:
            print(
                "Country dropdown is not present. "
                "Activating Međunarodni promet."
            )

            activated = await activate_international(
                calculator_frame
            )

            if not activated:
                # Save the exact state before failing.
                await save_calculator_diagnostics(
                    calculator_frame
                )

                raise RuntimeError(
                    "Could not find or activate "
                    "Međunarodni promet."
                )

            section(
                "WAITING FOR INTERNATIONAL CALCULATOR"
            )

            country_select = (
                await wait_for_country_select(
                    calculator_frame,
                    timeout_ms=10_000,
                )
            )

        if country_select is None:
            html, text = (
                await save_calculator_diagnostics(
                    calculator_frame
                )
            )

            print()
            print(
                "Visible calculator text:"
            )
            print(text[:30000])

            raise RuntimeError(
                "International calculator activated, "
                "but no country <select> was found."
            )

        # ------------------------------------------------------------------
        # COUNTRY SELECT
        # ------------------------------------------------------------------

        section("COUNTRY DROPDOWN FOUND")

        select_id = await country_select.get_attribute(
            "id"
        )

        select_name = await country_select.get_attribute(
            "name"
        )

        print(
            f"Country select id: {select_id}"
        )
        print(
            f"Country select name: {select_name}"
        )

        destinations = (
            await extract_destination_options(
                country_select
            )
        )

        if not destinations:
            raise RuntimeError(
                "Country dropdown was found, but "
                "contained no destinations."
            )

        save_countries(destinations)

        # ------------------------------------------------------------------
        # TEST DESTINATIONS
        # ------------------------------------------------------------------

        section("TESTING DESTINATION AVAILABILITY")

        print(
            "IMPORTANT: destination presence in the "
            "dropdown is NOT treated as availability."
        )

        results = []

        total = len(destinations)

        for index, destination in enumerate(
            destinations,
            start=1,
        ):
            elapsed = time.monotonic()

            print()
            print(
                f"[{index}/{total}] "
                f"Testing: {destination['name']}"
            )

            if destination["disabled"]:
                result = {
                    "name": destination["name"],
                    "value": destination["value"],
                    "status": "UNAVAILABLE",
                    "reason": "option is disabled",
                    "text": "",
                    "seconds": 0,
                }

                print(
                    "  -> UNAVAILABLE "
                    "(disabled option)"
                )

            else:
                tested = await test_destination(
                    calculator_frame,
                    country_select,
                    destination,
                )

                result = {
                    "name": destination["name"],
                    "value": destination["value"],
                    **tested,
                }

                print(
                    f"  -> {result['status']}: "
                    f"{result['reason']} "
                    f"({result['seconds']}s)"
                )

            results.append(result)

            # Do not let an unexpectedly slow run continue forever.
            if (
                time.monotonic() - elapsed
                > DESTINATION_TIMEOUT
            ):
                print(
                    "  Destination exceeded expected "
                    "time budget."
                )

        # ------------------------------------------------------------------
        # RESULTS
        # ------------------------------------------------------------------

        summary = write_results(
            destinations,
            results,
            started_at,
        )

        # Save final calculator state too.
        await save_calculator_diagnostics(
            calculator_frame
        )

        section("SUCCESS")

        print(
            f"Raw destination options: "
            f"{len(destinations)}"
        )
        print(
            f"Available: "
            f"{len(summary['available'])}"
        )
        print(
            f"Unavailable: "
            f"{len(summary['unavailable'])}"
        )
        print(
            f"Undetermined: "
            f"{len(summary['undetermined'])}"
        )
        print(
            f"Errors: "
            f"{len(summary['errors'])}"
        )

        print()
        print(
            "Artifacts:"
        )
        print(
            f"  - {COUNTRIES_FILE}"
        )
        print(
            f"  - {RESULTS_FILE}"
        )
        print(
            f"  - {PAGE_FILE}"
        )
        print(
            f"  - {IFRAME_FILE}"
        )
        print(
            f"  - {IFRAME_TEXT_FILE}"
        )

    except Exception:
        raise


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    try:
        asyncio.run(main())

    except KeyboardInterrupt:
        print("Interrupted.")
        sys.exit(130)

    except Exception as exc:
        print()
        print("=" * 70)
        print("FATAL ERROR")
        print("=" * 70)
        print(
            f"{type(exc).__name__}: {exc}"
        )
        sys.exit(1)
