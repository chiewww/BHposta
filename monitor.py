import asyncio
import os
import sys
from pathlib import Path

from playwright.async_api import (
    async_playwright,
    TimeoutError as PlaywrightTimeoutError,
)


# ============================================================
# CONFIGURATION
# ============================================================

URL = os.getenv(
    "CALCULATOR_URL",
    "https://www.posta.ba/kalkulator-cijena/",
)

OUTPUT_FILE = Path("posta-countries.txt")

NAVIGATION_TIMEOUT = 30_000
DEFAULT_TIMEOUT = 10_000
FRAME_WAIT_TIMEOUT = 30_000
CALCULATION_TIMEOUT = 10_000

BETWEEN_DESTINATIONS_MS = 300

UNAVAILABLE_MESSAGE = (
    "Prijem pošiljaka se trenutno ne vrši za odabranu državu"
)

CALCULATOR_IFRAME_URL_PART = (
    "bhpwebout.posta.ba/KalkulatorCijena_WEB_app"
)


# ============================================================
# ACTUAL CONTROLS PROVIDED FROM THE WEBSITE
# ============================================================

INTERNATIONAL_TEXT = "Međunarodni promet"

DOPISNICA_SELECTOR = "#ImageButton8"

COUNTRY_SELECTOR = "#ddlMeDoOdrediste"

AIR_TRANSPORT_SELECTOR = "#chbMeDoAvionski"

WEIGHT_SELECTOR = "#tbxMeDoAvioTezina"

CALCULATE_SELECTOR = "#btnMeDoIzracunaj"


# ============================================================
# HELPERS
# ============================================================

def clean_text(value):
    """
    Normalize only whitespace around/inside text.

    For country names, the actual option text is preserved as much
    as possible. We do NOT sort, deduplicate, or otherwise modify
    the dropdown entries.
    """
    return " ".join((value or "").split())


def save_output(dropdown, unavailable):
    """
    Write the single file that changedetection.io will monitor.

    List 1:
        Every dropdown entry, exact order.

    List 2:
        Only countries for which the exact unavailable message
        appeared after clicking Izračunaj.
    """

    lines = []

    lines.append("DROPDOWN")

    for country in dropdown:
        lines.append(country)

    lines.append("")
    lines.append("UNAVAILABLE")

    for country in unavailable:
        lines.append(country)

    text = "\n".join(lines) + "\n"

    OUTPUT_FILE.write_text(
        text,
        encoding="utf-8",
    )

    print(
        f"Saved {OUTPUT_FILE} "
        f"({len(text):,} bytes)"
    )


async def get_body_text(frame):
    try:
        return await frame.locator(
            "body"
        ).inner_text(
            timeout=DEFAULT_TIMEOUT
        )
    except Exception:
        return ""


# ============================================================
# FIND CALCULATOR IFRAME
# ============================================================

async def find_calculator_frame(page):
    """
    Locate the BH Pošta calculator iframe.

    The iframe can initially appear as about:blank, so we repeatedly
    inspect all frames.
    """

    print("Locating calculator iframe...")

    for attempt in range(1, 31):

        frames = page.frames

        print(
            f"Frame search {attempt}/30 "
            f"({len(frames)} frames)"
        )

        # ----------------------------------------------------
        # First: known iframe URL
        # ----------------------------------------------------

        for index, frame in enumerate(frames):

            frame_url = frame.url or ""

            if (
                CALCULATOR_IFRAME_URL_PART.casefold()
                in frame_url.casefold()
            ):
                print(
                    f"Calculator iframe found: frame {index}"
                )

                print(
                    f"URL: {frame_url}"
                )

                return frame

        # ----------------------------------------------------
        # Second: inspect HTML for calculator controls
        # ----------------------------------------------------

        for index, frame in enumerate(frames):

            try:
                html = await frame.content()
            except Exception:
                continue

            if not html:
                continue

            markers = (
                "ddlMeDoOdrediste",
                "tbxMeDoAvioTezina",
                "btnMeDoIzracunaj",
                "ImageButton8",
                "Međunarodni promet",
            )

            if any(
                marker in html
                for marker in markers
            ):
                print(
                    f"Calculator iframe found by HTML: "
                    f"frame {index}"
                )

                print(
                    f"URL: {frame.url}"
                )

                return frame

        await page.wait_for_timeout(1_000)

    return None


# ============================================================
# SELECT MEĐUNARODNI PROMET
# ============================================================

async def activate_international(frame):
    """
    Click the visible 'Međunarodni promet' tab.

    The site uses DevExpress/ASP.NET controls, so we intentionally
    target the visible text rather than guessing a generated ID.
    """

    print()
    print("Selecting Međunarodni promet...")

    # --------------------------------------------------------
    # Exact visible text
    # --------------------------------------------------------

    try:
        candidates = frame.get_by_text(
            INTERNATIONAL_TEXT,
            exact=True,
        )

        count = await candidates.count()

        print(
            f"International text candidates: {count}"
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

            # Try normal click first.
            try:
                await candidate.click(
                    timeout=DEFAULT_TIMEOUT,
                )

                print(
                    "Clicked Međunarodni promet."
                )

                await frame.page.wait_for_timeout(
                    1_500
                )

                return True

            except Exception as exc:
                print(
                    f"Normal click failed: {exc}"
                )

            # Try forced click.
            try:
                await candidate.click(
                    timeout=DEFAULT_TIMEOUT,
                    force=True,
                )

                print(
                    "Clicked Međunarodni promet "
                    "using force=True."
                )

                await frame.page.wait_for_timeout(
                    1_500
                )

                return True

            except Exception as exc:
                print(
                    f"Forced click failed: {exc}"
                )

            # Try clickable ancestors.
            for xpath in (
                "xpath=ancestor::a[1]",
                "xpath=ancestor::td[1]",
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
                        1_500
                    )

                    return True

                except Exception:
                    continue

    except Exception as exc:
        print(
            f"Exact international search failed: {exc}"
        )

    # --------------------------------------------------------
    # Generic fallback
    # --------------------------------------------------------

    try:
        locator = frame.locator(
            "span, a, td, div"
        )

        count = await locator.count()

        for i in range(count):

            element = locator.nth(i)

            try:
                if not await element.is_visible():
                    continue

                text = clean_text(
                    await element.inner_text()
                )

                if text != INTERNATIONAL_TEXT:
                    continue

                await element.click(
                    timeout=DEFAULT_TIMEOUT,
                    force=True,
                )

                print(
                    "Clicked Međunarodni promet "
                    "using generic element search."
                )

                await frame.page.wait_for_timeout(
                    1_500
                )

                return True

            except Exception:
                continue

    except Exception as exc:
        print(
            f"Generic international search failed: {exc}"
        )

    return False


# ============================================================
# SELECT DOPISNICA
# ============================================================

async def activate_dopisnica(frame):
    """
    Select the Dopisnica calculator.

    Actual control supplied by the user:

        #ImageButton8

    This is an image submit control, so clicking it can trigger
    an ASP.NET postback.
    """

    print()
    print("Selecting Dopisnica...")

    try:
        button = frame.locator(
            DOPISNICA_SELECTOR
        )

        count = await button.count()

        print(
            f"Dopisnica controls found: {count}"
        )

        if count == 0:
            return False

        await button.first.scroll_into_view_if_needed()

        try:
            await button.first.click(
                timeout=DEFAULT_TIMEOUT,
            )
        except Exception as exc:
            print(
                f"Normal Dopisnica click failed: {exc}"
            )

            await button.first.click(
                timeout=DEFAULT_TIMEOUT,
                force=True,
            )

        print(
            "Clicked Dopisnica."
        )

        # Give ASP.NET AJAX/postback time to update.
        await frame.page.wait_for_timeout(
            2_000
        )

        return True

    except Exception as exc:
        print(
            f"Could not select Dopisnica: {exc}"
        )

        return False


# ============================================================
# WAIT FOR COUNTRY DROPDOWN
# ============================================================

async def wait_for_country_dropdown(
    frame,
    timeout_ms=FRAME_WAIT_TIMEOUT,
):
    """
    Wait until the actual international country selector exists
    and contains options.
    """

    print()
    print("Waiting for international country dropdown...")

    deadline = (
        asyncio.get_running_loop().time()
        + timeout_ms / 1000
    )

    while (
        asyncio.get_running_loop().time()
        < deadline
    ):

        try:
            selector = frame.locator(
                COUNTRY_SELECTOR
            )

            if await selector.count() > 0:

                try:
                    if await selector.first.is_visible():

                        option_count = (
                            await selector.first.locator(
                                "option"
                            ).count()
                        )

                        print(
                            f"Country dropdown found "
                            f"with {option_count} options."
                        )

                        if option_count > 0:
                            return selector.first

                except Exception:
                    pass

        except Exception:
            pass

        await frame.page.wait_for_timeout(
            500
        )

    return None


# ============================================================
# READ DROPDOWN
# ============================================================

async def read_dropdown(country_select):
    """
    Read EVERY option exactly in the order supplied by the site.

    IMPORTANT:
    There is deliberately NO deduplication here.

    If the website contains:

        ASCENSION
        Ascension

    both remain.

    If the website contains duplicate values with different labels,
    both remain.

    We use the visible option text, because that is what the user
    wants monitored.
    """

    print()
    print("Reading country dropdown...")

    options = country_select.locator(
        "option"
    )

    count = await options.count()

    print(
        f"Option elements found: {count}"
    )

    dropdown = []

    for i in range(count):

        option = options.nth(i)

        try:
            text = await option.inner_text()

            # Preserve the actual displayed country name while
            # removing only surrounding/HTML whitespace.
            text = clean_text(text)

            if text:
                dropdown.append(text)

        except Exception as exc:
            print(
                f"Could not read option {i}: {exc}"
            )

    print(
        f"Read {len(dropdown)} dropdown entries."
    )

    return dropdown


# ============================================================
# SELECT AIR TRANSPORT
# ============================================================

async def select_air_transport(frame):
    """
    Ensure 'Avionski prijenos' is selected.

    Actual checkbox:

        #chbMeDoAvionski
    """

    checkbox = frame.locator(
        AIR_TRANSPORT_SELECTOR
    )

    if await checkbox.count() == 0:
        raise RuntimeError(
            "Avionski prijenos checkbox "
            "was not found."
        )

    checkbox = checkbox.first

    try:
        checked = await checkbox.is_checked()

        if not checked:
            print(
                "Selecting Avionski prijenos..."
            )

            await checkbox.check(
                timeout=DEFAULT_TIMEOUT,
                force=True,
            )

            await frame.page.wait_for_timeout(
                300
            )

        else:
            print(
                "Avionski prijenos already selected."
            )

    except Exception as exc:
        print(
            f"Checkbox check failed: {exc}"
        )

        # Fallback to click.
        await checkbox.click(
            timeout=DEFAULT_TIMEOUT,
            force=True,
        )

        await frame.page.wait_for_timeout(
            300
        )


# ============================================================
# SET 10 GRAMS
# ============================================================

async def set_weight_10g(frame):
    """
    Enter 10 into the actual international air weight field.
    """

    weight = frame.locator(
        WEIGHT_SELECTOR
    )

    if await weight.count() == 0:
        raise RuntimeError(
            "Avionski prijenos weight field "
            "was not found."
        )

    weight = weight.first

    print(
        "Entering 10 g..."
    )

    await weight.fill(
        "10",
        timeout=DEFAULT_TIMEOUT,
    )

    # Trigger normal browser input/change events.
    await weight.press(
        "Tab"
    )

    await frame.page.wait_for_timeout(
        300
    )


# ============================================================
# CALCULATE
# ============================================================

async def click_calculate(frame):
    """
    Click the actual Izračunaj button.
    """

    button = frame.locator(
        CALCULATE_SELECTOR
    )

    if await button.count() == 0:
        raise RuntimeError(
            "Izračunaj button "
            "was not found."
        )

    button = button.first

    print(
        "Clicking Izračunaj..."
    )

    await button.scroll_into_view_if_needed()

    try:
        await button.click(
            timeout=DEFAULT_TIMEOUT,
        )
    except Exception as exc:
        print(
            f"Normal calculate click failed: {exc}"
        )

        await button.click(
            timeout=DEFAULT_TIMEOUT,
            force=True,
        )


# ============================================================
# WAIT FOR CALCULATION RESULT
# ============================================================

async def wait_for_calculation_result(frame):
    """
    Wait until the exact unavailable message appears OR the page
    changes enough to indicate that the calculation has completed.

    We do NOT attempt to determine whether a result is available.

    We only care whether the exact unavailable message appears.
    """

    deadline = (
        asyncio.get_running_loop().time()
        + CALCULATION_TIMEOUT / 1000
    )

    last_text = ""

    while (
        asyncio.get_running_loop().time()
        < deadline
    ):

        await frame.page.wait_for_timeout(
            300
        )

        text = await get_body_text(
            frame
        )

        last_text = text

        if UNAVAILABLE_MESSAGE in text:
            return True, text

        # Check for the message even if it is split across
        # whitespace/newlines.
        normalized = " ".join(
            text.split()
        )

        if UNAVAILABLE_MESSAGE in normalized:
            return True, text

    return False, last_text


# ============================================================
# TEST ONE COUNTRY
# ============================================================

async def test_country(
    frame,
    country_select,
    country_name,
):
    """
    Test one dropdown entry.

    Returns True ONLY if the exact unavailable message appears.
    """

    print()
    print(
        f"Testing: {country_name}"
    )

    # --------------------------------------------------------
    # Select the country.
    #
    # We select by label/text rather than value because the output
    # must correspond exactly to the visible dropdown entry.
    #
    # If duplicate labels somehow exist, Playwright may require
    # value-based handling. In that case we fall back to matching
    # the actual option text.
    # --------------------------------------------------------

    try:
        await country_select.select_option(
            label=country_name,
            timeout=DEFAULT_TIMEOUT,
        )

    except Exception as exc:

        print(
            f"Could not select country by label: {exc}"
        )

        # Fallback: locate the exact option text and use its value.
        options = country_select.locator(
            "option"
        )

        option_count = await options.count()

        selected = False

        for i in range(option_count):

            option = options.nth(i)

            try:
                text = clean_text(
                    await option.inner_text()
                )

                if text != country_name:
                    continue

                value = await option.get_attribute(
                    "value"
                )

                if value is None:
                    await country_select.select_option(
                        index=i,
                        timeout=DEFAULT_TIMEOUT,
                    )
                else:
                    await country_select.select_option(
                        value=value,
                        timeout=DEFAULT_TIMEOUT,
                    )

                selected = True
                break

            except Exception:
                continue

        if not selected:
            print(
                f"FAILED TO SELECT: {country_name}"
            )

            return False

    # Selecting a country causes an ASP.NET postback on this site.
    await frame.page.wait_for_timeout(
        700
    )

    # The postback can replace controls, so reacquire them every time.
    await select_air_transport(frame)

    await set_weight_10g(frame)

    await click_calculate(frame)

    unavailable, result_text = (
        await wait_for_calculation_result(
            frame
        )
    )

    if unavailable:

        print(
            f"UNAVAILABLE MESSAGE FOUND: "
            f"{country_name}"
        )

        return True

    print(
        f"Unavailable message NOT found: "
        f"{country_name}"
    )

    return False


# ============================================================
# MAIN
# ============================================================

async def main():

    print("=" * 70)
    print("JP BH POŠTA DAILY COUNTRY MONITOR")
    print("=" * 70)

    print(
        f"URL: {URL}"
    )

    print(
        f"Output: {OUTPUT_FILE}"
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

        try:

            # ====================================================
            # OPEN WEBSITE
            # ====================================================

            print()
            print("Opening website...")

            try:
                await page.goto(
                    URL,
                    wait_until="domcontentloaded",
                    timeout=NAVIGATION_TIMEOUT,
                )

            except PlaywrightTimeoutError as exc:

                print(
                    "Navigation timeout occurred."
                )

                print(
                    "Continuing because the page may "
                    "already be usable."
                )

                print(
                    str(exc)
                )

            await page.wait_for_timeout(
                2_000
            )

            # ====================================================
            # FIND IFRAME
            # ====================================================

            frame = await find_calculator_frame(
                page
            )

            if frame is None:
                raise RuntimeError(
                    "Could not locate the BH Pošta "
                    "calculator iframe."
                )

            print()
            print(
                f"Calculator frame URL: {frame.url}"
            )

            # ====================================================
            # SELECT MEĐUNARODNI PROMET
            # ====================================================

            international_selected = (
                await activate_international(
                    frame
                )
            )

            if not international_selected:
                raise RuntimeError(
                    "Could not select "
                    "Međunarodni promet."
                )

            # ====================================================
            # SELECT DOPISNICA
            # ====================================================

            dopisnica_selected = (
                await activate_dopisnica(
                    frame
                )
            )

            if not dopisnica_selected:
                raise RuntimeError(
                    "Could not select "
                    "Dopisnica."
                )

            # ====================================================
            # WAIT FOR INTERNATIONAL DROPDOWN
            # ====================================================

            country_select = (
                await wait_for_country_dropdown(
                    frame
                )
            )

            if country_select is None:
                raise RuntimeError(
                    "International country dropdown "
                    "#ddlMeDoOdrediste was not found."
                )

            # ====================================================
            # LIST 1
            # ====================================================

            dropdown = await read_dropdown(
                country_select
            )

            if not dropdown:
                raise RuntimeError(
                    "Country dropdown is empty."
                )

            # ====================================================
            # WRITE LIST 1 IMMEDIATELY
            #
            # This ensures the file exists and contains the exact
            # dropdown even if something goes wrong later.
            # ====================================================

            save_output(
                dropdown,
                [],
            )

            # ====================================================
            # LIST 2
            # ====================================================

            unavailable = []

            print()
            print("=" * 70)
            print("TESTING COUNTRIES")
            print("=" * 70)

            # ----------------------------------------------------
            # IMPORTANT:
            #
            # We iterate over the dropdown entries exactly as read.
            #
            # No sorting.
            # No deduplication.
            # No filtering.
            #
            # If the website contains the same visible name twice,
            # both entries are tested.
            # ----------------------------------------------------

            for index, country_name in enumerate(
                dropdown,
                1,
            ):

                print()
                print(
                    f"[{index}] {country_name}"
                )

                try:

                    # Reacquire the selector because ASP.NET
                    # postbacks may replace DOM elements.
                    country_select = (
                        await wait_for_country_dropdown(
                            frame,
                            timeout_ms=15_000,
                        )
                    )

                    if country_select is None:
                        print(
                            "Country dropdown disappeared."
                        )

                        # Try returning to international calculator.
                        await activate_international(
                            frame
                        )

                        await frame.page.wait_for_timeout(
                            1_000
                        )

                        country_select = (
                            await wait_for_country_dropdown(
                                frame,
                                timeout_ms=15_000,
                            )
                        )

                    if country_select is None:
                        print(
                            f"Could not recover country "
                            f"dropdown for {country_name}."
                        )

                        continue

                    is_unavailable = (
                        await test_country(
                            frame,
                            country_select,
                            country_name,
                        )
                    )

                    if is_unavailable:

                        unavailable.append(
                            country_name
                        )

                    # ------------------------------------------------
                    # SAVE AFTER EVERY COUNTRY
                    #
                    # This keeps the output file current even if a
                    # later country causes an unexpected failure.
                    # ------------------------------------------------

                    save_output(
                        dropdown,
                        unavailable,
                    )

                    await page.wait_for_timeout(
                        BETWEEN_DESTINATIONS_MS
                    )

                except Exception as exc:

                    # An unexpected error for one country does NOT
                    # automatically put that country into UNAVAILABLE.
                    #
                    # Only the exact website message is allowed to
                    # add a country to List 2.

                    print(
                        f"ERROR testing {country_name}: "
                        f"{type(exc).__name__}: {exc}"
                    )

                    # Continue with the next country.
                    continue

            # ====================================================
            # FINAL OUTPUT
            # ====================================================

            save_output(
                dropdown,
                unavailable,
            )

            print()
            print("=" * 70)
            print("MONITOR COMPLETED")
            print("=" * 70)

            print(
                f"Output file: {OUTPUT_FILE}"
            )

        finally:

            try:
                await context.close()
            except Exception:
                pass

            try:
                await browser.close()
            except Exception:
                pass


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:
        asyncio.run(main())

    except KeyboardInterrupt:

        print(
            "Monitor interrupted."
        )

        sys.exit(130)
