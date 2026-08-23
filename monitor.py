import asyncio
import os
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

OUTPUT_FILE = Path("posta-countries.txt")

NAVIGATION_TIMEOUT = 30_000
DEFAULT_TIMEOUT = 5_000
FRAME_WAIT_TIMEOUT = 30_000

# How long to wait after clicking "Izračunaj" for the
# unavailable message to appear.
RESULT_WAIT_TIMEOUT = 3_000

# Small pause between countries.
BETWEEN_COUNTRIES_MS = 100

# Overall safety limit.
OVERALL_TIMEOUT = 45 * 60 * 1000

UNAVAILABLE_MESSAGE = (
    "Prijem pošiljaka se trenutno ne vrši za odabranu državu"
)


def save_text(path, text):
    path.write_text(
        text or "",
        encoding="utf-8",
    )


def clean_name(value):
    return " ".join(
        (value or "").split()
    ).strip()


async def frame_content(frame):
    try:
        return await frame.content()
    except Exception:
        return ""


async def find_calculator_frame(page):
    """
    Locate the BH Pošta calculator iframe.

    First tries the known iframe URL.
    Then falls back to inspecting frame HTML.
    """

    print("Locating calculator iframe...")

    for attempt in range(1, 31):
        frames = page.frames

        print(
            f"Frame search {attempt}/30 "
            f"({len(frames)} frames)"
        )

        # --------------------------------------------------------
        # First choice: known calculator iframe URL.
        # --------------------------------------------------------

        for index, frame in enumerate(frames):
            url = frame.url or ""

            if (
                CALCULATOR_IFRAME_URL_PART.casefold()
                in url.casefold()
            ):
                print(
                    f"Calculator iframe found: "
                    f"frame {index}"
                )
                print(f"URL: {url}")
                return frame

        # --------------------------------------------------------
        # Second choice: inspect HTML.
        # --------------------------------------------------------

        for index, frame in enumerate(frames):
            html = await frame_content(frame)

            if not html:
                continue

            markers = (
                "ddlMeDoOdrediste",
                "btnMeDoIzracunaj",
                "tbxMeDoAvioTezina",
                "chbMeDoAvionski",
                "Međunarodni promet",
            )

            if any(
                marker in html
                for marker in markers
            ):
                print(
                    f"Calculator iframe found "
                    f"by HTML: frame {index}"
                )
                print(
                    f"URL: {frame.url}"
                )
                return frame

        await page.wait_for_timeout(1_000)

    return None


async def click_international(frame):
    """
    Select the 'Međunarodni promet' tab.

    We deliberately do this before looking for the country
    dropdown because the international controls are not present
    until this tab is selected.
    """

    print()
    print("Selecting Međunarodni promet...")

    # ------------------------------------------------------------
    # Exact visible text.
    # ------------------------------------------------------------

    try:
        locator = frame.get_by_text(
            "Međunarodni promet",
            exact=True,
        )

        count = await locator.count()

        for i in range(count):
            item = locator.nth(i)

            try:
                if not await item.is_visible():
                    continue

                print(
                    "Found visible "
                    "Međunarodni promet."
                )

                try:
                    await item.click(
                        timeout=DEFAULT_TIMEOUT,
                        force=True,
                    )

                    await frame.page.wait_for_timeout(
                        500
                    )

                    print(
                        "Međunarodni promet selected."
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
                        parent = item.locator(
                            xpath
                        )

                        if await parent.count() == 0:
                            continue

                        await parent.first.click(
                            timeout=DEFAULT_TIMEOUT,
                            force=True,
                        )

                        await frame.page.wait_for_timeout(
                            500
                        )

                        print(
                            "Međunarodni promet "
                            "selected through ancestor."
                        )

                        return True

                    except Exception:
                        continue

            except Exception:
                continue

    except Exception as exc:
        print(
            f"Exact text lookup failed: {exc}"
        )

    # ------------------------------------------------------------
    # Generic fallback.
    # ------------------------------------------------------------

    try:
        elements = frame.locator(
            "span,td,a,div"
        )

        count = await elements.count()

        for i in range(count):
            element = elements.nth(i)

            try:
                if not await element.is_visible():
                    continue

                text = clean_name(
                    await element.inner_text()
                )

                if text != "Međunarodni promet":
                    continue

                await element.click(
                    timeout=DEFAULT_TIMEOUT,
                    force=True,
                )

                await frame.page.wait_for_timeout(
                    500
                )

                print(
                    "Međunarodni promet selected "
                    "through generic search."
                )

                return True

            except Exception:
                continue

    except Exception as exc:
        print(
            f"Generic international-tab "
            f"search failed: {exc}"
        )

    return False


async def click_dopisnica(frame):
    """
    Select Dopisnica.

    User supplied the actual control:

        <input type="image"
               name="ImageButton8"
               id="ImageButton8"
               title="Dopisnica"
               ...>
    """

    print()
    print("Selecting Dopisnica...")

    # ------------------------------------------------------------
    # Exact selector supplied by user.
    # ------------------------------------------------------------

    try:
        button = frame.locator(
            "#ImageButton8"
        )

        if await button.count() > 0:
            print(
                "Found #ImageButton8"
            )

            await button.first.click(
                timeout=DEFAULT_TIMEOUT,
                force=True,
            )

            # ASP.NET postback.
            await frame.page.wait_for_timeout(
                700
            )

            print(
                "Dopisnica selected."
            )

            return True

    except Exception as exc:
        print(
            f"#ImageButton8 click failed: {exc}"
        )

    # ------------------------------------------------------------
    # Fallback by title.
    # ------------------------------------------------------------

    try:
        button = frame.locator(
            "input[title='Dopisnica']"
        )

        if await button.count() > 0:
            await button.first.click(
                timeout=DEFAULT_TIMEOUT,
                force=True,
            )

            await frame.page.wait_for_timeout(
                700
            )

            print(
                "Dopisnica selected "
                "using title selector."
            )

            return True

    except Exception as exc:
        print(
            f"Dopisnica title fallback failed: "
            f"{exc}"
        )

    return False


async def find_country_select(frame):
    """
    Locate the exact international country dropdown supplied
    by the user:

        #ddlMeDoOdrediste
    """

    selector = frame.locator(
        "#ddlMeDoOdrediste"
    )

    try:
        if await selector.count() > 0:
            print(
                "Found country dropdown:"
                " #ddlMeDoOdrediste"
            )

            return selector.first

    except Exception:
        pass

    return None


async def wait_for_country_select(
    frame,
    timeout_ms=FRAME_WAIT_TIMEOUT,
):
    """
    Wait until the international country dropdown appears.
    """

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
            300
        )

    return None


async def read_dropdown_options(
    country_select,
):
    """
    Read the ACTUAL dropdown contents.

    IMPORTANT:
    Nothing is filtered, renamed, sorted, or removed.

    The order is exactly the order of the <option> elements
    returned by the website.
    """

    print()
    print(
        "Reading complete country dropdown..."
    )

    options = country_select.locator(
        "option"
    )

    count = await options.count()

    print(
        f"Dropdown contains {count} options."
    )

    countries = []

    for i in range(count):
        option = options.nth(i)

        name = clean_name(
            await option.inner_text()
        )

        value = (
            await option.get_attribute(
                "value"
            )
        )

        # We deliberately do not remove anything.
        # Every option is preserved in its original order.
        countries.append(
            {
                "name": name,
                "value": value or "",
            }
        )

    return countries


def write_output(
    dropdown_countries,
    unavailable_countries,
):
    """
    Create posta-countries.txt with exactly two lists.

    LIST 1:
        Complete actual dropdown contents.

    LIST 2:
        Only countries for which the exact unavailable
        message appeared after clicking Izračunaj.
    """

    lines = []

    lines.append(
        "LIST 1 - MEĐUNARODNI PROMET / DOPISNICA"
    )
    lines.append(
        "=========================================="
    )

    for country in dropdown_countries:
        lines.append(
            country["name"]
        )

    lines.append("")
    lines.append(
        "LIST 2 - PRIJEM POŠILJAKA SE TRENUTNO NE VRŠI"
    )
    lines.append(
        "=============================================="
    )

    for country in unavailable_countries:
        lines.append(country)

    lines.append("")

    save_text(
        OUTPUT_FILE,
        "\n".join(lines),
    )


async def select_avionski_prijenos(
    frame,
):
    """
    Select the exact checkbox supplied by the user:

        #chbMeDoAvionski
    """

    checkbox = frame.locator(
        "#chbMeDoAvionski"
    )

    if await checkbox.count() == 0:
        raise RuntimeError(
            "#chbMeDoAvionski was not found."
        )

    checkbox = checkbox.first

    try:
        checked = await checkbox.is_checked()

        if not checked:
            await checkbox.check(
                timeout=DEFAULT_TIMEOUT,
                force=True,
            )

            await frame.page.wait_for_timeout(
                200
            )

    except Exception:
        # Fallback: click directly.
        try:
            await checkbox.click(
                timeout=DEFAULT_TIMEOUT,
                force=True,
            )

            await frame.page.wait_for_timeout(
                200
            )

        except Exception as exc:
            raise RuntimeError(
                "Could not select "
                "Avionski prijenos: "
                f"{exc}"
            )

    return True


async def set_weight_10g(frame):
    """
    Enter 10 into:

        #tbxMeDoAvioTezina
    """

    field = frame.locator(
        "#tbxMeDoAvioTezina"
    )

    if await field.count() == 0:
        raise RuntimeError(
            "#tbxMeDoAvioTezina was not found."
        )

    field = field.first

    await field.fill("10")

    return True


async def get_body_text(frame):
    try:
        return await frame.locator(
            "body"
        ).inner_text(timeout=2_000)
    except Exception:
        return ""


def contains_unavailable_message(
    text,
):
    return (
        UNAVAILABLE_MESSAGE.casefold()
        in (text or "").casefold()
    )


async def calculate_country(
    frame,
    country_select,
    country,
):
    """
    Test one country.

    Returns True ONLY when the exact unavailable message
    appears.

    Everything else returns False.

    This is intentional: List 2 must contain only countries
    for which the requested message appears.
    """

    name = country["name"]
    value = country["value"]

    # ------------------------------------------------------------
    # Select destination.
    #
    # The website uses onchange + ASP.NET postback, so selecting
    # a country can replace/update controls in the iframe.
    # ------------------------------------------------------------

    try:
        if value:
            await country_select.select_option(
                value=value
            )
        else:
            await country_select.select_option(
                label=name
            )

    except Exception as exc:
        print(
            f"  Could not select country: {exc}"
        )
        return False

    # Give the ASP.NET postback a short opportunity to update
    # the international form.
    await frame.page.wait_for_timeout(
        250
    )

    # ------------------------------------------------------------
    # Re-find controls after the country postback.
    # ------------------------------------------------------------

    try:
        await select_avionski_prijenos(
            frame
        )

        await set_weight_10g(
            frame
        )

    except Exception as exc:
        print(
            f"  Could not prepare calculation: "
            f"{exc}"
        )
        return False

    # ------------------------------------------------------------
    # Clear any old unavailable message by recording the current
    # page state before clicking.
    # ------------------------------------------------------------

    before = await get_body_text(
        frame
    )

    # ------------------------------------------------------------
    # Click exact calculate button:
    #
    # #btnMeDoIzracunaj
    # ------------------------------------------------------------

    calculate = frame.locator(
        "#btnMeDoIzracunaj"
    )

    if await calculate.count() == 0:
        print(
            "  #btnMeDoIzracunaj not found."
        )
        return False

    try:
        await calculate.first.click(
            timeout=DEFAULT_TIMEOUT,
            force=True,
        )

    except Exception as exc:
        print(
            f"  Calculate click failed: {exc}"
        )
        return False

    # ------------------------------------------------------------
    # Wait specifically for the requested message.
    #
    # We do NOT wait for generic price/result text.
    # ------------------------------------------------------------

    deadline = (
        asyncio.get_running_loop().time()
        + RESULT_WAIT_TIMEOUT / 1000
    )

    while (
        asyncio.get_running_loop().time()
        < deadline
    ):
        text = await get_body_text(
            frame
        )

        if contains_unavailable_message(
            text
        ):
            return True

        await frame.page.wait_for_timeout(
            100
        )

    # ------------------------------------------------------------
    # Final check.
    # ------------------------------------------------------------

    after = await get_body_text(
        frame
    )

    if contains_unavailable_message(
        after
    ):
        return True

    return False


async def main():
    print("=" * 70)
    print("JP BH POŠTA COUNTRY MONITOR")
    print("=" * 70)
    print()
    print(f"URL: {URL}")
    print()
    print(
        "Output:"
        f" {OUTPUT_FILE}"
    )
    print()

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
            # ====================================================
            # OPEN WEBSITE
            # ====================================================

            print(
                "Opening calculator page..."
            )

            try:
                await page.goto(
                    URL,
                    wait_until="domcontentloaded",
                    timeout=NAVIGATION_TIMEOUT,
                )

            except PlaywrightTimeoutError:
                print(
                    "Navigation timeout; "
                    "continuing because the page may "
                    "already be usable."
                )

            await page.wait_for_timeout(
                1_500
            )

            # ====================================================
            # FIND IFRAME
            # ====================================================

            frame = await find_calculator_frame(
                page
            )

            if frame is None:
                raise RuntimeError(
                    "Could not locate calculator iframe."
                )

            print()
            print(
                f"Calculator frame URL: {frame.url}"
            )

            # ====================================================
            # SELECT MEĐUNARODNI PROMET
            # ====================================================

            if not await click_international(
                frame
            ):
                raise RuntimeError(
                    "Could not select "
                    "Međunarodni promet."
                )

            # ====================================================
            # SELECT DOPISNICA
            # ====================================================

            if not await click_dopisnica(
                frame
            ):
                raise RuntimeError(
                    "Could not select Dopisnica."
                )

            # ====================================================
            # WAIT FOR COUNTRY DROPDOWN
            # ====================================================

            print()
            print(
                "Waiting for international "
                "country dropdown..."
            )

            country_select = (
                await wait_for_country_select(
                    frame
                )
            )

            if country_select is None:
                raise RuntimeError(
                    "Country dropdown "
                    "#ddlMeDoOdrediste "
                    "was not found after selecting "
                    "Međunarodni promet and Dopisnica."
                )

            # ====================================================
            # READ LIST 1
            # ====================================================

            dropdown_countries = (
                await read_dropdown_options(
                    country_select
                )
            )

            if not dropdown_countries:
                raise RuntimeError(
                    "The country dropdown "
                    "contained no options."
                )

            print()
            print(
                "Complete dropdown captured."
            )

            # ====================================================
            # INITIAL OUTPUT
            #
            # This means posta-countries.txt exists even while
            # testing is still underway.
            # ====================================================

            unavailable_countries = []

            write_output(
                dropdown_countries,
                unavailable_countries,
            )

            # ====================================================
            # TEST COUNTRIES
            # ====================================================

            print()
            print("=" * 70)
            print(
                "TESTING COUNTRIES FOR "
                "UNAVAILABLE MESSAGE"
            )
            print("=" * 70)
            print()

            overall_deadline = (
                asyncio.get_running_loop().time()
                + OVERALL_TIMEOUT / 1000
            )

            for index, country in enumerate(
                dropdown_countries,
                1,
            ):
                # ------------------------------------------------
                # Overall safety timeout.
                # ------------------------------------------------

                if (
                    asyncio.get_running_loop().time()
                    >= overall_deadline
                ):
                    print()
                    print(
                        "Overall timeout reached."
                    )
                    print(
                        "Stopping country testing."
                    )
                    break

                name = country["name"]

                print(
                    f"[{index}/{len(dropdown_countries)}] "
                    f"{name}",
                    flush=True,
                )

                try:
                    unavailable = (
                        await calculate_country(
                            frame,
                            country_select,
                            country,
                        )
                    )

                except Exception as exc:
                    print(
                        f"  ERROR: {exc}"
                    )
                    unavailable = False

                if unavailable:
                    print(
                        "  -> UNAVAILABLE MESSAGE FOUND"
                    )

                    unavailable_countries.append(
                        name
                    )

                else:
                    print(
                        "  -> message not found"
                    )

                # ------------------------------------------------
                # IMPORTANT:
                #
                # Save after every country.
                #
                # If GitHub Actions stops unexpectedly, the file
                # still contains the work completed so far.
                # ------------------------------------------------

                write_output(
                    dropdown_countries,
                    unavailable_countries,
                )

                await page.wait_for_timeout(
                    BETWEEN_COUNTRIES_MS
                )

            # ====================================================
            # FINAL OUTPUT
            # ====================================================

            write_output(
                dropdown_countries,
                unavailable_countries,
            )

            print()
            print("=" * 70)
            print("MONITOR COMPLETE")
            print("=" * 70)
            print()
            print(
                f"List 1 entries: "
                f"{len(dropdown_countries)}"
            )
            print(
                f"List 2 entries: "
                f"{len(unavailable_countries)}"
            )
            print()
            print(
                f"Created: {OUTPUT_FILE}"
            )
            print()
            print("List 2:")
            print("-" * 70)

            for name in unavailable_countries:
                print(name)

            print()
            print(
                "Output file contents:"
            )
            print("-" * 70)

            print(
                OUTPUT_FILE.read_text(
                    encoding="utf-8"
                )
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


if __name__ == "__main__":
    try:
        asyncio.run(main())

    except KeyboardInterrupt:
        print(
            "Monitor interrupted."
        )
        sys.exit(130)

    except Exception as exc:
        print()
        print("=" * 70)
        print("MONITOR FAILED")
        print("=" * 70)
        print(
            f"{type(exc).__name__}: {exc}"
        )
        sys.exit(1)
