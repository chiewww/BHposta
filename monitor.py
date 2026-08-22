import asyncio
import os
import re
from pathlib import Path
from urllib.parse import urljoin

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError


# ============================================================
# CONFIGURATION
# ============================================================

URL = os.environ.get(
    "CALCULATOR_URL",
    "https://www.posta.ba/kalkulator-cijena/",
).strip()

CALCULATOR_FRAME_HOST = "bhpwebout.posta.ba"
CALCULATOR_FRAME_PATH = "/KalkulatorCijena_WEB_app/Bos/Default.aspx"

ERROR_MESSAGE = "Prijem pošiljaka se trenutno ne vrši za odabranu državu"

COUNTRIES_FILE = Path("countries.txt")

PAGE_HTML = Path("page.html")
IFRAME_HTML = Path("iframe.html")
DIAGNOSTIC_TXT = Path("diagnostic.txt")
DIAGNOSTIC_HTML = Path("diagnostic.html")
SCREENSHOT = Path("diagnostic.png")

TIMEOUT = 30_000


# ============================================================
# OUTPUT HELPERS
# ============================================================

diagnostic_lines = []


def section(title):
    line = "=" * 70
    print()
    print(line)
    print(title)
    print(line)

    diagnostic_lines.append("")
    diagnostic_lines.append(line)
    diagnostic_lines.append(title)
    diagnostic_lines.append(line)


def log(message):
    print(message)
    diagnostic_lines.append(str(message))


def save_diagnostic():
    DIAGNOSTIC_TXT.write_text(
        "\n".join(diagnostic_lines),
        encoding="utf-8",
    )


def normalize_text(text):
    if not text:
        return ""

    return re.sub(r"\s+", " ", text).strip()


# ============================================================
# FRAME DETECTION
# ============================================================

def is_calculator_frame(frame):
    """
    The real calculator is hosted on:

    https://bhpwebout.posta.ba/
        KalkulatorCijena_WEB_app/Bos/Default.aspx

    Do NOT identify the frame merely by searching for text such
    as "Kalkulator". The main page also contains that text.
    """

    frame_url = (frame.url or "").strip().lower()

    return (
        CALCULATOR_FRAME_HOST.lower() in frame_url
        and CALCULATOR_FRAME_PATH.lower() in frame_url
    )


async def find_calculator_frame(page):
    section("LOCATING CALCULATOR IFRAME")

    frames = page.frames

    log(f"Number of frames: {len(frames)}")

    for index, frame in enumerate(frames):
        frame_url = frame.url or ""

        log("")
        log(f"Checking frame {index}: {frame_url}")

        if is_calculator_frame(frame):
            log(f"FOUND CALCULATOR FRAME: {index}")
            log(f"Calculator URL: {frame_url}")
            return frame

    log("")
    log("Calculator frame was not found.")

    log("")
    log("All frame URLs:")

    for index, frame in enumerate(frames):
        log(f"  Frame {index}: {frame.url}")

    return None


# ============================================================
# SAVE FRAME INFORMATION
# ============================================================

async def save_frame(frame):
    section("SAVING CALCULATOR IFRAME")

    try:
        html = await frame.content()

        IFRAME_HTML.write_text(
            html,
            encoding="utf-8",
        )

        log(f"Saved: {IFRAME_HTML} ({len(html):,} bytes)")

        try:
            text = normalize_text(await frame.locator("body").inner_text())

            Path("iframe.txt").write_text(
                text,
                encoding="utf-8",
            )

            log(f"Saved: iframe.txt ({len(text):,} bytes)")

        except Exception as exc:
            log(f"Could not save iframe text: {exc}")

        return html

    except Exception as exc:
        log(f"Could not save calculator iframe: {exc}")
        return ""


# ============================================================
# DEBUG HTML
# ============================================================

async def dump_controls(frame):
    section("CALCULATOR CONTROL DIAGNOSTICS")

    selectors = [
        "#ddlMeDoOdrediste",
        "#chbMeDoAvionski",
        "#tbxMeDoAvioTezina",
        "#btnMeDoIzracunaj",
        "#ddlUnObPiTez",
        "#btnUnObPiIzracunaj",
        "#ImageButton4",
        "input[type='submit']",
        "select",
        "input",
        "button",
    ]

    for selector in selectors:
        try:
            count = await frame.locator(selector).count()
            log(f"{selector:40} -> {count}")
        except Exception as exc:
            log(f"{selector:40} -> ERROR: {exc}")

    log("")

    try:
        selects = frame.locator("select")
        select_count = await selects.count()

        log(f"SELECT elements: {select_count}")

        for i in range(select_count):
            element = selects.nth(i)

            log("")
            log(f"SELECT #{i}")

            try:
                log(f"  id   = {await element.get_attribute('id')}")
                log(f"  name = {await element.get_attribute('name')}")

                options = element.locator("option")
                option_count = await options.count()

                log(f"  options = {option_count}")

                for j in range(option_count):
                    option = options.nth(j)

                    value = await option.get_attribute("value")
                    text = normalize_text(await option.inner_text())

                    log(
                        f"    [{j}] value={value!r} text={text!r}"
                    )

            except Exception as exc:
                log(f"  ERROR: {exc}")

    except Exception as exc:
        log(f"Could not inspect select elements: {exc}")


# ============================================================
# INTERNATIONAL TAB DETECTION
# ============================================================

async def inspect_possible_tabs(frame):
    section("INSPECTING TAB CONTROLS")

    candidates = []

    # Text-based candidates.
    try:
        all_elements = frame.locator("text=Međunarodni promet")
        count = await all_elements.count()

        log(f"text=Međunarodni promet -> {count}")

        for i in range(count):
            element = all_elements.nth(i)

            try:
                tag = await element.evaluate(
                    "(el) => el.tagName"
                )

                outer = await element.evaluate(
                    "(el) => el.outerHTML"
                )

                candidates.append(element)

                log("")
                log(f"TEXT CANDIDATE #{i}")
                log(f"  tag: {tag}")
                log(f"  html: {outer[:2000]}")

            except Exception as exc:
                log(f"Could not inspect candidate #{i}: {exc}")

    except Exception as exc:
        log(f"Text search failed: {exc}")

    # Search HTML directly.
    try:
        html = await frame.content()

        matches = list(
            re.finditer(
                r"Međunarodni\s+promet",
                html,
                flags=re.IGNORECASE,
            )
        )

        log("")
        log(f"Raw HTML occurrences of 'Međunarodni promet': {len(matches)}")

        for i, match in enumerate(matches[:20]):
            start = max(0, match.start() - 1000)
            end = min(len(html), match.end() + 1500)

            snippet = html[start:end]

            log("")
            log(f"RAW HTML MATCH #{i}")
            log(snippet)

    except Exception as exc:
        log(f"Could not inspect raw HTML: {exc}")

    return candidates


async def click_international_tab(frame):
    section("ACTIVATING MEĐUNARODNI PROMET")

    # First inspect the page so we know exactly what markup exists.
    await inspect_possible_tabs(frame)

    # --------------------------------------------------------
    # Strategy 1:
    # Search links, spans, divs, labels and table cells
    # containing the exact visible text.
    # --------------------------------------------------------

    selectors = [
        "a",
        "span",
        "div",
        "td",
        "label",
        "li",
        "img",
        "input",
    ]

    for selector in selectors:

        try:
            elements = frame.locator(selector)

            count = await elements.count()

            for i in range(count):
                element = elements.nth(i)

                try:
                    text = normalize_text(
                        await element.inner_text(
                            timeout=1000
                        )
                    )

                except Exception:
                    text = ""

                if "Međunarodni promet" not in text:
                    continue

                log("")
                log(
                    f"Potential tab found: {selector} #{i}"
                )
                log(f"Visible text: {text[:500]}")

                try:
                    html = await element.evaluate(
                        "(el) => el.outerHTML"
                    )

                    log(f"HTML: {html[:3000]}")

                except Exception:
                    pass

                try:
                    await element.click(
                        timeout=5000,
                        force=True,
                    )

                    log(
                        f"Clicked potential international tab: "
                        f"{selector} #{i}"
                    )

                    await frame.wait_for_timeout(1500)

                    if await international_controls_exist(frame):
                        log(
                            "International controls appeared."
                        )
                        return True

                except Exception as exc:
                    log(
                        f"Click failed for "
                        f"{selector} #{i}: {exc}"
                    )

    # --------------------------------------------------------
    # Strategy 2:
    # Search every element whose text contains the phrase.
    # --------------------------------------------------------

    try:
        elements = frame.locator(
            "xpath=//*[contains(normalize-space(.), "
            "'Međunarodni promet')]"
        )

        count = await elements.count()

        log("")
        log(
            f"XPath international candidates: {count}"
        )

        for i in range(count):
            element = elements.nth(i)

            try:
                tag = await element.evaluate(
                    "(el) => el.tagName"
                )

                html = await element.evaluate(
                    "(el) => el.outerHTML"
                )

                log("")
                log(f"XPath candidate #{i}")
                log(f"Tag: {tag}")
                log(f"HTML: {html[:3000]}")

                await element.click(
                    timeout=5000,
                    force=True,
                )

                await frame.wait_for_timeout(1500)

                if await international_controls_exist(frame):
                    log(
                        "International controls appeared "
                        "after XPath click."
                    )
                    return True

            except Exception as exc:
                log(
                    f"XPath candidate #{i} failed: {exc}"
                )

    except Exception as exc:
        log(f"XPath search failed: {exc}")

    # --------------------------------------------------------
    # Strategy 3:
    # Look for ASP.NET / DevExpress tab controls.
    #
    # The diagnostic HTML showed:
    # ASPxTabControl1
    #
    # Therefore inspect elements around that identifier.
    # --------------------------------------------------------

    try:
        html = await frame.content()

        for needle in [
            "ASPxTabControl1",
            "ASPxTabControl",
            "TabControl",
            "International",
            "Međunarodni",
        ]:

            positions = [
                m.start()
                for m in re.finditer(
                    re.escape(needle),
                    html,
                    flags=re.IGNORECASE,
                )
            ]

            if positions:
                log("")
                log(
                    f"HTML occurrences of {needle!r}: "
                    f"{len(positions)}"
                )

                for pos in positions[:10]:
                    start = max(0, pos - 1500)
                    end = min(
                        len(html),
                        pos + 3000,
                    )

                    log(html[start:end])

    except Exception as exc:
        log(
            f"Could not inspect DevExpress markup: {exc}"
        )

    return False


# ============================================================
# INTERNATIONAL CONTROL DETECTION
# ============================================================

async def international_controls_exist(frame):
    """
    The international destination dropdown is expected to be:

        #ddlMeDoOdrediste
    """

    try:
        return (
            await frame.locator(
                "#ddlMeDoOdrediste"
            ).count()
            > 0
        )

    except Exception:
        return False


# ============================================================
# COUNTRY EXTRACTION
# ============================================================

async def extract_countries(frame):
    section("EXTRACTING DESTINATION COUNTRIES")

    selector = "#ddlMeDoOdrediste"

    dropdown = frame.locator(selector)

    count = await dropdown.count()

    log(
        f"{selector} count: {count}"
    )

    if count == 0:
        raise RuntimeError(
            "International destination dropdown "
            "#ddlMeDoOdrediste was not found."
        )

    option_locator = dropdown.locator("option")

    option_count = await option_locator.count()

    log(
        f"Number of country options: {option_count}"
    )

    countries = []

    for i in range(option_count):
        option = option_locator.nth(i)

        value = await option.get_attribute("value")
        text = normalize_text(
            await option.inner_text()
        )

        if not text:
            continue

        countries.append(
            {
                "index": i,
                "value": value or "",
                "name": text,
            }
        )

        log(
            f"[{i:03}] value={value!r} name={text}"
        )

    if not countries:
        raise RuntimeError(
            "Country dropdown exists but contains "
            "no options."
        )

    return countries


# ============================================================
# SELECT POSTCARD
# ============================================================

async def select_postcard(frame):
    section("SELECTING DOPISNICA / POSTCARD")

    # The diagnostic showed:
    #
    # ImageButton4
    # title="Dopisnica"
    #
    # This is the calculator's postcard icon.

    selectors = [
        "#ImageButton4",
        "input[title='Dopisnica']",
        "img[title='Dopisnica']",
        "[title='Dopisnica']",
    ]

    for selector in selectors:

        try:
            locator = frame.locator(selector)

            count = await locator.count()

            log(
                f"{selector:35} -> {count}"
            )

            if count == 0:
                continue

            element = locator.first

            try:
                await element.click(
                    timeout=5000,
                    force=True,
                )

                await frame.wait_for_timeout(1000)

                log(
                    f"Clicked postcard control: {selector}"
                )

                return True

            except Exception as exc:
                log(
                    f"Click failed: {exc}"
                )

        except Exception as exc:
            log(
                f"Selector error: {selector}: {exc}"
            )

    # Fallback: find an element by title.
    try:
        elements = frame.locator(
            "[title]"
        )

        count = await elements.count()

        for i in range(count):

            element = elements.nth(i)

            title = await element.get_attribute(
                "title"
            )

            if title and title.strip().lower() == "dopisnica":

                log(
                    "Found fallback title='Dopisnica'"
                )

                await element.click(
                    timeout=5000,
                    force=True,
                )

                await frame.wait_for_timeout(1000)

                return True

    except Exception as exc:
        log(
            f"Fallback postcard detection failed: {exc}"
        )

    return False


# ============================================================
# AIR TRANSPORT
# ============================================================

async def enable_air_transport(frame):
    section("ENABLING AVIONSKI PRIJENOS")

    selectors = [
        "#chbMeDoAvionski",
        "input[name='chbMeDoAvionski']",
        "input[type='checkbox']",
    ]

    # First try the exact expected selector.
    for selector in selectors:

        try:
            locator = frame.locator(selector)

            count = await locator.count()

            log(
                f"{selector:40} -> {count}"
            )

            if count == 0:
                continue

            # For the generic checkbox selector, find one
            # whose surrounding text refers to Avionski prijenos.
            if selector == "input[type='checkbox']":

                matched = None

                for i in range(count):

                    candidate = locator.nth(i)

                    try:
                        candidate_id = (
                            await candidate.get_attribute(
                                "id"
                            )
                        )

                        candidate_name = (
                            await candidate.get_attribute(
                                "name"
                            )
                        )

                        outer = await candidate.evaluate(
                            "(el) => el.parentElement.outerHTML"
                        )

                        combined = (
                            f"{candidate_id or ''} "
                            f"{candidate_name or ''} "
                            f"{outer or ''}"
                        ).lower()

                        if (
                            "avionski" in combined
                            or "avio" in combined
                        ):
                            matched = candidate
                            break

                    except Exception:
                        continue

                if matched is None:
                    continue

                element = matched

            else:
                element = locator.first

            try:
                if not await element.is_checked():
                    await element.check(
                        timeout=5000,
                        force=True,
                    )

                    await frame.wait_for_timeout(
                        1000
                    )

                    log(
                        "Avionski prijenos enabled."
                    )

                else:
                    log(
                        "Avionski prijenos was already enabled."
                    )

                return True

            except Exception as exc:

                log(
                    f"Checkbox operation failed: {exc}"
                )

        except Exception as exc:
            log(
                f"Selector error: {selector}: {exc}"
            )

    return False


# ============================================================
# WEIGHT
# ============================================================

async def enter_weight(frame, grams="10"):
    section("ENTERING AIR WEIGHT")

    selectors = [
        "#tbxMeDoAvioTezina",
        "input[name='tbxMeDoAvioTezina']",
    ]

    for selector in selectors:

        try:
            locator = frame.locator(selector)

            count = await locator.count()

            log(
                f"{selector:40} -> {count}"
            )

            if count == 0:
                continue

            await locator.first.fill(
                str(grams)
            )

            await frame.wait_for_timeout(500)

            value = await locator.first.input_value()

            log(
                f"Weight field value: {value}"
            )

            if value == str(grams):
                return True

        except Exception as exc:
            log(
                f"Weight entry failed: {exc}"
            )

    return False


# ============================================================
# CALCULATE
# ============================================================

async def click_calculate(frame):
    section("CLICKING IZRAČUNAJ")

    selectors = [
        "#btnMeDoIzracunaj",
        "input[name='btnMeDoIzracunaj']",
        "input[type='submit'][value='Izračunaj']",
        "input.dugme[value='Izračunaj']",
    ]

    for selector in selectors:

        try:
            locator = frame.locator(selector)

            count = await locator.count()

            log(
                f"{selector:45} -> {count}"
            )

            if count == 0:
                continue

            await locator.first.click(
                timeout=10000,
                force=True,
            )

            log(
                f"Clicked calculate button: {selector}"
            )

            # ASP.NET postback / update.
            await frame.wait_for_timeout(2000)

            return True

        except Exception as exc:
            log(
                f"Calculate click failed: {exc}"
            )

    # Last-resort search for submit inputs whose value is
    # Izračunaj.
    try:
        submits = frame.locator(
            "input[type='submit']"
        )

        count = await submits.count()

        for i in range(count):

            element = submits.nth(i)

            value = await element.get_attribute(
                "value"
            )

            if normalize_text(value) == "Izračunaj":

                await element.click(
                    timeout=10000,
                    force=True,
                )

                await frame.wait_for_timeout(2000)

                log(
                    "Clicked fallback Izračunaj submit."
                )

                return True

    except Exception as exc:
        log(
            f"Fallback calculate failed: {exc}"
        )

    return False


# ============================================================
# ERROR DETECTION
# ============================================================

async def get_frame_text(frame):
    try:
        return normalize_text(
            await frame.locator("body").inner_text()
        )
    except Exception:
        return ""


async def error_message_present(frame):
    text = await get_frame_text(frame)

    return ERROR_MESSAGE.lower() in text.lower()


async def find_error_text(frame):
    """
    Return the actual text surrounding the error message.
    """

    try:
        body_text = await frame.locator(
            "body"
        ).inner_text()

        normalized = normalize_text(body_text)

        position = normalized.lower().find(
            ERROR_MESSAGE.lower()
        )

        if position < 0:
            return ""

        start = max(
            0,
            position - 150,
        )

        end = min(
            len(normalized),
            position + len(ERROR_MESSAGE) + 300,
        )

        return normalized[start:end]

    except Exception:
        return ""


# ============================================================
# COUNTRY TESTING
# ============================================================

async def test_country(
    frame,
    country,
    index,
    total,
):
    name = country["name"]
    value = country["value"]

    print()
    print(
        f"[{index}/{total}] Testing: "
        f"{name} ({value})"
    )

    diagnostic_lines.append(
        f"[{index}/{total}] Testing: "
        f"{name} ({value})"
    )

    dropdown = frame.locator(
        "#ddlMeDoOdrediste"
    )

    # --------------------------------------------------------
    # Select destination.
    # --------------------------------------------------------

    try:
        await dropdown.select_option(
            value=value
        )

    except Exception as exc:

        log(
            f"Could not select {name} by value: "
            f"{exc}"
        )

        try:
            await dropdown.select_option(
                label=name
            )

        except Exception as exc2:

            log(
                f"Could not select {name} by label: "
                f"{exc2}"
            )

            return {
                "name": name,
                "value": value,
                "status": "SELECT_FAILED",
            }

    await frame.wait_for_timeout(800)

    # --------------------------------------------------------
    # Ensure postcard.
    #
    # Some ASP.NET controls can reset after a postback.
    # --------------------------------------------------------

    try:
        await select_postcard(frame)
    except Exception:
        pass

    # --------------------------------------------------------
    # Ensure air transport.
    # --------------------------------------------------------

    try:
        air_ok = await enable_air_transport(frame)

        if not air_ok:
            log(
                "WARNING: Could not confirm "
                "Avionski prijenos."
            )

    except Exception as exc:
        log(
            f"Air transport error: {exc}"
        )

    # --------------------------------------------------------
    # Enter 10 grams.
    # --------------------------------------------------------

    try:
        weight_ok = await enter_weight(
            frame,
            "10",
        )

        if not weight_ok:
            log(
                "WARNING: Could not confirm "
                "10 g weight."
            )

    except Exception as exc:
        log(
            f"Weight error: {exc}"
        )

    # --------------------------------------------------------
    # Click calculate.
    # --------------------------------------------------------

    try:
        calculate_ok = await click_calculate(
            frame
        )

        if not calculate_ok:

            log(
                "ERROR: Could not click Izračunaj."
            )

            return {
                "name": name,
                "value": value,
                "status": "CALCULATE_FAILED",
            }

    except Exception as exc:

        log(
            f"Calculate error: {exc}"
        )

        return {
            "name": name,
            "value": value,
            "status": "CALCULATE_FAILED",
        }

    # --------------------------------------------------------
    # Give the ASP.NET application time to update.
    # --------------------------------------------------------

    await frame.wait_for_timeout(1500)

    # --------------------------------------------------------
    # Check error.
    # --------------------------------------------------------

    try:
        has_error = await error_message_present(
            frame
        )

        if has_error:

            context = await find_error_text(
                frame
            )

            print(
                f"  -> UNAVAILABLE"
            )

            diagnostic_lines.append(
                f"  -> UNAVAILABLE"
            )

            if context:
                diagnostic_lines.append(
                    f"     {context}"
                )

            return {
                "name": name,
                "value": value,
                "status": "UNAVAILABLE",
            }

        else:

            print(
                f"  -> AVAILABLE / NO ERROR"
            )

            diagnostic_lines.append(
                f"  -> AVAILABLE / NO ERROR"
            )

            return {
                "name": name,
                "value": value,
                "status": "AVAILABLE",
            }

    except Exception as exc:

        log(
            f"Error-message check failed: {exc}"
        )

        return {
            "name": name,
            "value": value,
            "status": "CHECK_FAILED",
        }


# ============================================================
# WRITE COUNTRIES.TXT
# ============================================================

def write_countries_file(
    countries,
    unavailable,
):
    section("WRITING COUNTRIES.TXT")

    lines = []

    lines.append(
        "JP BH POŠTA - DESTINATION COUNTRY MONITOR"
    )
    lines.append(
        "Generated automatically by GitHub Actions."
    )
    lines.append(
        "Original dropdown order is preserved."
    )
    lines.append("")

    lines.append(
        "ALL DESTINATION COUNTRIES"
    )
    lines.append(
        "========================="
    )

    for country in countries:
        lines.append(
            country["name"]
        )

    lines.append("")

    lines.append(
        "COUNTRIES SHOWING:"
    )
    lines.append(
        ERROR_MESSAGE
    )
    lines.append(
        "=================================================="
    )

    unavailable_names = {
        item["name"]
        for item in unavailable
    }

    # Preserve dropdown order.
    for country in countries:

        if country["name"] in unavailable_names:

            lines.append(
                country["name"]
            )

    lines.append("")

    lines.append(
        f"TOTAL DESTINATIONS: {len(countries)}"
    )

    lines.append(
        f"TOTAL UNAVAILABLE: {len(unavailable)}"
    )

    COUNTRIES_FILE.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    log(
        f"Saved {COUNTRIES_FILE} "
        f"({len(lines):,} lines)"
    )


# ============================================================
# MAIN
# ============================================================

async def main():

    section(
        "JP BH POŠTA CALCULATOR MONITOR"
    )

    log(f"URL: {URL}")

    if not URL:
        raise RuntimeError(
            "CALCULATOR_URL is empty."
        )

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )

        context = await browser.new_context(
            viewport={
                "width": 1440,
                "height": 1200,
            },
            locale="hr-HR",
            timezone_id="Europe/Sarajevo",
        )

        page = await context.new_page()

        page.set_default_timeout(
            TIMEOUT
        )

        # ----------------------------------------------------
        # OPEN MAIN PAGE
        # ----------------------------------------------------

        section("OPENING MAIN PAGE")

        log("Opening page...")

        response = await page.goto(
            URL,
            wait_until="domcontentloaded",
            timeout=60_000,
        )

        if response:
            log(
                f"HTTP status: "
                f"{response.status}"
            )

        await page.wait_for_timeout(
            3000
        )

        log(
            f"Final URL: {page.url}"
        )

        log(
            f"Page title: {await page.title()}"
        )

        # ----------------------------------------------------
        # SAVE MAIN PAGE
        # ----------------------------------------------------

        try:
            html = await page.content()

            PAGE_HTML.write_text(
                html,
                encoding="utf-8",
            )

            log(
                f"Saved: page.html "
                f"({len(html):,} bytes)"
            )

        except Exception as exc:
            log(
                f"Could not save page.html: {exc}"
            )

        # ----------------------------------------------------
        # WAIT FOR IFRAMES
        # ----------------------------------------------------

        section("LOCATING CALCULATOR IFRAME")

        # Give iframe loading some time.
        await page.wait_for_timeout(
            5000
        )

        calculator_frame = None

        # Try repeatedly because the calculator iframe can
        # appear after the main page loads.
        for attempt in range(10):

            log(
                f"Frame search attempt "
                f"{attempt + 1}/10"
            )

            calculator_frame = (
                await find_calculator_frame(page)
            )

            if calculator_frame:
                break

            await page.wait_for_timeout(
                2000
            )

        if calculator_frame is None:

            # Save screenshot before failing.
            try:
                await page.screenshot(
                    path=str(SCREENSHOT),
                    full_page=True,
                )

                log(
                    f"Screenshot saved to: "
                    f"{SCREENSHOT}"
                )

            except Exception:
                pass

            save_diagnostic()

            raise RuntimeError(
                "Could not find the actual calculator "
                "iframe. Expected a frame whose URL "
                f"contains {CALCULATOR_FRAME_HOST}"
                f"{CALCULATOR_FRAME_PATH}"
            )

        # ----------------------------------------------------
        # WAIT FOR ACTUAL CALCULATOR DOCUMENT
        # ----------------------------------------------------

        section(
            "WAITING FOR CALCULATOR IFRAME"
        )

        try:
            await calculator_frame.wait_for_load_state(
                "domcontentloaded",
                timeout=30_000,
            )

        except Exception as exc:
            log(
                f"Calculator frame load-state warning: "
                f"{exc}"
            )

        await page.wait_for_timeout(
            2000
        )

        log(
            f"Calculator URL: "
            f"{calculator_frame.url}"
        )

        # ----------------------------------------------------
        # SAVE CALCULATOR HTML
        # ----------------------------------------------------

        await save_frame(
            calculator_frame
        )

        # ----------------------------------------------------
        # INITIAL CONTROL DIAGNOSTICS
        # ----------------------------------------------------

        section(
            "INITIAL CALCULATOR CONTROLS"
        )

        await dump_controls(
            calculator_frame
        )

        # ----------------------------------------------------
        # ACTIVATE INTERNATIONAL
        # ----------------------------------------------------

        international_ok = (
            await click_international_tab(
                calculator_frame
            )
        )

        if not international_ok:

            # Save current state.
            try:
                html = await calculator_frame.content()

                IFRAME_HTML.write_text(
                    html,
                    encoding="utf-8",
                )

            except Exception:
                pass

            try:
                await page.screenshot(
                    path=str(SCREENSHOT),
                    full_page=True,
                )

            except Exception:
                pass

            save_diagnostic()

            raise RuntimeError(
                "Could not activate Međunarodni promet "
                "or the international controls did not "
                "appear. See iframe.html and "
                "diagnostic.png."
            )

        # ----------------------------------------------------
        # WAIT FOR INTERNATIONAL CONTROLS
        # ----------------------------------------------------

        section(
            "WAITING FOR INTERNATIONAL CONTROLS"
        )

        try:

            await calculator_frame.wait_for_selector(
                "#ddlMeDoOdrediste",
                timeout=30_000,
            )

        except PlaywrightTimeoutError:

            # Save everything useful.
            await save_frame(
                calculator_frame
            )

            await dump_controls(
                calculator_frame
            )

            try:
                await page.screenshot(
                    path=str(SCREENSHOT),
                    full_page=True,
                )
            except Exception:
                pass

            save_diagnostic()

            raise RuntimeError(
                "International destination dropdown "
                "#ddlMeDoOdrediste did not appear."
            )

        # ----------------------------------------------------
        # INTERNATIONAL CONTROLS FOUND
        # ----------------------------------------------------

        section(
            "INTERNATIONAL CONTROLS FOUND"
        )

        await dump_controls(
            calculator_frame
        )

        # ----------------------------------------------------
        # EXTRACT COUNTRIES
        # ----------------------------------------------------

        countries = await extract_countries(
            calculator_frame
        )

        log("")
        log(
            f"TOTAL COUNTRIES FOUND: "
            f"{len(countries)}"
        )

        # ----------------------------------------------------
        # WRITE INITIAL COUNTRY LIST.
        #
        # This ensures that even if testing fails later,
        # the raw dropdown list is preserved.
        # ----------------------------------------------------

        write_countries_file(
            countries,
            [],
        )

        # ----------------------------------------------------
        # SELECT DOPISNICA
        # ----------------------------------------------------

        postcard_ok = await select_postcard(
            calculator_frame
        )

        if not postcard_ok:

            log(
                "WARNING: Could not explicitly "
                "select Dopisnica."
            )

        # ----------------------------------------------------
        # ENABLE AIR TRANSPORT
        # ----------------------------------------------------

        air_ok = await enable_air_transport(
            calculator_frame
        )

        if not air_ok:

            log(
                "WARNING: Could not explicitly "
                "enable Avionski prijenos."
            )

        # ----------------------------------------------------
        # ENTER WEIGHT
        # ----------------------------------------------------

        weight_ok = await enter_weight(
            calculator_frame,
            "10",
        )

        if not weight_ok:

            log(
                "WARNING: Could not explicitly "
                "enter 10 grams."
            )

        # ----------------------------------------------------
        # TEST COUNTRIES
        # ----------------------------------------------------

        section(
            "TESTING ALL DESTINATION COUNTRIES"
        )

        unavailable = []
        results = []

        total = len(countries)

        for position, country in enumerate(
            countries,
            start=1,
        ):

            result = await test_country(
                calculator_frame,
                country,
                position,
                total,
            )

            results.append(
                result
            )

            if result["status"] == "UNAVAILABLE":
                unavailable.append(
                    result
                )

        # ----------------------------------------------------
        # WRITE FINAL COUNTRIES FILE
        # ----------------------------------------------------

        write_countries_file(
            countries,
            unavailable,
        )

        # ----------------------------------------------------
        # FINAL DIAGNOSTICS
        # ----------------------------------------------------

        section(
            "FINAL SUMMARY"
        )

        log(
            f"Total destinations: "
            f"{len(countries)}"
        )

        log(
            f"Unavailable destinations: "
            f"{len(unavailable)}"
        )

        log("")
        log(
            "UNAVAILABLE COUNTRIES"
        )

        for country in unavailable:
            log(
                f"  {country['name']} "
                f"({country['value']})"
            )

        # Save current calculator HTML.
        try:
            html = await calculator_frame.content()

            DIAGNOSTIC_HTML.write_text(
                html,
                encoding="utf-8",
            )

            log(
                f"Saved: diagnostic.html "
                f"({len(html):,} bytes)"
            )

        except Exception as exc:
            log(
                f"Could not save diagnostic.html: "
                f"{exc}"
            )

        # Screenshot.
        try:

            await page.screenshot(
                path=str(SCREENSHOT),
                full_page=True,
            )

            log(
                f"Screenshot saved to: "
                f"{SCREENSHOT}"
            )

        except Exception as exc:

            log(
                f"Screenshot failed: {exc}"
            )

        save_diagnostic()

        await browser.close()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:

        asyncio.run(
            main()
        )

    except Exception as exc:

        print()
        print("=" * 70)
        print("MONITOR FAILED")
        print("=" * 70)
        print(str(exc))

        diagnostic_lines.append("")
        diagnostic_lines.append(
            "=" * 70
        )
        diagnostic_lines.append(
            "MONITOR FAILED"
        )
        diagnostic_lines.append(
            "=" * 70
        )
        diagnostic_lines.append(
            str(exc)
        )

        save_diagnostic()

        raise
