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

# Maximum time spent testing destinations.
# This prevents a broken calculator from making GitHub Actions run forever.
DESTINATION_TEST_TIMEOUT = 45 * 60 * 1000

# Time allowed for one destination calculation.
PER_DESTINATION_TIMEOUT = 7_000

# Small pause between calculator operations.
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
    section("LOCATING CALCULATOR IFRAME")

    frames = page.frames
    print(f"Number of frames: {len(frames)}")

    for index, frame in enumerate(frames):
        url = frame.url or ""
        print(f"Checking frame {index}: {url}")

        if CALCULATOR_IFRAME_URL_PART.lower() in url.lower():
            print(f"FOUND CALCULATOR FRAME: {index}")
            print(f"Calculator URL: {url}")
            return frame

    print("URL match not found. Inspecting frame HTML...")

    for index, frame in enumerate(frames):
        html = await frame_content(frame)

        if not html:
            continue

        markers = (
            "ddlUnObPiTez",
            "ddlMeObPiOderdiste",
            "Međunarodni promet",
            "Kalkulator cijena",
        )

        if any(marker in html for marker in markers):
            print(f"FOUND calculator by HTML: frame {index}")
            print(f"Calculator URL: {frame.url}")
            return frame

    return None


async def save_calculator_diagnostics(frame):
    html = await frame_content(frame)
    save_text(IFRAME_FILE, html)

    try:
        text = await frame.locator("body").inner_text(
            timeout=DEFAULT_TIMEOUT
        )
    except Exception:
        text = ""

    save_text(IFRAME_TEXT_FILE, text)

    return html, text


async def activate_international(frame):
    section("ACTIVATING MEĐUNARODNI PROMET")

    try:
        candidates = frame.get_by_text(
            "Međunarodni promet",
            exact=True,
        )

        count = await candidates.count()
        print(f"Exact text candidates: {count}")

        for i in range(count):
            candidate = candidates.nth(i)

            try:
                if not await candidate.is_visible():
                    continue
            except Exception:
                continue

            try:
                print("Found visible Međunarodni promet.")

                try:
                    print(
                        "Tag:",
                        await candidate.evaluate(
                            "(el) => el.tagName"
                        ),
                    )
                    print(
                        "HTML:",
                        (
                            await candidate.evaluate(
                                "(el) => el.outerHTML"
                            )
                        )[:1000],
                    )
                except Exception:
                    pass

                try:
                    await candidate.click(
                        timeout=DEFAULT_TIMEOUT,
                        force=True,
                    )
                    print("Clicked international tab.")
                    await frame.page.wait_for_timeout(800)
                    return True
                except Exception as exc:
                    print(
                        f"Direct click failed: {exc}"
                    )

                for xpath in (
                    "xpath=ancestor::td[1]",
                    "xpath=ancestor::a[1]",
                    "xpath=ancestor::div[1]",
                ):
                    try:
                        parent = candidate.locator(xpath)

                        if await parent.count():
                            await parent.first.click(
                                timeout=DEFAULT_TIMEOUT,
                                force=True,
                            )
                            print(
                                "Clicked clickable ancestor."
                            )
                            await frame.page.wait_for_timeout(800)
                            return True
                    except Exception:
                        pass

            except Exception as exc:
                print(
                    f"Error with candidate {i}: {exc}"
                )

        # Fallback substring search.
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

                await frame.page.wait_for_timeout(800)
                return True

            except Exception:
                continue

    except Exception as exc:
        print(
            f"Could not activate international calculator: {exc}"
        )

    return False


async def find_country_select(frame):
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
        "Njemacka",
        "Njemačka",
        "SAD",
        "Sjedinjene",
        "Velika Britanija",
    )

    best = None
    best_score = 0

    for i in range(count):
        select = selects.nth(i)

        try:
            sid = await select.get_attribute("id")
            name = await select.get_attribute("name")
            text = await select.inner_text()
            option_count = await select.locator(
                "option"
            ).count()

            print(
                f"SELECT #{i}: id={sid}, "
                f"name={name}, "
                f"options={option_count}"
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
                f"Error inspecting select #{i}: {exc}"
            )

    if best is not None:
        sid = await best.get_attribute("id")
        print(
            f"COUNTRY SELECT FOUND: {sid}"
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
        select = await find_country_select(frame)

        if select is not None:
            return select

        await frame.page.wait_for_timeout(400)

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
        f"Destination option count: {count}"
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
                await option.get_attribute("value")
            )

            if not name:
                continue

            if name.casefold() in placeholders:
                continue

            destinations.append(
                {
                    "name": name,
                    "value": value or "",
                }
            )

        except Exception as exc:
            print(
                f"Could not read destination {i}: "
                f"{exc}"
            )

    # Deduplicate by value where possible.
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


async def discover_controls(frame):
    """
    Discover the international calculator controls.

    This intentionally does not assume that the site uses a particular
    ASP.NET control ID for the calculate button.
    """

    section("DISCOVERING CALCULATOR CONTROLS")

    selects = frame.locator("select")
    select_count = await selects.count()

    for i in range(select_count):
        select = selects.nth(i)

        try:
            sid = await select.get_attribute("id")
            name = await select.get_attribute("name")
            option_count = await select.locator(
                "option"
            ).count()

            print(
                f"select[{i}] "
                f"id={sid} "
                f"name={name} "
                f"options={option_count}"
            )
        except Exception:
            pass

    inputs = frame.locator("input")
    input_count = await inputs.count()

    print(
        f"Input count: {input_count}"
    )

    for i in range(input_count):
        inp = inputs.nth(i)

        try:
            iid = await inp.get_attribute("id")
            name = await inp.get_attribute("name")
            typ = await inp.get_attribute("type")
            value = await inp.get_attribute("value")
            title = await inp.get_attribute("title")

            print(
                f"input[{i}] "
                f"id={iid} "
                f"name={name} "
                f"type={typ} "
                f"value={value} "
                f"title={title}"
            )
        except Exception:
            pass

    buttons = frame.locator(
        "button, input[type='button'], "
        "input[type='submit'], a"
    )

    button_count = await buttons.count()

    print(
        f"Button/link count: {button_count}"
    )

    for i in range(min(button_count, 100)):
        button = buttons.nth(i)

        try:
            if not await button.is_visible():
                continue

            text = clean_name(
                await button.inner_text()
            )

            value = (
                await button.get_attribute("value")
            )
            bid = (
                await button.get_attribute("id")
            )

            combined = clean_name(
                f"{text} {value or ''}"
            )

            if (
                "izrač" in combined.casefold()
                or "izrac" in combined.casefold()
                or "calculate" in combined.casefold()
            ):
                print(
                    f"CALCULATE CANDIDATE: "
                    f"id={bid}, "
                    f"text={combined}"
                )

        except Exception:
            pass


async def find_calculate_control(frame):
    """
    Locate the actual calculation control.

    Returns a locator or None.
    """

    # Most specific text first.
    text_candidates = [
        "Izračun",
        "Izračunaj",
        "Izracun",
        "Izracunaj",
    ]

    for text in text_candidates:
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
                    pass

        except Exception:
            pass

    # Search buttons/inputs by value/title/alt.
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
                await control.get_attribute("value")
            )
            title = (
                await control.get_attribute("title")
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
            pass

    return None


async def choose_first_weight(frame):
    """
    Select the first international weight band if needed.
    """

    selects = frame.locator("select")
    count = await selects.count()

    for i in range(count):
        select = selects.nth(i)

        try:
            sid = await select.get_attribute("id")
            options = select.locator("option")
            option_count = await options.count()

            if (
                sid == "ddlMeObPiTezine"
                or option_count == 7
            ):
                values = []

                for j in range(option_count):
                    option = options.nth(j)

                    values.append(
                        {
                            "value": (
                                await option.get_attribute(
                                    "value"
                                )
                            ),
                            "text": clean_name(
                                await option.inner_text()
                            ),
                        }
                    )

                if values:
                    first = values[0]

                    await select.select_option(
                        value=first["value"]
                    )

                    await frame.page.wait_for_timeout(
                        250
                    )

                    print(
                        "Weight selected:",
                        first["text"],
                    )

                    return select

        except Exception:
            continue

    return None


def text_has_error(text):
    lowered = text.casefold()

    error_markers = [
        "nije moguće",
        "nije moguce",
        "nije dozvoljeno",
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
        for marker in error_markers
    )


def extract_prices(text):
    """
    Find likely KM/BAM price values in calculator output.

    We intentionally keep this permissive because the site may format
    prices differently.
    """

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

    # Deduplicate.
    result = []
    seen = set()

    for value in found:
        key = value.casefold()

        if key not in seen:
            seen.add(key)
            result.append(value)

    return result


def looks_like_calculation_result(text):
    """
    Determine whether the page contains an actual result.

    We don't require a price in every case because the calculator may
    display a numeric result without the KM/BAM suffix.
    """

    if text_has_error(text):
        return False

    prices = extract_prices(text)

    if prices:
        return True

    lowered = text.casefold()

    result_markers = [
        "cijena",
        "cijene",
        "iznos",
        "price",
        "rezultat",
    ]

    return any(
        marker in lowered
        for marker in result_markers
    )


async def get_body_text(frame):
    try:
        return await frame.locator(
            "body"
        ).inner_text(timeout=3000)
    except Exception:
        return ""


async def calculate_destination(
    frame,
    country_select,
    destination,
):
    """
    Test one destination.

    Returns:
        AVAILABLE
        UNAVAILABLE
        UNKNOWN
    """

    name = destination["name"]
    value = destination["value"]

    try:
        # Select the destination.
        if value:
            await country_select.select_option(
                value=value
            )
        else:
            await country_select.select_option(
                label=name
            )

        # Give the site's AJAX/DevExpress code a chance to react.
        await frame.page.wait_for_timeout(300)

        # Make sure a valid international weight exists.
        await choose_first_weight(frame)

        before = await get_body_text(frame)

        calculate = await find_calculate_control(
            frame
        )

        if calculate is None:
            return (
                "UNKNOWN",
                "Calculate control not found",
                before,
            )

        # Click the calculator.
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

        # Wait briefly for AJAX.
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
                350
            )

            last_text = await get_body_text(
                frame
            )

            if text_has_error(last_text):
                return (
                    "UNAVAILABLE",
                    "Calculator displayed an unavailable/error message",
                    last_text,
                )

            if looks_like_calculation_result(
                last_text
            ):
                return (
                    "AVAILABLE",
                    "Calculator produced a result",
                    last_text,
                )

        # No positive result after timeout.
        return (
            "UNKNOWN",
            "No definitive calculator result detected",
            last_text,
        )

    except Exception as exc:
        return (
            "UNKNOWN",
            f"Exception while testing destination: {exc}",
            "",
        )


def write_results(
    results,
    total,
    timed_out=False,
):
    section("WRITING CALCULATOR RESULTS")

    available = [
        item
        for item in results
        if item["status"] == "AVAILABLE"
    ]

    unavailable = [
        item
        for item in results
        if item["status"] == "UNAVAILABLE"
    ]

    unknown = [
        item
        for item in results
        if item["status"] == "UNKNOWN"
    ]

    lines = []

    lines.append(
        "JP BH POŠTA CALCULATOR DESTINATION TEST"
    )
    lines.append("=" * 70)
    lines.append("")
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
    lines.append(
        f"TIMED OUT: {'YES' if timed_out else 'NO'}"
    )
    lines.append("")

    lines.append("AVAILABLE DESTINATIONS")
    lines.append("-" * 70)

    for item in available:
        prices = item.get("prices", "")
        suffix = (
            f" | {prices}"
            if prices
            else ""
        )

        lines.append(
            f"{item['name']} "
            f"[value={item['value']}]"
            f"{suffix}"
        )

    lines.append("")
    lines.append("UNAVAILABLE DESTINATIONS")
    lines.append("-" * 70)

    if unavailable:
        for item in unavailable:
            lines.append(
                f"{item['name']} "
                f"[value={item['value']}] "
                f"| {item['reason']}"
            )
    else:
        lines.append(
            "None definitively identified."
        )

    lines.append("")
    lines.append("UNKNOWN / NEEDS REVIEW")
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

    # Only genuinely AVAILABLE destinations go into countries.txt.
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

    print(
        f"AVAILABLE: {len(available)}"
    )
    print(
        f"UNAVAILABLE: {len(unavailable)}"
    )
    print(
        f"UNKNOWN: {len(unknown)}"
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
        html = await frame_content(frame)

        parts.extend(
            [
                "",
                f"CALCULATOR HTML LENGTH: {len(html)}",
                "",
                "CALCULATOR HTML:",
                html[:50000],
                "",
            ]
        )

        try:
            text = await frame.locator(
                "body"
            ).inner_text(timeout=3000)
        except Exception:
            text = ""

        parts.extend(
            [
                "CALCULATOR TEXT:",
                text[:30000],
                "",
            ]
        )

    parts.extend(
        [
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
    section("JP BH POŠTA CALCULATOR MONITOR")
    print(f"URL: {URL}")

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
                    "Continuing because the page may "
                    "already be usable."
                )
                print(str(exc))

            if response is not None:
                print(
                    f"HTTP status: {response.status}"
                )

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
                1200
            )

            frame = await find_calculator_frame(
                page
            )

            if frame is None:
                print(
                    "Calculator frame not found "
                    "immediately. Waiting..."
                )

                try:
                    await page.wait_for_selector(
                        "iframe",
                        timeout=5000,
                    )
                except Exception:
                    pass

                frame = await find_calculator_frame(
                    page
                )

            if frame is None:
                raise RuntimeError(
                    "Could not locate BH Pošta "
                    "calculator iframe."
                )

            section("SAVING CALCULATOR IFRAME")

            await save_calculator_diagnostics(
                frame
            )

            section("CHECKING INITIAL CALCULATOR")

            country_select = (
                await find_country_select(frame)
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
                        15_000,
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
                    "Suspiciously small destination "
                    f"list: {len(destinations)}"
                )

            await discover_controls(frame)

            section(
                "TESTING DESTINATIONS"
            )

            print(
                f"Testing {len(destinations)} "
                "destinations."
            )
            print(
                "This tests the calculator itself; "
                "it does not assume every <option> "
                "is available."
            )

            results = []

            deadline = (
                asyncio.get_running_loop().time()
                + DESTINATION_TEST_TIMEOUT / 1000
            )

            timed_out = False

            for index, destination in enumerate(
                destinations,
                1,
            ):
                if (
                    asyncio.get_running_loop().time()
                    >= deadline
                ):
                    timed_out = True

                    print(
                        "OVERALL DESTINATION TEST "
                        "TIMEOUT REACHED."
                    )

                    break

                print(
                    f"[{index:03d}/{len(destinations):03d}] "
                    f"Testing {destination['name']}..."
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
                    f"    RESULT: {status}"
                )

                if prices:
                    print(
                        f"    PRICE: "
                        f"{', '.join(prices)}"
                    )

                print(
                    f"    REASON: {reason}"
                )

                await page.wait_for_timeout(
                    BETWEEN_DESTINATIONS_MS
                )

                # Update the results file continuously.
                # This means an Action timeout/crash still leaves
                # partial results in the artifact.
                write_results(
                    results,
                    len(destinations),
                    timed_out=False,
                )

            if timed_out:
                print(
                    "WARNING: destination testing "
                    "ended because of overall timeout."
                )

            # Final write.
            write_results(
                results,
                len(destinations),
                timed_out=timed_out,
            )

            section("SUCCESS")

            print(
                "Calculator destination testing completed."
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

            if timed_out:
                print(
                    "WARNING: not every destination "
                    "was tested."
                )

        except Exception as exc:
            section("MONITOR FAILED")

            print(
                f"{type(exc).__name__}: {exc}"
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
