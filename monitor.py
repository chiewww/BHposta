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

COUNTRIES_FILE = Path("countries.txt")
DIAGNOSTIC_FILE = Path("diagnostic.txt")
PAGE_FILE = Path("page.html")
IFRAME_FILE = Path("iframe.html")
IFRAME_TEXT_FILE = Path("iframe.txt")
SCREENSHOT_FILE = Path("diagnostic.png")

# A real country dropdown should have far more than this.
MIN_COUNTRY_OPTIONS = 50

# Maximum number of countries we will process.
# None means all countries.
MAX_COUNTRIES = None


# ============================================================
# OUTPUT HELPERS
# ============================================================

diagnostic_lines = []


def log(message=""):
    print(message)
    diagnostic_lines.append(str(message))


def section(title):
    log()
    log("=" * 70)
    log(title)
    log("=" * 70)


def save_diagnostic():
    try:
        DIAGNOSTIC_FILE.write_text(
            "\n".join(diagnostic_lines),
            encoding="utf-8",
        )
        print(f"Diagnostic saved: {DIAGNOSTIC_FILE}")
    except Exception as exc:
        print(f"Could not save diagnostic: {exc}")


def normalize_text(text):
    if text is None:
        return ""

    return re.sub(r"\s+", " ", text).strip()


# ============================================================
# FIND CALCULATOR FRAME
# ============================================================

async def find_calculator_frame(page):
    section("LOCATING CALCULATOR IFRAME")

    frames = page.frames

    log(f"Number of frames: {len(frames)}")

    # First preference:
    # The known calculator hostname.
    for index, frame in enumerate(frames):
        log(f"Checking frame {index}: {frame.url}")

        if "bhpwebout.posta.ba" in frame.url.lower():
            log(f"FOUND CALCULATOR FRAME: {index}")
            log(f"Calculator URL: {frame.url}")
            return frame

    # Second preference:
    # Look for a frame containing calculator-specific text.
    for index, frame in enumerate(frames):
        try:
            text = await frame.locator("body").inner_text(timeout=3000)
            text = normalize_text(text)

            if (
                "Kalkulator cijena" in text
                and "Međunarodni promet" in text
            ):
                log(f"FOUND CALCULATOR FRAME BY CONTENT: {index}")
                log(f"Calculator URL: {frame.url}")
                return frame

        except Exception:
            continue

    return None


# ============================================================
# SAVE FRAME INFORMATION
# ============================================================

async def save_frame_files(frame):
    section("SAVING CALCULATOR FRAME")

    try:
        html = await frame.content()
        IFRAME_FILE.write_text(html, encoding="utf-8")
        log(f"Saved {IFRAME_FILE} ({len(html):,} bytes)")
    except Exception as exc:
        log(f"Could not save iframe HTML: {exc}")

    try:
        text = await frame.locator("body").inner_text(timeout=5000)
        IFRAME_TEXT_FILE.write_text(text, encoding="utf-8")
        log(f"Saved {IFRAME_TEXT_FILE} ({len(text):,} bytes)")
    except Exception as exc:
        log(f"Could not save iframe text: {exc}")


# ============================================================
# ACTIVATE INTERNATIONAL TRAFFIC
# ============================================================

async def activate_international(frame):
    section("ACTIVATING MEĐUNARODNI PROMET")

    # The successful diagnostic showed:
    #
    # <span class="dx-vam">Međunarodni promet</span>
    #
    # Therefore we search by visible text, not by a fragile ID.

    candidates = frame.get_by_text(
        "Međunarodni promet",
        exact=True,
    )

    count = await candidates.count()

    log(f"Text candidate count: {count}")

    if count == 0:
        # Try a broader text search.
        candidates = frame.locator(
            "text=Međunarodni promet"
        )

        count = await candidates.count()

        log(f"Broader text candidate count: {count}")

    if count == 0:
        return False

    for i in range(count):
        candidate = candidates.nth(i)

        try:
            if await candidate.is_visible():
                log("Found visible Međunarodni promet element.")

                try:
                    log(f"Tag: {await candidate.evaluate('(el) => el.tagName')}")
                except Exception:
                    pass

                try:
                    log(f"HTML: {await candidate.evaluate('(el) => el.outerHTML')}")
                except Exception:
                    pass

                # Try normal click first.
                try:
                    await candidate.click(timeout=5000)
                except Exception:
                    # DevExpress controls sometimes have overlays.
                    await candidate.click(
                        timeout=5000,
                        force=True,
                    )

                # Give ASP.NET/DevExpress callback time to complete.
                await frame.wait_for_timeout(1500)

                return True

        except Exception as exc:
            log(f"Candidate {i} failed: {exc}")

    return False


# ============================================================
# FIND COUNTRY DROPDOWN
# ============================================================

async def find_country_dropdown(frame):
    section("LOCATING COUNTRY DROPDOWN")

    # IMPORTANT:
    #
    # We deliberately DO NOT look for:
    #
    #     #ddlMeDoOdrediste
    #
    # because the live page has demonstrated that this ID is
    # not reliable.
    #
    # Instead, inspect every <select> and identify the one
    # containing a large number of country options.

    selects = frame.locator("select")

    select_count = await selects.count()

    log(f"Number of <select> elements: {select_count}")

    candidates = []

    for i in range(select_count):
        select = selects.nth(i)

        try:
            option_count = await select.locator("option").count()

            select_id = await select.get_attribute("id")
            select_name = await select.get_attribute("name")

            log(
                f"SELECT {i}: "
                f"id={select_id!r}, "
                f"name={select_name!r}, "
                f"options={option_count}"
            )

            if option_count >= MIN_COUNTRY_OPTIONS:
                candidates.append((i, option_count))

        except Exception as exc:
            log(f"Could not inspect select {i}: {exc}")

    if not candidates:
        log()
        log("No large <select> element found.")

        # Extra diagnostic information.
        try:
            html = await frame.content()

            marker = "odredišna"
            position = html.lower().find(marker.lower())

            if position >= 0:
                start = max(0, position - 5000)
                end = min(len(html), position + 15000)

                log()
                log("HTML AROUND 'odredišna':")
                log(html[start:end])

        except Exception as exc:
            log(f"Could not inspect HTML: {exc}")

        return None

    # Pick the candidate with the largest number of options.
    candidates.sort(key=lambda item: item[1], reverse=True)

    selected_index, selected_count = candidates[0]

    log()
    log(
        f"COUNTRY DROPDOWN CANDIDATE: "
        f"select index {selected_index}, "
        f"{selected_count} options"
    )

    return selects.nth(selected_index)


# ============================================================
# EXTRACT COUNTRY OPTIONS
# ============================================================

async def extract_countries(country_select):
    section("EXTRACTING DESTINATION COUNTRIES")

    options = country_select.locator("option")

    count = await options.count()

    log(f"Total dropdown options: {count}")

    countries = []

    for i in range(count):
        option = options.nth(i)

        try:
            text = normalize_text(await option.inner_text())
            value = await option.get_attribute("value")

            if not text:
                continue

            log(
                f"[{i}] value={value!r} text={text!r}"
            )

            countries.append(
                {
                    "index": i,
                    "value": value,
                    "text": text,
                }
            )

        except Exception as exc:
            log(f"Could not read option {i}: {exc}")

    log()
    log(f"COUNTRY COUNT: {len(countries)}")

    # Preserve EXACT dropdown order.
    return countries


# ============================================================
# SAVE ALL COUNTRIES
# ============================================================

def save_countries_file(countries, unavailable):
    section("WRITING countries.txt")

    lines = []

    lines.append("ALL DESTINATION COUNTRIES")
    lines.append("=========================")
    lines.append("")

    for country in countries:
        lines.append(country["text"])

    lines.append("")
    lines.append("")
    lines.append(
        f"TOTAL DESTINATION COUNTRIES: {len(countries)}"
    )

    lines.append("")
    lines.append("")
    lines.append("COUNTRIES WITH ERROR")
    lines.append("====================")
    lines.append("")

    for country in unavailable:
        lines.append(country["text"])

    lines.append("")
    lines.append("")
    lines.append(
        f"TOTAL WITH ERROR: {len(unavailable)}"
    )

    COUNTRIES_FILE.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    log(
        f"Saved {COUNTRIES_FILE} "
        f"({len(lines)} lines)"
    )


# ============================================================
# FIND CALCULATE BUTTON
# ============================================================

async def find_calculate_button(frame):
    # First try the actual submit value.
    selectors = [
        "input[type='submit'][value='Izračunaj']",
        "input[type='submit']",
        "input.dugme",
    ]

    for selector in selectors:
        locator = frame.locator(selector)

        count = await locator.count()

        if count:
            for i in range(count):
                button = locator.nth(i)

                try:
                    if await button.is_visible():
                        value = await button.get_attribute("value")

                        if (
                            value is None
                            or "izračun" in value.lower()
                        ):
                            return button

                except Exception:
                    continue

    # Last fallback: locate by text/value.
    buttons = frame.get_by_text(
        "Izračunaj",
        exact=True,
    )

    count = await buttons.count()

    for i in range(count):
        button = buttons.nth(i)

        try:
            if await button.is_visible():
                return button
        except Exception:
            continue

    return None


# ============================================================
# GET CURRENT CALCULATOR TEXT
# ============================================================

async def get_calculator_text(frame):
    try:
        return normalize_text(
            await frame.locator("body").inner_text(
                timeout=5000
            )
        )
    except Exception:
        return ""


# ============================================================
# DETECT ERROR MESSAGE
# ============================================================

async def error_is_present(frame):
    # Direct text search.
    try:
        locator = frame.get_by_text(
            ERROR_MESSAGE,
            exact=False,
        )

        count = await locator.count()

        for i in range(count):
            try:
                if await locator.nth(i).is_visible():
                    return True
            except Exception:
                pass

    except Exception:
        pass

    # Body-text fallback.
    text = await get_calculator_text(frame)

    return ERROR_MESSAGE in text


# ============================================================
# SELECT COUNTRY
# ============================================================

async def select_country(country_select, country):
    value = country["value"]
    text = country["text"]

    # Prefer value because it is less ambiguous.
    if value is not None:
        try:
            await country_select.select_option(
                value=value,
                timeout=5000,
            )
            return
        except Exception:
            pass

    # Fall back to visible text.
    await country_select.select_option(
        label=text,
        timeout=5000,
    )


# ============================================================
# CLEAR PREVIOUS RESULT
# ============================================================

async def clear_previous_result(frame):
    # The calculator is an ASP.NET application. The result/error
    # may remain in the DOM after a previous calculation.
    #
    # We therefore simply allow the next calculation to replace it.
    #
    # A short delay also prevents requests from being fired too
    # quickly.

    await frame.wait_for_timeout(200)


# ============================================================
# CALCULATE ONE COUNTRY
# ============================================================

async def calculate_country(frame, country_select, country, index, total):
    name = country["text"]

    log(
        f"[{index}/{total}] "
        f"Testing: {name}"
    )

    await select_country(
        country_select,
        country,
    )

    await clear_previous_result(frame)

    button = await find_calculate_button(frame)

    if button is None:
        raise RuntimeError(
            "Could not find the Izračunaj button."
        )

    # Remember current URL in case the form navigates.
    old_url = frame.url

    try:
        await button.click(
            timeout=10000,
        )
    except Exception:
        await button.click(
            timeout=10000,
            force=True,
        )

    # Wait for ASP.NET postback / response.
    await frame.wait_for_timeout(1200)

    # Wait briefly for the error text if it is going to appear.
    try:
        await frame.get_by_text(
            ERROR_MESSAGE,
            exact=False,
        ).first.wait_for(
            state="visible",
            timeout=1500,
        )
    except Exception:
        pass

    has_error = await error_is_present(frame)

    if has_error:
        log(
            f"    -> ERROR: "
            f"{ERROR_MESSAGE}"
        )
    else:
        log("    -> no error")

    # If the calculator navigated, wait for it.
    if frame.url != old_url:
        try:
            await frame.wait_for_load_state(
                "domcontentloaded",
                timeout=5000,
            )
        except Exception:
            pass

    return has_error


# ============================================================
# DEBUG SELECT ELEMENT
# ============================================================

async def dump_selects(frame):
    section("SELECT DIAGNOSTIC")

    selects = frame.locator("select")

    count = await selects.count()

    log(f"Select count: {count}")

    for i in range(count):
        select = selects.nth(i)

        try:
            outer = await select.evaluate(
                "(el) => el.outerHTML"
            )

            # Limit output to avoid enormous logs.
            if len(outer) > 20000:
                outer = outer[:20000] + "\n...[TRUNCATED]..."

            log()
            log(f"SELECT {i}:")
            log(outer)

        except Exception as exc:
            log(
                f"Could not dump select {i}: {exc}"
            )


# ============================================================
# MAIN
# ============================================================

async def main():
    section("JP BH POŠTA CALCULATOR MONITOR")

    log(f"URL: {URL}")

    if not URL:
        raise RuntimeError(
            "CALCULATOR_URL is empty."
        )

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True,
        )

        context = await browser.new_context(
            viewport={
                "width": 1440,
                "height": 1200,
            },
            locale="bs-BA",
        )

        page = await context.new_page()

        try:
            # ====================================================
            # OPEN MAIN PAGE
            # ====================================================

            section("OPENING MAIN PAGE")

            log("Opening page...")

            response = await page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            if response:
                log(
                    f"HTTP status: "
                    f"{response.status}"
                )

            log(
                f"Final URL: {page.url}"
            )

            log(
                f"Page title: "
                f"{await page.title()}"
            )

            await page.wait_for_timeout(2000)

            # Save main HTML.
            try:
                html = await page.content()

                PAGE_FILE.write_text(
                    html,
                    encoding="utf-8",
                )

                log(
                    f"Saved {PAGE_FILE} "
                    f"({len(html):,} bytes)"
                )

            except Exception as exc:
                log(
                    f"Could not save main HTML: {exc}"
                )

            # Screenshot page, not frame.
            try:
                await page.screenshot(
                    path=str(SCREENSHOT_FILE),
                    full_page=True,
                )

                log(
                    f"Screenshot saved: "
                    f"{SCREENSHOT_FILE}"
                )

            except Exception as exc:
                log(
                    f"Could not save screenshot: {exc}"
                )

            # ====================================================
            # FIND CALCULATOR FRAME
            # ====================================================

            frame = await find_calculator_frame(page)

            if frame is None:
                raise RuntimeError(
                    "Could not locate the calculator iframe."
                )

            # ====================================================
            # SAVE CALCULATOR FRAME
            # ====================================================

            await save_frame_files(frame)

            # ====================================================
            # CHECK WHETHER COUNTRY SELECT ALREADY EXISTS
            # ====================================================

            section("CHECKING INITIAL CALCULATOR")

            country_select = await find_country_dropdown(
                frame
            )

            if country_select is None:

                log(
                    "Country dropdown is not present yet."
                )

                log(
                    "Attempting to activate "
                    "Međunarodni promet."
                )

                activated = await activate_international(
                    frame
                )

                if not activated:
                    raise RuntimeError(
                        "Could not activate "
                        "Međunarodni promet."
                    )

                # Give the ASP.NET/DevExpress interface time
                # to update.
                await frame.wait_for_timeout(2000)

                # Save the resulting HTML.
                await save_frame_files(frame)

                # Try again.
                country_select = (
                    await find_country_dropdown(frame)
                )

            if country_select is None:

                # Extra diagnostics.
                await dump_selects(frame)

                try:
                    text = await get_calculator_text(frame)

                    log()
                    log(
                        "VISIBLE CALCULATOR TEXT:"
                    )
                    log(text[:30000])

                except Exception as exc:
                    log(
                        f"Could not get calculator text: {exc}"
                    )

                raise RuntimeError(
                    "Could not locate the country dropdown "
                    "after activating Međunarodni promet. "
                    "The script deliberately searches for "
                    "the large country <select> instead of "
                    "requiring #ddlMeDoOdrediste."
                )

            # ====================================================
            # EXTRACT COUNTRIES
            # ====================================================

            countries = await extract_countries(
                country_select
            )

            if not countries:
                raise RuntimeError(
                    "Country dropdown was found, "
                    "but it contains no usable countries."
                )

            if len(countries) < MIN_COUNTRY_OPTIONS:
                raise RuntimeError(
                    f"Only {len(countries)} dropdown "
                    f"options were found; expected a "
                    f"country list of at least "
                    f"{MIN_COUNTRY_OPTIONS}."
                )

            # Respect configured limit, if any.
            countries_to_test = countries

            if MAX_COUNTRIES is not None:
                countries_to_test = countries[
                    :MAX_COUNTRIES
                ]

            log()
            log(
                f"Countries discovered: "
                f"{len(countries)}"
            )

            log(
                f"Countries to test: "
                f"{len(countries_to_test)}"
            )

            # ====================================================
            # TEST COUNTRIES
            # ====================================================

            section(
                "TESTING ALL DESTINATION COUNTRIES"
            )

            unavailable = []

            total = len(countries_to_test)

            for number, country in enumerate(
                countries_to_test,
                start=1,
            ):

                try:
                    # The form may have been refreshed after a
                    # postback, so reacquire the dropdown every
                    # time if necessary.

                    current_select = (
                        await find_country_dropdown(frame)
                    )

                    if current_select is None:
                        raise RuntimeError(
                            "Country dropdown disappeared "
                            "before testing this country."
                        )

                    has_error = await calculate_country(
                        frame,
                        current_select,
                        country,
                        number,
                        total,
                    )

                    if has_error:
                        unavailable.append(country)

                except Exception as exc:
                    log()
                    log(
                        f"ERROR TESTING "
                        f"{country['text']}: {exc}"
                    )

                    # Save state before stopping.
                    try:
                        await save_frame_files(frame)
                    except Exception:
                        pass

                    raise

            # ====================================================
            # WRITE OUTPUT
            # ====================================================

            section("FINAL RESULTS")

            log(
                f"Total countries: "
                f"{len(countries)}"
            )

            log(
                f"Countries with error: "
                f"{len(unavailable)}"
            )

            log()
            log("COUNTRIES WITH ERROR:")

            for country in unavailable:
                log(
                    f"  {country['text']}"
                )

            save_countries_file(
                countries,
                unavailable,
            )

            # ====================================================
            # FINAL DIAGNOSTIC SAVE
            # ====================================================

            section("MONITOR COMPLETED")

            log(
                f"countries.txt contains "
                f"{len(countries)} destination countries "
                f"in the original dropdown order."
            )

            log(
                f"{len(unavailable)} countries returned "
                f"the specified unavailable-service error."
            )

        except Exception as exc:

            section("MONITOR FAILED")

            log(
                f"{type(exc).__name__}: {exc}"
            )

            # Save whatever HTML is currently available.
            try:
                await save_frame_files(frame)
            except Exception:
                pass

            try:
                await page.screenshot(
                    path=str(SCREENSHOT_FILE),
                    full_page=True,
                )
            except Exception:
                pass

            raise

        finally:
            save_diagnostic()

            await context.close()
            await browser.close()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    asyncio.run(main())
