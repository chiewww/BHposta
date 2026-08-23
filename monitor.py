import asyncio
import os
import re
import sys
from pathlib import Path

from playwright.async_api import (
    async_playwright,
    TimeoutError as PlaywrightTimeoutError,
)


URL = os.getenv(
    "CALCULATOR_URL",
    "https://www.posta.ba/kalkulator-cijena/",
)

CALCULATOR_IFRAME_URL_PART = (
    "bhpwebout.posta.ba/KalkulatorCijena_WEB_app"
)

COUNTRIES_FILE = Path("countries.txt")
RESULTS_FILE = Path("calculator-results.txt")
PAGE_FILE = Path("page.html")
IFRAME_FILE = Path("iframe.html")
IFRAME_TEXT_FILE = Path("iframe.txt")
DIAGNOSTIC_FILE = Path("diagnostic.txt")
DIAGNOSTIC_HTML_FILE = Path("diagnostic.html")
DIAGNOSTIC_PNG_FILE = Path("diagnostic.png")

NAVIGATION_TIMEOUT = 30_000
DEFAULT_TIMEOUT = 5_000
FRAME_WAIT_TIMEOUT = 30_000
PER_DESTINATION_TIMEOUT = 7_000
OVERALL_TEST_TIMEOUT = 45 * 60 * 1000
BETWEEN_DESTINATIONS_MS = 150


def section(title):
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def save_text(path, text):
    try:
        path.write_text(text or "", encoding="utf-8")
        print(f"Saved {path} ({len(text or ''):,} bytes)")
    except Exception as exc:
        print(f"Could not save {path}: {exc}")


async def safe_content(page):
    try:
        return await page.content()
    except Exception:
        return ""


async def safe_screenshot(page):
    try:
        await page.screenshot(
            path=str(DIAGNOSTIC_PNG_FILE),
            full_page=True,
        )
        print(f"Saved {DIAGNOSTIC_PNG_FILE}")
    except Exception as exc:
        print(f"Could not save screenshot: {exc}")


async def frame_content(frame):
    try:
        return await frame.content()
    except Exception:
        return ""


async def find_calculator_frame(page):
    """
    Locate the BH Pošta calculator iframe.

    IMPORTANT:
    The calculator iframe can temporarily appear as about:blank.
    Therefore we repeatedly inspect all frames and prefer the known
    bhpwebout.posta.ba URL.
    """

    section("LOCATING CALCULATOR IFRAME")

    for attempt in range(1, 16):
        frames = page.frames

        print(
            f"Frame search attempt {attempt}/15. "
            f"Number of frames: {len(frames)}"
        )

        # First: URL match.
        for index, frame in enumerate(frames):
            url = frame.url or ""

            print(
                f"Checking frame {index}: {url}"
            )

            if (
                CALCULATOR_IFRAME_URL_PART.casefold()
                in url.casefold()
            ):
                print(
                    f"FOUND CALCULATOR FRAME: {index}"
                )
                print(
                    f"Calculator URL: {url}"
                )
                return frame

        # Second: known calculator controls.
        for index, frame in enumerate(frames):
            html = await frame_content(frame)

            if not html:
                continue

            markers = (
                "ddlUnObPiTez",
                "ddlMeObPiOderdiste",
                "ddlMeObPiTezine",
                "Međunarodni promet",
                "Kalkulator cijena",
            )

            if any(
                marker in html
                for marker in markers
            ):
                print(
                    f"FOUND calculator by HTML: frame {index}"
                )
                print(
                    f"Calculator URL: {frame.url}"
                )
                return frame

        if attempt < 15:
            await page.wait_for_timeout(1_000)

    return None


async def save_calculator_diagnostics(frame):
    html = await frame_content(frame)
    save_text(IFRAME_FILE, html)

    try:
        text = await frame.locator(
            "body"
        ).inner_text(timeout=DEFAULT_TIMEOUT)
    except Exception:
        text = ""

    save_text(IFRAME_TEXT_FILE, text)

    return html, text


async def activate_international(frame):
    """
    Activate the DevExpress 'Međunarodni promet' tab.

    We deliberately inspect the actual HTML rather than relying on
    an ASP.NET control ID.
    """

    section("ACTIVATING MEĐUNARODNI PROMET")

    # First, try the exact visible text.
    try:
        candidates = frame.get_by_text(
            "Međunarodni promet",
            exact=True,
        )

        count = await candidates.count()

        print(
            f"Exact text candidates: {count}"
        )

        for i in range(count):
            candidate = candidates.nth(i)

            try:
                if not await candidate.is_visible():
                    continue
            except Exception:
                continue

            print(
                "Found visible Međunarodni promet."
            )

            try:
                tag = await candidate.evaluate(
                    "(el) => el.tagName"
                )
                outer = await candidate.evaluate(
                    "(el) => el.outerHTML"
                )

                print(f"Tag: {tag}")
                print(
                    f"HTML: {outer[:1500]}"
                )
            except Exception:
                pass

            # Try direct click.
            try:
                await candidate.click(
                    timeout=DEFAULT_TIMEOUT,
                    force=True,
                )

                print(
                    "Clicked Međunarodni promet."
                )

                await frame.page.wait_for_timeout(
                    1_000
                )

                return True

            except Exception as exc:
                print(
                    f"Direct click failed: {exc}"
                )

            # Try clickable ancestors.
            for xpath in (
                "xpath=ancestor::td[1]",
                "xpath=ancestor::a[1]",
                "xpath=ancestor::div[1]",
                "xpath=parent::*",
            ):
                try:
                    parent = candidate.locator(
                        xpath
                    )

                    if await parent.count() == 0:
                        continue

                    await parent.first.click(
                        timeout=DEFAULT_TIMEOUT,
                        force=True,
                    )

                    print(
                        f"Clicked ancestor: {xpath}"
                    )

                    await frame.page.wait_for_timeout(
                        1_000
                    )

                    return True

                except Exception:
                    continue

    except Exception as exc:
        print(
            f"Exact text search failed: {exc}"
        )

    # Substring fallback.
    try:
        candidates = frame.get_by_text(
            "Međunarodni promet"
        )

        count = await candidates.count()

        print(
            f"Substring candidates: {count}"
        )

        for i in range(count):
            candidate = candidates.nth(i)

            try:
                if not await candidate.is_visible():
                    continue

                await candidate.click(
                    timeout=DEFAULT_TIMEOUT,
                    force=True,
                )

                print(
                    "Clicked international tab "
                    "using substring search."
                )

                await frame.page.wait_for_timeout(
                    1_000
                )

                return True

            except Exception:
                continue

    except Exception as exc:
        print(
            f"Substring search failed: {exc}"
        )

    # Last fallback: inspect elements whose text contains the phrase.
    try:
        locator = frame.locator(
            "span,td,a,div"
        )

        count = await locator.count()

        for i in range(count):
            element = locator.nth(i)

            try:
                if not await element.is_visible():
                    continue

                text = await element.inner_text()

                if (
                    "Međunarodni promet"
                    not in text
                ):
                    continue

                print(
                    "Found international tab "
                    "through generic element search."
                )

                await element.click(
                    timeout=DEFAULT_TIMEOUT,
                    force=True,
                )

                await frame.page.wait_for_timeout(
                    1_000
                )

                return True

            except Exception:
                continue

    except Exception as exc:
        print(
            f"Generic tab search failed: {exc}"
        )

    return False


async def find_country_select(frame):
    """
    Find the international destination selector.

    Known working ID from the successful run:

        ddlMeObPiOderdiste

    We use that ID first, then fall back to inspecting all selects.
    """

    print()
    print("LOCATING COUNTRY DROPDOWN")

    # Known selector.
    try:
        known = frame.locator(
            "#ddlMeObPiOderdiste"
        )

        if await known.count() > 0:
            try:
                if await known.first.is_visible():
                    option_count = await known.first.locator(
                        "option"
                    ).count()

                    if option_count >= 20:
                        print(
                            "FOUND known country selector:"
                            " #ddlMeObPiOderdiste"
                        )

                        return known.first
            except Exception:
                pass
    except Exception:
        pass

    selects = frame.locator("select")
    count = await selects.count()

    print(
        f"Number of select elements: {count}"
    )

    markers = (
        "Afganistan",
        "Albanija",
        "Alžir",
        "Australija",
        "Austrija",
        "Belgija",
        "Bosna i Hercegovina",
        "Hrvatska",
        "Njemačka",
        "Njemacka",
        "Sjedinjene",
        "Velika Britanija",
    )

    best = None
    best_score = 0

    for i in range(count):
        select = selects.nth(i)

        try:
            sid = await select.get_attribute(
                "id"
            )
            name = await select.get_attribute(
                "name"
            )
            text = await select.inner_text()
            option_count = await select.locator(
                "option"
            ).count()

            print(
                f"SELECT #{i}"
            )
            print(
                f"  id = {sid}"
            )
            print(
                f"  name = {name}"
            )
            print(
                f"  options = {option_count}"
            )

            score = sum(
                1
                for marker in markers
                if marker.casefold()
                in text.casefold()
            )

            if option_count >= 20:
                score += 10

            if score > best_score:
                best = select
                best_score = score

        except Exception as exc:
            print(
                f"Could not inspect select #{i}: {exc}"
            )

    if best is not None:
        print(
            "COUNTRY SELECT FOUND:"
            f" {await best.get_attribute('id')}"
        )
        return best

    return None


async def wait_for_country_select(
    frame,
    timeout_ms=15_000,
):
    deadline = (
        asyncio.get_running_loop().time()
        + timeout_ms / 1000
    )

    while (
        asyncio.get_running_loop().time()
        < deadline
    ):
        select = await find_country_select(
            frame
        )

        if select is not None:
            return select

        await frame.page.wait_for_timeout(
            500
        )

    return None


def clean_name(value):
    return re.sub(
        r"\s+",
        " ",
        value or "",
    ).strip()


async def read_destinations(select):
    section("READING DESTINATIONS")

    options = select.locator("option")
    count = await options.count()

    print(
        f"Total option elements: {count}"
    )

    destinations = []

    placeholders = {
        "odredišna zemlja",
        "odredisna zemlja",
        "izaberite",
        "odaberite",
        "select",
        "select country",
    }

    for i in range(count):
        option = options.nth(i)

        try:
            name = clean_name(
                await option.inner_text()
            )

            value = (
                await option.get_attribute(
                    "value"
                )
            )

            if not name:
                continue

            if (
                name.casefold()
                in placeholders
            ):
                continue

            destinations.append(
                {
                    "name": name,
                    "value": value or "",
                }
            )

        except Exception as exc:
            print(
                f"Could not read option {i}: {exc}"
            )

    unique = []
    seen = set()

    for destination in destinations:
        key = (
            destination["value"]
            or destination["name"]
        ).casefold()

        if key in seen:
            continue

        seen.add(key)
        unique.append(destination)

    print(
        f"Unique destinations: {len(unique)}"
    )

    return unique


def write_results(
    results,
    total,
    status="RUNNING",
):
    """
    ALWAYS write calculator-results.txt.

    This function is deliberately safe to call even when results is
    empty. That guarantees that the artifact exists from the beginning.
    """

    available = [
        r for r in results
        if r["status"] == "AVAILABLE"
    ]

    unavailable = [
        r for r in results
        if r["status"] == "UNAVAILABLE"
    ]

    unknown = [
        r for r in results
        if r["status"] == "UNKNOWN"
    ]

    lines = []

    lines.append(
        "JP BH POŠTA CALCULATOR DESTINATION TEST"
    )
    lines.append("=" * 70)
    lines.append("")
    lines.append(
        f"STATUS: {status}"
    )
    lines.append(
        f"DESTINATIONS DISCOVERED: {total}"
    )
    lines.append(
        f"DESTINATIONS TESTED: {len(results)}"
    )
    lines.append(
        f"AVAILABLE: {len(available)}"
    )
    lines.append(
        f"UNAVAILABLE: {len(unavailable)}"
    )
    lines.append(
        f"UNKNOWN: {len(unknown)}"
    )
    lines.append("")

    lines.append(
        "AVAILABLE DESTINATIONS"
    )
    lines.append("-" * 70)

    if available:
        for item in available:
            price = item.get(
                "prices",
                "",
            )

            if price:
                lines.append(
                    f"{item['name']} "
                    f"[value={item['value']}] "
                    f"| {price}"
                )
            else:
                lines.append(
                    f"{item['name']} "
                    f"[value={item['value']}]"
                )
    else:
        lines.append("None.")

    lines.append("")
    lines.append(
        "UNAVAILABLE DESTINATIONS"
    )
    lines.append("-" * 70)

    if unavailable:
        for item in unavailable:
            lines.append(
                f"{item['name']} "
                f"[value={item['value']}] "
                f"| {item['reason']}"
            )
    else:
        lines.append("None.")

    lines.append("")
    lines.append(
        "UNKNOWN / NEEDS REVIEW"
    )
    lines.append("-" * 70)

    if unknown:
        for item in unknown:
            lines.append(
                f"{item['name']} "
                f"[value={item['value']}] "
                f"| {item['reason']}"
            )
    else:
        lines.append("None.")

    save_text(
        RESULTS_FILE,
        "\n".join(lines) + "\n",
    )

    # countries.txt contains ONLY confirmed AVAILABLE destinations.
    countries = [
        item["name"]
        for item in available
    ]

    save_text(
        COUNTRIES_FILE,
        (
            "\n".join(countries) + "\n"
            if countries
            else ""
        ),
    )


def extract_prices(text):
    patterns = [
        r"\b\d+(?:[.,]\d{1,2})?\s*(?:KM|BAM)\b",
        r"\b(?:KM|BAM)\s*\d+(?:[.,]\d{1,2})?\b",
    ]

    found = []

    for pattern in patterns:
        found.extend(
            re.findall(
                pattern,
                text,
                flags=re.IGNORECASE,
            )
        )

    result = []
    seen = set()

    for value in found:
        key = value.casefold()

        if key not in seen:
            seen.add(key)
            result.append(value)

    return result


def text_has_error(text):
    lowered = text.casefold()

    markers = [
        "nije moguće",
        "nije moguce",
        "nije dostupno",
        "nije dostupna",
        "nije dostupan",
        "ne može se",
        "ne moze se",
        "ne postoji usluga",
        "usluga nije",
        "trenutno nije",
        "odredište nije",
        "odrediste nije",
        "zabranjeno",
        "nedostupno",
        "nedostupna",
        "nedostupan",
        "cannot",
        "not available",
        "unavailable",
        "not permitted",
        "not allowed",
    ]

    return any(
        marker in lowered
        for marker in markers
    )


def looks_like_result(text):
    if text_has_error(text):
        return False

    prices = extract_prices(text)

    if prices:
        return True

    lowered = text.casefold()

    markers = (
        "cijena",
        "cijene",
        "iznos",
        "price",
        "rezultat",
    )

    return any(
        marker in lowered
        for marker in markers
    )


async def get_body_text(frame):
    try:
        return await frame.locator(
            "body"
        ).inner_text(timeout=3_000)
    except Exception:
        return ""


async def choose_first_weight(frame):
    """
    Select the first international weight option.

    Known working ID:

        ddlMeObPiTezine
    """

    try:
        known = frame.locator(
            "#ddlMeObPiTezine"
        )

        if await known.count() > 0:
            option_count = await known.first.locator(
                "option"
            ).count()

            if option_count > 0:
                first = known.first.locator(
                    "option"
                ).first

                value = await first.get_attribute(
                    "value"
                )

                if value:
                    await known.first.select_option(
                        value=value
                    )
                else:
                    await known.first.select_option(
                        index=0
                    )

                await frame.page.wait_for_timeout(
                    250
                )

                return known.first

    except Exception as exc:
        print(
            f"Weight selection warning: {exc}"
        )

    return None


async def find_calculate_control(frame):
    """
    Search for the calculator's actual calculation control.
    """

    texts = (
        "Izračun",
        "Izračunaj",
        "Izracun",
        "Izracunaj",
    )

    for text in texts:
        try:
            locator = frame.get_by_text(
                text,
                exact=False,
            )

            count = await locator.count()

            for i in range(count):
                candidate = locator.nth(i)

                try:
                    if await candidate.is_visible():
                        return candidate
                except Exception:
                    continue

        except Exception:
            continue

    controls = frame.locator(
        "button, input[type='button'], "
        "input[type='submit'], a"
    )

    count = await controls.count()

    for i in range(count):
        control = controls.nth(i)

        try:
            if not await control.is_visible():
                continue

            text = clean_name(
                await control.inner_text()
            )

            value = (
                await control.get_attribute(
                    "value"
                )
            )

            title = (
                await control.get_attribute(
                    "title"
                )
            )

            combined = clean_name(
                f"{text} {value or ''} {title or ''}"
            ).casefold()

            if (
                "izrač" in combined
                or "izrac" in combined
                or "calculate" in combined
            ):
                return control

        except Exception:
            continue

    return None


async def calculate_destination(
    frame,
    country_select,
    destination,
):
    """
    Test one destination.

    Returns:
        status, reason, text
    """

    name = destination["name"]
    value = destination["value"]

    try:
        # Select destination.
        if value:
            await country_select.select_option(
                value=value
            )
        else:
            await country_select.select_option(
                label=name
            )

        await frame.page.wait_for_timeout(
            400
        )

        # Select first weight.
        await choose_first_weight(
            frame
        )

        before = await get_body_text(
            frame
        )

        calculate = await find_calculate_control(
            frame
        )

        if calculate is None:
            return (
                "UNKNOWN",
                "Calculate control not found",
                before,
            )

        try:
            await calculate.click(
                timeout=DEFAULT_TIMEOUT,
                force=True,
            )
        except Exception as exc:
            return (
                "UNKNOWN",
                f"Calculate click failed: {exc}",
                before,
            )

        deadline = (
            asyncio.get_running_loop().time()
            + PER_DESTINATION_TIMEOUT / 1000
        )

        last_text = before

        while (
            asyncio.get_running_loop().time()
            < deadline
        ):
            await frame.page.wait_for_timeout(
                400
            )

            last_text = await get_body_text(
                frame
            )

            if text_has_error(
                last_text
            ):
                return (
                    "UNAVAILABLE",
                    "Calculator displayed an unavailable/error message",
                    last_text,
                )

            if looks_like_result(
                last_text
            ):
                return (
                    "AVAILABLE",
                    "Calculator produced a result",
                    last_text,
                )

        return (
            "UNKNOWN",
            "No definitive result detected",
            last_text,
        )

    except Exception as exc:
        return (
            "UNKNOWN",
            f"Exception: {exc}",
            "",
        )


async def build_diagnostic(
    page,
    frame,
    error,
):
    section("CREATING DIAGNOSTICS")

    save_text(
        DIAGNOSTIC_HTML_FILE,
        await safe_content(page),
    )

    parts = [
        "JP BH POŠTA CALCULATOR DIAGNOSTIC",
        "",
        f"URL: {URL}",
        f"PAGE URL: {page.url}",
        f"FRAME COUNT: {len(page.frames)}",
        "",
    ]

    for i, current_frame in enumerate(
        page.frames
    ):
        parts.append(
            f"FRAME {i}: {current_frame.url}"
        )

    if frame is not None:
        html = await frame_content(
            frame
        )

        parts.extend(
            [
                "",
                f"CALCULATOR HTML LENGTH: {len(html)}",
                "",
                "CALCULATOR TEXT:",
            ]
        )

        try:
            text = await frame.locator(
                "body"
            ).inner_text(timeout=3_000)
        except Exception:
            text = ""

        parts.append(
            text[:30_000]
        )

        parts.extend(
            [
                "",
                "CALCULATOR HTML:",
                html[:50_000],
            ]
        )

    parts.extend(
        [
            "",
            "ERROR:",
            f"{type(error).__name__}: {error}",
        ]
    )

    save_text(
        DIAGNOSTIC_FILE,
        "\n".join(parts),
    )

    await safe_screenshot(page)


async def main():
    section(
        "JP BH POŠTA CALCULATOR MONITOR"
    )

    print(f"URL: {URL}")

    # IMPORTANT:
    # Create the two principal output files immediately.
    # Therefore they exist even if the calculator subsequently fails.
    save_text(
        RESULTS_FILE,
        "JP BH POŠTA CALCULATOR DESTINATION TEST\n"
        + "=" * 70
        + "\n"
        + "STATUS: STARTING\n"
        + "No destinations tested yet.\n",
    )

    save_text(
        COUNTRIES_FILE,
        "",
    )

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
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
            DEFAULT_TIMEOUT
        )

        page.set_default_navigation_timeout(
            NAVIGATION_TIMEOUT
        )

        frame = None

        try:
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
                    "WARNING: page.goto timed out."
                )
                print(
                    "Continuing because page may "
                    "already be usable."
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

            save_text(
                PAGE_FILE,
                await safe_content(page),
            )

            await page.wait_for_timeout(
                2_000
            )

            frame = await find_calculator_frame(
                page
            )

            if frame is None:
                raise RuntimeError(
                    "Could not locate BH Pošta "
                    "calculator iframe."
                )

            section(
                "SAVING CALCULATOR IFRAME"
            )

            await save_calculator_diagnostics(
                frame
            )

            section(
                "CHECKING INITIAL CALCULATOR"
            )

            country_select = (
                await find_country_select(
                    frame
                )
            )

            if country_select is None:
                print(
                    "International country selector "
                    "not present."
                )

                activated = (
                    await activate_international(
                        frame
                    )
                )

                if not activated:
                    raise RuntimeError(
                        "Could not activate "
                        "Međunarodni promet."
                    )

                section(
                    "WAITING FOR INTERNATIONAL CALCULATOR"
                )

                country_select = (
                    await wait_for_country_select(
                        frame,
                        FRAME_WAIT_TIMEOUT,
                    )
                )

            if country_select is None:
                raise RuntimeError(
                    "International calculator activated "
                    "but country selector was not found."
                )

            section(
                "COUNTRY DROPDOWN FOUND"
            )

            print(
                "Country select ID:",
                await country_select.get_attribute(
                    "id"
                ),
            )

            print(
                "Country select name:",
                await country_select.get_attribute(
                    "name"
                ),
            )

            destinations = (
                await read_destinations(
                    country_select
                )
            )

            if len(destinations) < 20:
                raise RuntimeError(
                    "Destination list is unexpectedly "
                    f"small: {len(destinations)}"
                )

            # This is important: write a valid result file BEFORE
            # attempting the first destination.
            write_results(
                [],
                len(destinations),
                status="DESTINATIONS_DISCOVERED",
            )

            section(
                "TESTING DESTINATIONS"
            )

            print(
                f"Testing {len(destinations)} "
                "destinations."
            )

            results = []

            overall_deadline = (
                asyncio.get_running_loop().time()
                + OVERALL_TEST_TIMEOUT / 1000
            )

            timed_out = False

            for index, destination in enumerate(
                destinations,
                1,
            ):
                if (
                    asyncio.get_running_loop().time()
                    >= overall_deadline
                ):
                    timed_out = True

                    print(
                        "Overall destination test "
                        "timeout reached."
                    )

                    break

                print()
                print(
                    f"[{index:03d}/{len(destinations):03d}] "
                    f"{destination['name']}"
                )

                status, reason, result_text = (
                    await calculate_destination(
                        frame,
                        country_select,
                        destination,
                    )
                )

                prices = extract_prices(
                    result_text
                )

                result = {
                    "name": destination["name"],
                    "value": destination["value"],
                    "status": status,
                    "reason": reason,
                    "prices": ", ".join(prices),
                }

                results.append(result)

                print(
                    f"RESULT: {status}"
                )

                if prices:
                    print(
                        "PRICE:",
                        ", ".join(prices),
                    )

                print(
                    "REASON:",
                    reason,
                )

                # CRITICAL:
                # Save after every destination so the artifact contains
                # partial results even if a later operation fails.
                write_results(
                    results,
                    len(destinations),
                    status="RUNNING",
                )

                await page.wait_for_timeout(
                    BETWEEN_DESTINATIONS_MS
                )

            if timed_out:
                final_status = (
                    "TIMED_OUT_PARTIAL"
                )
            else:
                final_status = "COMPLETE"

            write_results(
                results,
                len(destinations),
                status=final_status,
            )

            section("SUCCESS")

            print(
                "Destination testing completed."
            )

            print(
                f"Destinations discovered: "
                f"{len(destinations)}"
            )

            print(
                f"Destinations tested: "
                f"{len(results)}"
            )

            print(
                f"Results file: {RESULTS_FILE}"
            )

            print(
                f"Countries file: {COUNTRIES_FILE}"
            )

        except Exception as exc:
            section("MONITOR FAILED")

            print(
                f"{type(exc).__name__}: {exc}"
            )

            # Even on failure, update calculator-results.txt.
            # This guarantees that the file reflects the failure.
            try:
                existing = ""

                if RESULTS_FILE.exists():
                    existing = RESULTS_FILE.read_text(
                        encoding="utf-8"
                    )

                failure_lines = [
                    "",
                    "=" * 70,
                    "MONITOR FAILURE",
                    "=" * 70,
                    f"{type(exc).__name__}: {exc}",
                    "",
                ]

                save_text(
                    RESULTS_FILE,
                    existing
                    + "\n".join(failure_lines),
                )

            except Exception as result_error:
                print(
                    "Could not update results file:",
                    result_error,
                )

            try:
                await build_diagnostic(
                    page,
                    frame,
                    exc,
                )
            except Exception as diagnostic_error:
                print(
                    "Could not create diagnostics:",
                    diagnostic_error,
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


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Interrupted.")
        sys.exit(130)
