import asyncio
import os
import re
from pathlib import Path

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError


# ============================================================
# CONFIGURATION
# ============================================================

URL = os.environ.get(
    "CALCULATOR_URL",
    "https://www.posta.ba/kalkulator-cijena/"
)

ERROR_MESSAGE = "Prijem pošiljaka se trenutno ne vrši za odabranu državu"

OUTPUT_FILE = Path("countries.txt")

DIAGNOSTIC_HTML = Path("page.html")
DIAGNOSTIC_RESPONSE = Path("response.html")
DIAGNOSTIC_SCREENSHOT = Path("diagnostic.png")
DIAGNOSTIC_TEXT = Path("diagnostic.txt")

# How long to wait for page operations.
TIMEOUT = 30_000

# Small pause after ASP.NET postbacks.
POSTBACK_WAIT = 1.5


# ============================================================
# HELPERS
# ============================================================

def section(title):
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def clean_text(text):
    if not text:
        return ""

    return re.sub(r"\s+", " ", text).strip()


def write_diagnostic(message):
    print(message)

    with DIAGNOSTIC_TEXT.open("a", encoding="utf-8") as f:
        f.write(message + "\n")


async def save_frame_html(frame, filename):
    try:
        html = await frame.content()

        with filename.open("w", encoding="utf-8") as f:
            f.write(html)

        return html

    except Exception as e:
        write_diagnostic(f"Could not save HTML: {e}")
        return ""


async def wait_for_stability(page):
    """
    Give JavaScript / ASP.NET UpdatePanel time to finish.
    """

    try:
        await page.wait_for_load_state("domcontentloaded", timeout=TIMEOUT)
    except Exception:
        pass

    await page.wait_for_timeout(1000)


async def find_frame_with_selector(page, selector):
    """
    Search the main document and every iframe for a selector.
    """

    # Main frame first.
    try:
        if await page.locator(selector).count() > 0:
            return page.main_frame
    except Exception:
        pass

    # Then all child frames.
    for frame in page.frames:
        if frame == page.main_frame:
            continue

        try:
            if await frame.locator(selector).count() > 0:
                return frame
        except Exception:
            pass

    return None


async def find_calculator_frame(page):
    """
    The calculator HTML we were given is ASP.NET and should contain
    ddlMeDoOdrediste.

    Search for that first.

    If it isn't present, look for other strong calculator identifiers.
    """

    selectors = [
        "#ddlMeDoOdrediste",
        "select[name='ddlMeDoOdrediste']",
        "#ASPxTabControl1",
        "#chbMeDoAvionski",
        "select[name='ddlMeDoOdrediste'] option",
    ]

    for selector in selectors:
        frame = await find_frame_with_selector(page, selector)

        if frame:
            write_diagnostic(
                f"Calculator found using selector: {selector}"
            )
            write_diagnostic(
                f"Calculator frame URL: {frame.url}"
            )
            return frame

    return None


async def print_page_diagnostics(page):
    section("SEARCHING RAW HTML")

    html = await page.content()

    DIAGNOSTIC_HTML.write_text(html, encoding="utf-8")

    print(f"Main page HTML length: {len(html):,}")

    searches = [
        "ddlMeDoOdrediste",
        "chbMeDoAvionski",
        "tbxMeDoAvioTezina",
        "btnMeDoIzracunaj",
        "btnMeObPiIzracunaj",
        "Međunarodni promet",
        "Unutrašnji promet",
        "UpdatePanel",
        "ASPxTabControl1",
        "Kalkulator",
        "Prijem pošiljaka",
        "Izračunaj",
    ]

    for term in searches:
        print(f"{term!r:45} -> {html.count(term)}")

    print()
    print("=" * 70)
    print("IFRAMES")
    print("=" * 70)

    print(f"Number of frames: {len(page.frames)}")

    for index, frame in enumerate(page.frames):
        try:
            frame_url = frame.url
        except Exception:
            frame_url = "UNKNOWN"

        print()
        print(f"Frame {index}")
        print(f"URL: {frame_url}")

        try:
            frame_html = await frame.content()

            print(f"HTML length: {len(frame_html):,}")

            for term in [
                "ddlMeDoOdrediste",
                "chbMeDoAvionski",
                "ASPxTabControl1",
                "Međunarodni promet",
                "Izračunaj",
            ]:
                count = frame_html.count(term)

                if count:
                    print(f"  {term!r}: {count}")

        except Exception as e:
            print(f"Could not inspect frame: {e}")


# ============================================================
# COUNTRY EXTRACTION
# ============================================================

async def extract_countries(frame):
    """
    Extract countries directly from:

        <select name="ddlMeDoOdrediste">
            <option value="AF">Afganistan</option>
            ...

    The order is deliberately preserved.
    """

    section("DESTINATION DROPDOWN")

    locator = frame.locator(
        "select[name='ddlMeDoOdrediste']"
    )

    count = await locator.count()

    print(f"Destination dropdown count: {count}")

    if count == 0:
        raise RuntimeError(
            "Could not find destination dropdown "
            "select[name='ddlMeDoOdrediste']"
        )

    select = locator.first

    options = select.locator("option")

    option_count = await options.count()

    print(f"Number of options: {option_count}")

    countries = []

    for i in range(option_count):

        option = options.nth(i)

        name = clean_text(await option.inner_text())
        value = await option.get_attribute("value")

        if not name:
            continue

        countries.append(
            {
                "name": name,
                "value": value or "",
            }
        )

    print()
    print("Countries found:")
    print()

    for i, country in enumerate(countries, start=1):
        print(
            f"{i:3}. {country['name']} "
            f"[{country['value']}]"
        )

    return countries


# ============================================================
# CHECK CURRENT ERROR
# ============================================================

async def page_contains_error(frame):
    """
    Check visible text for the exact error message.
    """

    try:
        body_text = await frame.locator("body").inner_text(
            timeout=10_000
        )

        normalized = clean_text(body_text)

        return ERROR_MESSAGE in normalized

    except Exception:
        return False


async def get_visible_text(frame):
    try:
        return clean_text(
            await frame.locator("body").inner_text(
                timeout=10_000
            )
        )
    except Exception:
        return ""


# ============================================================
# SELECT DESTINATION
# ============================================================

async def select_destination(frame, country_value):
    """
    Select the country.

    The real calculator has:

        onchange="javascript:setTimeout(
            '__doPostBack(\'ddlMeDoOdrediste\',\'\')',
            0
        )"

    So selecting the option causes an ASP.NET postback.

    Playwright's select_option triggers the onchange JavaScript.
    """

    select = frame.locator(
        "select[name='ddlMeDoOdrediste']"
    ).first

    await select.select_option(value=country_value)

    # Allow the onchange timer to fire.
    await frame.page.wait_for_timeout(500)

    # Wait for the ASP.NET update.
    await frame.page.wait_for_timeout(
        int(POSTBACK_WAIT * 1000)
    )


# ============================================================
# CALCULATE
# ============================================================

async def click_calculate(frame):
    """
    Click the appropriate calculation button.

    International traffic may use btnMeDoIzracunaj.

    The HTML diagnostic supplied earlier also showed
    btnMeObPiIzracunaj, so both are supported.
    """

    selectors = [
        "#btnMeDoIzracunaj",
        "input[name='btnMeDoIzracunaj']",
        "#btnMeObPiIzracunaj",
        "input[name='btnMeObPiIzracunaj']",
        "input[type='submit'][value='Izračunaj']",
    ]

    for selector in selectors:

        locator = frame.locator(selector)

        try:
            count = await locator.count()

            if count == 0:
                continue

            # Use the first visible button.
            for i in range(count):

                button = locator.nth(i)

                try:
                    if not await button.is_visible():
                        continue

                    await button.click()

                    await frame.page.wait_for_timeout(
                        int(POSTBACK_WAIT * 1000)
                    )

                    return True

                except Exception:
                    continue

        except Exception:
            continue

    return False


# ============================================================
# TEST ONE COUNTRY
# ============================================================

async def test_country(page, frame, country, index, total):
    name = country["name"]
    value = country["value"]

    print()
    print(
        f"[{index}/{total}] Testing: "
        f"{name} [{value}]"
    )

    try:
        # Select destination.
        await select_destination(
            frame,
            value
        )

        # Check whether destination selection itself already
        # produced the unavailable message.
        if await page_contains_error(frame):
            print("  -> ERROR MESSAGE PRESENT after destination selection")
            return True

        # Click calculation.
        clicked = await click_calculate(frame)

        if not clicked:
            print("  -> Could not find/click Izračunaj")
            return False

        # Check result.
        if await page_contains_error(frame):
            print("  -> NOT AVAILABLE")
            return True

        # No exact error.
        print("  -> AVAILABLE / NO ERROR")

        return False

    except Exception as e:
        print(f"  -> ERROR while testing country: {e}")

        return False


# ============================================================
# WRITE OUTPUT
# ============================================================

def write_countries_file(countries, unavailable):
    """
    Output is intentionally NOT alphabetized.

    The original dropdown order is preserved.

    Format:

    ALL DESTINATIONS
    ----------------
    Afganistan
    Albanija
    ...

    NOT CURRENTLY ACCEPTED
    ----------------------
    ...
    """

    lines = []

    lines.append("ALL DESTINATIONS")
    lines.append("================")
    lines.append("")

    for country in countries:
        lines.append(country["name"])

    lines.append("")
    lines.append("")
    lines.append("NOT CURRENTLY ACCEPTED")
    lines.append("======================")
    lines.append("")

    unavailable_names = {
        country["name"]
        for country in unavailable
    }

    # IMPORTANT:
    # Preserve original dropdown order here too.
    for country in countries:
        if country["name"] in unavailable_names:
            lines.append(country["name"])

    lines.append("")

    OUTPUT_FILE.write_text(
        "\n".join(lines),
        encoding="utf-8"
    )


# ============================================================
# MAIN
# ============================================================

async def main():

    # Start fresh diagnostic log.
    DIAGNOSTIC_TEXT.write_text(
        "",
        encoding="utf-8"
    )

    section("JP BH POŠTA CALCULATOR MONITOR")

    print(f"URL: {URL}")

    if not URL:
        raise RuntimeError(
            "CALCULATOR_URL is empty"
        )

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )

        context = await browser.new_context(
            viewport={
                "width": 1440,
                "height": 1200,
            },
            locale="hr-HR",
            timezone_id="Europe/Sarajevo",
            user_agent=(
                "Mozilla/5.0 "
                "(X11; Linux x86_64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/131.0.0.0 "
                "Safari/537.36"
            ),
        )

        page = await context.new_page()

        page.set_default_timeout(TIMEOUT)

        # ----------------------------------------------------
        # OPEN PAGE
        # ----------------------------------------------------

        section("OPENING PAGE")

        print("Opening page...")

        try:

            response = await page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=TIMEOUT,
            )

            if response:
                print(
                    f"HTTP status: {response.status}"
                )

                print(
                    f"Final URL: {page.url}"
                )

                # Save raw HTTP response.
                try:
                    body = await response.body()

                    DIAGNOSTIC_RESPONSE.write_bytes(
                        body
                    )

                    print(
                        f"Response body saved: "
                        f"{len(body):,} bytes"
                    )

                except Exception as e:
                    print(
                        f"Could not save response body: {e}"
                    )

        except Exception as e:

            print()
            print("PAGE NAVIGATION FAILED")
            print(str(e))

            await page.screenshot(
                path=str(DIAGNOSTIC_SCREENSHOT),
                full_page=True,
            )

            await browser.close()

            raise

        await wait_for_stability(page)

        print(
            f"Page title: "
            f"{await page.title()}"
        )

        # ----------------------------------------------------
        # INITIAL DIAGNOSTICS
        # ----------------------------------------------------

        await print_page_diagnostics(page)

        # Save screenshot.
        try:
            await page.screenshot(
                path=str(DIAGNOSTIC_SCREENSHOT),
                full_page=True,
            )

            print(
                f"Screenshot saved to: "
                f"{DIAGNOSTIC_SCREENSHOT}"
            )

        except Exception as e:
            print(
                f"Could not save screenshot: {e}"
            )

        # ----------------------------------------------------
        # FIND CALCULATOR
        # ----------------------------------------------------

        section("LOCATING CALCULATOR")

        frame = await find_calculator_frame(page)

        if frame is None:

            print()
            print(
                "ERROR: The calculator controls were not found."
            )

            print()
            print(
                "The browser did not receive the ASP.NET "
                "calculator HTML."
            )

            print()
            print(
                "Expected selector:"
            )

            print(
                "  #ddlMeDoOdrediste"
            )

            print()
            print(
                "The saved page.html and response.html "
                "should show what GitHub actually received."
            )

            await browser.close()

            raise RuntimeError(
                "Calculator controls not found. "
                "See page.html and response.html."
            )

        print(
            f"Using calculator frame: {frame.url}"
        )

        # ----------------------------------------------------
        # EXTRACT COUNTRIES
        # ----------------------------------------------------

        countries = await extract_countries(
            frame
        )

        if not countries:
            await browser.close()

            raise RuntimeError(
                "Destination dropdown exists but "
                "contains no countries."
            )

        # ----------------------------------------------------
        # TEST COUNTRIES
        # ----------------------------------------------------

        section("TESTING DESTINATIONS")

        unavailable = []

        total = len(countries)

        print(
            f"Testing {total} destinations."
        )

        print(
            "Original dropdown order will be preserved."
        )

        for index, country in enumerate(
            countries,
            start=1
        ):

            is_unavailable = await test_country(
                page,
                frame,
                country,
                index,
                total,
            )

            if is_unavailable:
                unavailable.append(country)

        # ----------------------------------------------------
        # WRITE OUTPUT
        # ----------------------------------------------------

        section("RESULT")

        write_countries_file(
            countries,
            unavailable
        )

        print(
            f"Total destinations: "
            f"{len(countries)}"
        )

        print(
            f"Unavailable destinations: "
            f"{len(unavailable)}"
        )

        print()
        print(
            "Unavailable destinations:"
        )

        for country in unavailable:
            print(
                f"  {country['name']}"
            )

        print()
        print(
            f"Output written to: "
            f"{OUTPUT_FILE}"
        )

        # ----------------------------------------------------
        # FINAL ERROR CHECK
        # ----------------------------------------------------

        section("FINAL DIAGNOSTIC")

        final_text = await get_visible_text(
            frame
        )

        if ERROR_MESSAGE in final_text:
            print(
                "ERROR MESSAGE IS CURRENTLY PRESENT"
            )
        else:
            print(
                "ERROR MESSAGE IS NOT CURRENTLY PRESENT"
            )

        print()
        print(
            f"Diagnostic report saved to: "
            f"{DIAGNOSTIC_TEXT}"
        )

        await browser.close()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    asyncio.run(main())
