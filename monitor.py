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
    "https://www.posta.ba/kalkulator-cijena/",
)

ERROR_MESSAGE = "Prijem pošiljaka se trenutno ne vrši za odabranu državu"

WEIGHT_GRAMS = "10"

# We want the "Dopisnica / Postcard" service.
POSTCARD_TITLES = [
    "Dopisnica",
    "Postcard",
]

# International calculator controls may have slightly different
# IDs after the international tab is activated, so we discover them.
COUNTRY_ID = "ddlMeDoOdrediste"

# Diagnostic files
PAGE_HTML = Path("page.html")
IFRAME_HTML = Path("iframe.html")
IFRAME_TEXT = Path("iframe.txt")
DIAGNOSTIC = Path("diagnostic.txt")
SCREENSHOT = Path("diagnostic.png")

# Output
COUNTRIES_FILE = Path("countries.txt")

# Timeouts
PAGE_TIMEOUT = 60_000
POSTBACK_TIMEOUT = 30_000
SHORT_WAIT = 1.5


# ============================================================
# HELPERS
# ============================================================

def section(title):
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def clean_text(text):
    return re.sub(r"\s+", " ", text or "").strip()


def save_text(path, text):
    path.write_text(text or "", encoding="utf-8")


async def safe_content(frame):
    try:
        return await frame.content()
    except Exception:
        return ""


async def wait_for_network(page, milliseconds=1500):
    """
    ASP.NET Web Forms sometimes performs a full navigation and
    sometimes an asynchronous update. We therefore use a small
    explicit wait rather than relying only on networkidle.
    """
    await page.wait_for_timeout(milliseconds)


async def find_calculator_frame(page):
    """
    Locate the actual calculator iframe.

    The main page contains several frames, including reCAPTCHA.
    The calculator is currently:
        https://bhpwebout.posta.ba/KalkulatorCijena_WEB_app/Bos/Default.aspx
    """

    section("LOCATING CALCULATOR IFRAME")

    frames = page.frames

    print(f"Number of frames: {len(frames)}")

    for index, frame in enumerate(frames):
        print(f"Checking frame {index}: {frame.url}")

        try:
            html = await frame.content()
        except Exception:
            html = ""

        # Strong indicators.
        if (
            "ddlUnObPiTez" in html
            or "btnUnObPiIzracunaj" in html
            or "Međunarodni promet" in html
            or "Unutrašnji promet" in html
        ):
            print(f"FOUND CALCULATOR FRAME: {index}")
            print(f"Calculator URL: {frame.url}")
            return frame

    # Fallback: look for the known iframe URL.
    for frame in frames:
        if "KalkulatorCijena_WEB_app" in frame.url:
            print("FOUND CALCULATOR FRAME BY URL")
            print(f"Calculator URL: {frame.url}")
            return frame

    return None


async def write_frame_diagnostics(frame):
    section("SAVING CALCULATOR IFRAME")

    html = await safe_content(frame)
    text = clean_text(await frame.locator("body").inner_text())

    save_text(IFRAME_HTML, html)
    save_text(IFRAME_TEXT, text)

    print(f"Saved: {IFRAME_HTML} ({len(html):,} bytes)")
    print(f"Saved: {IFRAME_TEXT} ({len(text):,} bytes)")

    return html


async def find_international_tab(frame):
    """
    Find the control which activates Međunarodni promet.

    The exact ASP.NET control ID is not assumed because the site's
    rendered markup may change.
    """

    section("LOCATING MEĐUNARODNI PROMET")

    # First look for text.
    candidates = frame.get_by_text("Međunarodni promet", exact=False)

    count = await candidates.count()
    print(f"Text candidates: {count}")

    for i in range(count):
        candidate = candidates.nth(i)

        try:
            if await candidate.is_visible():
                print(
                    f"Visible Međunarodni promet candidate #{i}: "
                    f"{await candidate.evaluate('(e) => e.outerHTML')}"
                )
                return candidate
        except Exception:
            pass

    # Look for elements whose title/alt/value contains the text.
    selectors = [
        "[title*='Međunarodni']",
        "[alt*='Međunarodni']",
        "input[value*='Međunarodni']",
        "a:has-text('Međunarodni promet')",
        "td:has-text('Međunarodni promet')",
        "span:has-text('Međunarodni promet')",
    ]

    for selector in selectors:
        try:
            loc = frame.locator(selector)
            count = await loc.count()

            for i in range(count):
                item = loc.nth(i)

                try:
                    if await item.is_visible():
                        print(f"Found international tab using: {selector}")
                        return item
                except Exception:
                    pass
        except Exception:
            pass

    return None


async def activate_international_tab(page, frame):
    """
    Activate the international calculator.

    This is the critical step discovered from the diagnostics:
    the initial iframe is the domestic calculator. The international
    controls are not present until this tab is activated.
    """

    section("ACTIVATING MEĐUNARODNI PROMET")

    tab = await find_international_tab(frame)

    if tab is None:
        print("Could not find Međunarodni promet tab.")
        return False

    print("Clicking Međunarodni promet...")

    old_url = frame.url

    try:
        async with page.expect_response(
            lambda response: "KalkulatorCijena_WEB_app" in response.url,
            timeout=POSTBACK_TIMEOUT,
        ):
            await tab.click()
    except PlaywrightTimeoutError:
        # The application may use an asynchronous ASP.NET postback
        # without producing the response we expected.
        print("No matching response captured; continuing.")
    except Exception as exc:
        print(f"Normal click failed: {exc}")

        # Try JavaScript click as fallback.
        try:
            await tab.evaluate("(el) => el.click()")
        except Exception as exc2:
            print(f"JavaScript click also failed: {exc2}")

    await wait_for_network(page, 2500)

    # Give ASP.NET a chance to update the DOM.
    try:
        await frame.wait_for_selector(
            "body",
            timeout=POSTBACK_TIMEOUT,
        )
    except Exception:
        pass

    html = await safe_content(frame)

    print(f"Frame URL before/after: {old_url} -> {frame.url}")
    print(f"Updated iframe HTML length: {len(html):,}")

    save_text(IFRAME_HTML, html)

    # This is the actual test that matters.
    if COUNTRY_ID in html:
        print("SUCCESS: international country dropdown is now present.")
        return True

    print("Country dropdown still not present after activating tab.")

    # Print useful diagnostic information.
    for term in [
        "ddlMeDoOdrediste",
        "chbMeDoAvionski",
        "tbxMeDoAvioTezina",
        "Izračunaj",
        "Međunarodni promet",
    ]:
        print(f"'{term}' -> {html.count(term)}")

    return False


async def find_country_dropdown(frame):
    """
    Find the international destination dropdown.
    """

    section("LOCATING COUNTRY DROPDOWN")

    selectors = [
        f"#{COUNTRY_ID}",
        "select[name='ddlMeDoOdrediste']",
        "select[id*='MeDoOdrediste']",
        "select[name*='MeDoOdrediste']",
    ]

    for selector in selectors:
        try:
            loc = frame.locator(selector)

            if await loc.count() > 0:
                print(f"FOUND country dropdown: {selector}")
                return loc.first
        except Exception:
            pass

    # Last resort: inspect every select.
    selects = frame.locator("select")
    count = await selects.count()

    print(f"Number of select elements: {count}")

    for i in range(count):
        select = selects.nth(i)

        try:
            element_id = await select.get_attribute("id")
            name = await select.get_attribute("name")

            print(f"select #{i}: id={element_id!r} name={name!r}")

            if (
                element_id == COUNTRY_ID
                or name == COUNTRY_ID
                or "Odrediste" in (element_id or "")
                or "Odrediste" in (name or "")
            ):
                return select
        except Exception:
            pass

    return None


async def extract_countries(country_select):
    """
    Extract the country names exactly in the order in which they
    appear in the website dropdown.

    No alphabetical sorting.
    """

    section("EXTRACTING DESTINATIONS")

    options = country_select.locator("option")
    count = await options.count()

    print(f"Number of country options: {count}")

    countries = []

    for i in range(count):
        option = options.nth(i)

        value = await option.get_attribute("value")
        text = clean_text(await option.inner_text())

        if text:
            countries.append(
                {
                    "index": i,
                    "name": text,
                    "value": value or "",
                }
            )

    print(f"Countries extracted: {len(countries)}")

    for country in countries:
        print(
            f"[{country['index']:03d}] "
            f"{country['name']} "
            f"(value={country['value']})"
        )

    return countries


async def find_postcard_control(frame):
    """
    Find the image/button representing Dopisnica.

    Diagnostic showed:

        input type=image
        id=ImageButton4
        title=Dopisnica

    But we don't depend exclusively on that ID.
    """

    for title in POSTCARD_TITLES:
        selectors = [
            f"input[type='image'][title='{title}']",
            f"input[type='image'][alt='{title}']",
            f"img[title='{title}']",
            f"img[alt='{title}']",
        ]

        for selector in selectors:
            try:
                loc = frame.locator(selector)

                if await loc.count() > 0:
                    item = loc.first

                    if await item.is_visible():
                        print(f"FOUND postcard control: {selector}")
                        return item
            except Exception:
                pass

    # Known ID from diagnostic.
    try:
        loc = frame.locator("#ImageButton4")

        if await loc.count() > 0:
            print("FOUND postcard control: #ImageButton4")
            return loc.first
    except Exception:
        pass

    return None


async def find_air_checkbox(frame):
    """
    Find the international Avionski prijenos checkbox.
    """

    selectors = [
        "#chbMeDoAvionski",
        "input[name='chbMeDoAvionski']",
        "input[id*='MeDoAvionski']",
        "input[name*='MeDoAvionski']",
    ]

    for selector in selectors:
        try:
            loc = frame.locator(selector)

            if await loc.count() > 0:
                return loc.first
        except Exception:
            pass

    return None


async def find_air_weight(frame):
    """
    Find the international air-weight input.
    """

    selectors = [
        "#tbxMeDoAvioTezina",
        "input[name='tbxMeDoAvioTezina']",
        "input[id*='MeDoAvioTezina']",
        "input[name*='MeDoAvioTezina']",
    ]

    for selector in selectors:
        try:
            loc = frame.locator(selector)

            if await loc.count() > 0:
                return loc.first
        except Exception:
            pass

    return None


async def find_international_calculate_button(frame):
    """
    Find the international Izračunaj button.

    Do not assume the domestic btnUnObPiIzracunaj.
    """

    selectors = [
        "#btnMeDoIzracunaj",
        "#btnMeObPiIzracunaj",
        "input[type='submit'][value='Izračunaj']",
        "input[type='submit'][value*='Izračun']",
    ]

    for selector in selectors:
        try:
            loc = frame.locator(selector)

            count = await loc.count()

            for i in range(count):
                item = loc.nth(i)

                try:
                    if await item.is_visible():
                        print(
                            f"FOUND calculate button: "
                            f"{selector} #{i}"
                        )
                        return item
                except Exception:
                    pass
        except Exception:
            pass

    return None


async def find_error_text(frame):
    """
    Search the rendered calculator text for the exact error message.
    """

    try:
        body_text = await frame.locator("body").inner_text()
    except Exception:
        body_text = ""

    return ERROR_MESSAGE in body_text


async def configure_postcard_and_air(frame):
    """
    Configure:
        Dopisnica/Postcard
        Avionski prijenos
        10 grams

    Returns True if all required controls were found.
    """

    postcard = await find_postcard_control(frame)

    if postcard is None:
        print("ERROR: Dopisnica/Postcard control not found.")
        return False

    print("Activating Dopisnica/Postcard...")

    try:
        await postcard.click()
    except Exception:
        try:
            await postcard.evaluate("(el) => el.click()")
        except Exception as exc:
            print(f"Could not activate postcard: {exc}")
            return False

    await wait_for_network(frame.page, SHORT_WAIT * 1000)

    # After selecting the service, controls may have changed.
    checkbox = await find_air_checkbox(frame)

    if checkbox is None:
        print("ERROR: Avionski prijenos checkbox not found.")
        return False

    print("Avionski prijenos checkbox found.")

    try:
        if not await checkbox.is_checked():
            print("Checking Avionski prijenos...")
            await checkbox.check()
            await wait_for_network(frame.page, SHORT_WAIT * 1000)
    except Exception as exc:
        print(f"Could not check air checkbox normally: {exc}")

        try:
            await checkbox.click()
            await wait_for_network(frame.page, SHORT_WAIT * 1000)
        except Exception as exc2:
            print(f"Could not click air checkbox: {exc2}")
            return False

    weight = await find_air_weight(frame)

    if weight is None:
        print("ERROR: air weight input not found.")
        return False

    print(f"Entering air weight: {WEIGHT_GRAMS} g")

    try:
        await weight.fill(WEIGHT_GRAMS)
    except Exception as exc:
        print(f"Could not fill weight normally: {exc}")
        return False

    return True


async def calculate_country(page, frame, country):
    """
    Test one country.

    Returns:
        True  = exact unavailable-country error was displayed
        False = it was not displayed
        None  = test could not be completed reliably
    """

    name = country["name"]
    value = country["value"]

    print()
    print("-" * 70)
    print(f"TESTING: {name}")
    print(f"VALUE:   {value}")
    print("-" * 70)

    country_select = await find_country_dropdown(frame)

    if country_select is None:
        print("ERROR: country dropdown disappeared.")
        return None

    # Select destination.
    try:
        await country_select.select_option(value=value)
    except Exception as exc:
        print(f"select_option failed for value {value!r}: {exc}")

        # Try by label.
        try:
            await country_select.select_option(label=name)
        except Exception as exc2:
            print(f"select by label also failed: {exc2}")
            return None

    await wait_for_network(page, 1200)

    # Selecting a destination can itself trigger an ASP.NET
    # postback. Re-find the controls afterward.
    if not await configure_postcard_and_air(frame):
        return None

    button = await find_international_calculate_button(frame)

    if button is None:
        print("ERROR: international Izračunaj button not found.")
        return None

    # Remove stale error/result state if possible by simply proceeding
    # with the new calculation.
    print("Clicking Izračunaj...")

    try:
        await button.click()
    except Exception as exc:
        print(f"Normal calculate click failed: {exc}")

        try:
            await button.evaluate("(el) => el.click()")
        except Exception as exc2:
            print(f"JavaScript calculate click failed: {exc2}")
            return None

    # Wait for ASP.NET response/update.
    await wait_for_network(page, 2000)

    # Search visible rendered text.
    unavailable = await find_error_text(frame)

    if unavailable:
        print("RESULT: UNAVAILABLE")
        print(f"Found exact message: {ERROR_MESSAGE}")
        return True

    print("RESULT: PRICE / OTHER RESPONSE")

    # Print a small result-area diagnostic, without flooding the log.
    try:
        text = clean_text(await frame.locator("body").inner_text())

        if len(text) > 5000:
            text = text[-5000:]

        print("Current calculator text:")
        print(text)
    except Exception:
        pass

    return False


def write_countries_file(all_countries, unavailable):
    """
    Write exactly two ordered lists.

    The order is the same as the website dropdown.

    This file is intended for ChangeDetection.io / changedetection.io,
    so keep the format stable and human-readable.
    """

    unavailable_names = {item["name"] for item in unavailable}

    lines = []

    lines.append("ALL DESTINATIONS")
    lines.append("=" * 70)

    for country in all_countries:
        lines.append(country["name"])

    lines.append("")
    lines.append("")
    lines.append("DESTINATIONS WITH ERROR")
    lines.append("=" * 70)

    for country in all_countries:
        if country["name"] in unavailable_names:
            lines.append(country["name"])

    lines.append("")

    COUNTRIES_FILE.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    print()
    print("=" * 70)
    print("COUNTRIES FILE")
    print("=" * 70)
    print(f"Saved: {COUNTRIES_FILE}")
    print(f"All destinations: {len(all_countries)}")
    print(f"Unavailable: {len(unavailable)}")


async def main():
    section("JP BH POŠTA CALCULATOR MONITOR")

    print(f"URL: {URL}")

    if not URL:
        raise RuntimeError("CALCULATOR_URL is empty")

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

        # --------------------------------------------------------
        # MAIN PAGE
        # --------------------------------------------------------

        section("OPENING MAIN PAGE")

        response = await page.goto(
            URL,
            wait_until="domcontentloaded",
            timeout=PAGE_TIMEOUT,
        )

        print(f"HTTP status: {response.status if response else 'unknown'}")
        print(f"Final URL: {page.url}")
        print(f"Page title: {await page.title()}")

        await wait_for_network(page, 2500)

        # Save main page.
        main_html = await page.content()
        save_text(PAGE_HTML, main_html)

        print(f"Saved: {PAGE_HTML} ({len(main_html):,} bytes)")

        # --------------------------------------------------------
        # LOCATE IFRAME
        # --------------------------------------------------------

        frame = await find_calculator_frame(page)

        if frame is None:
            await page.screenshot(
                path=str(SCREENSHOT),
                full_page=True,
            )

            raise RuntimeError(
                "Calculator iframe not found. "
                "See page.html and diagnostic.png."
            )

        # --------------------------------------------------------
        # INITIAL IFRAME DIAGNOSTICS
        # --------------------------------------------------------

        await write_frame_diagnostics(frame)

        # --------------------------------------------------------
        # ACTIVATE INTERNATIONAL
        # --------------------------------------------------------

        international_ok = await activate_international_tab(
            page,
            frame,
        )

        if not international_ok:
            await page.screenshot(
                path=str(SCREENSHOT),
                full_page=True,
            )

            html = await safe_content(frame)

            save_text(IFRAME_HTML, html)

            raise RuntimeError(
                "Could not activate Međunarodni promet or "
                "country dropdown did not appear. "
                "See iframe.html, iframe.txt and diagnostic.png."
            )

        # --------------------------------------------------------
        # INTERNATIONAL CALCULATOR
        # --------------------------------------------------------

        section("INTERNATIONAL CALCULATOR")

        country_select = await find_country_dropdown(frame)

        if country_select is None:
            await page.screenshot(
                path=str(SCREENSHOT),
                full_page=True,
            )

            raise RuntimeError(
                "International country dropdown not found."
            )

        # --------------------------------------------------------
        # EXTRACT COUNTRIES
        # --------------------------------------------------------

        all_countries = await extract_countries(country_select)

        if not all_countries:
            raise RuntimeError(
                "Country dropdown was found but contained no countries."
            )

        # Safety check. Your current list was approximately 262.
        # Do not silently overwrite countries.txt if the website
        # suddenly returns a tiny/invalid list.
        if len(all_countries) < 100:
            raise RuntimeError(
                f"Only {len(all_countries)} destinations were found. "
                "This is probably a website/application failure, "
                "so countries.txt was NOT updated."
            )

        # --------------------------------------------------------
        # SAVE DIAGNOSTIC AFTER INTERNATIONAL TAB
        # --------------------------------------------------------

        html = await safe_content(frame)
        text = clean_text(await frame.locator("body").inner_text())

        save_text(IFRAME_HTML, html)
        save_text(IFRAME_TEXT, text)

        # --------------------------------------------------------
        # TEST COUNTRIES
        # --------------------------------------------------------

        section("TESTING ALL DESTINATIONS")

        unavailable = []
        failed = []

        for number, country in enumerate(all_countries, start=1):

            print()
            print(
                f"[{number}/{len(all_countries)}] "
                f"{country['name']}"
            )

            result = await calculate_country(
                page,
                frame,
                country,
            )

            if result is True:
                unavailable.append(country)

            elif result is None:
                failed.append(country)

            # Small pause to avoid hammering the calculator.
            await page.wait_for_timeout(700)

        # --------------------------------------------------------
        # RESULTS
        # --------------------------------------------------------

        section("FINAL RESULTS")

        print(f"Total destinations: {len(all_countries)}")
        print(f"Unavailable destinations: {len(unavailable)}")
        print(f"Failed tests: {len(failed)}")

        if failed:
            print()
            print("FAILED TESTS:")
            for country in failed:
                print(f"  - {country['name']}")

        # IMPORTANT:
        # If any country could not be tested, don't publish a
        # potentially incomplete result as if it were valid.
        if failed:
            await page.screenshot(
                path=str(SCREENSHOT),
                full_page=True,
            )

            raise RuntimeError(
                f"{len(failed)} country test(s) failed. "
                "countries.txt was NOT updated."
            )

        # --------------------------------------------------------
        # WRITE OUTPUT
        # --------------------------------------------------------

        write_countries_file(
            all_countries,
            unavailable,
        )

        # --------------------------------------------------------
        # FINAL DIAGNOSTICS
        # --------------------------------------------------------

        await page.screenshot(
            path=str(SCREENSHOT),
            full_page=True,
        )

        final_html = await safe_content(frame)
        save_text(IFRAME_HTML, final_html)

        diagnostic_lines = [
            "JP BH POSTA CALCULATOR MONITOR",
            "",
            f"URL: {URL}",
            f"Final URL: {page.url}",
            f"Calculator iframe URL: {frame.url}",
            "",
            f"Total destinations: {len(all_countries)}",
            f"Unavailable destinations: {len(unavailable)}",
            f"Failed tests: {len(failed)}",
            "",
            "Unavailable destinations:",
        ]

        for country in unavailable:
            diagnostic_lines.append(country["name"])

        diagnostic_lines.append("")
        diagnostic_lines.append("Failed destinations:")

        for country in failed:
            diagnostic_lines.append(country["name"])

        save_text(
            DIAGNOSTIC,
            "\n".join(diagnostic_lines),
        )

        print()
        print("=" * 70)
        print("MONITOR COMPLETED SUCCESSFULLY")
        print("=" * 70)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
