python
import asyncio
import os
from pathlib import Path

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError


# ============================================================
# CONFIGURATION
# ============================================================

URL = os.getenv(
    "CALCULATOR_URL",
    "https://www.posta.ba/kalkulator-cijena/",
)

OUTPUT = Path("posta-countries.txt")

COUNTRY_SELECTOR = "#ddlMeDoOdrediste"
WEIGHT_SELECTOR = "#tbxMeDoAvioTezina"
CALCULATE_SELECTOR = "#btnMeDoIzracunaj"

INTERNATIONAL_TAB_LINK = "#ASPxTabControl1_T1T"
INTERNATIONAL_TAB = "#ASPxTabControl1_T1"

MESSAGE = (
    "Prijem pošiljaka se trenutno ne vrši za odabranu državu"
)

# How long to wait for ASP.NET AJAX / postback operations.
POSTBACK_WAIT_MS = 2500

# How long to wait for the country dropdown after changing tabs.
DROPDOWN_WAIT_SECONDS = 30


# ============================================================
# OUTPUT
# ============================================================

def write_output(list1, list2, status):
    lines = []

    lines.append("JP BH POŠTA COUNTRY MONITOR")
    lines.append("=" * 70)
    lines.append(f"STATUS: {status}")
    lines.append("")

    lines.append("LIST 1")
    lines.append("Actual country dropdown contents")
    lines.append("-" * 70)

    for country in list1:
        lines.append(country["name"])

    lines.append("")
    lines.append("LIST 2")
    lines.append(MESSAGE)
    lines.append("-" * 70)

    for country in list2:
        lines.append(country["name"])

    lines.append("")

    OUTPUT.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


# ============================================================
# FRAME HELPERS
# ============================================================

async def get_body_text(frame):
    try:
        return await frame.locator("body").inner_text()
    except Exception:
        return ""


async def find_calculator_frame(page):
    print("Locating calculator iframe...")

    for attempt in range(30):
        frames = page.frames

        print(
            f"Frame search {attempt + 1}/30 "
            f"({len(frames)} frames)"
        )

        # First choice: identify the frame by its URL.
        for index, frame in enumerate(frames):
            frame_url = frame.url or ""

            if "KalkulatorCijena_WEB_app" in frame_url:
                print(
                    f"Calculator iframe found: frame {index}"
                )
                print(
                    f"URL: {frame_url}"
                )
                return frame

        # Second choice: identify by calculator HTML.
        for index, frame in enumerate(frames):
            try:
                html = await frame.content()
            except Exception:
                continue

            if (
                "ddlMeDoOdrediste" in html
                and "btnMeDoIzracunaj" in html
            ):
                print(
                    f"Calculator iframe found by HTML: frame {index}"
                )
                print(
                    f"URL: {frame.url}"
                )
                return frame

        await page.wait_for_timeout(1000)

    return None


# ============================================================
# TAB ACTIVATION
# ============================================================

async def wait_for_international_controls(frame):
    """
    Wait until the international calculator controls actually
    exist.

    We do NOT assume that a click succeeding means the ASP.NET
    postback has finished.
    """

    print(
        "Waiting for international calculator controls..."
    )

    deadline = asyncio.get_running_loop().time() + DROPDOWN_WAIT_SECONDS

    while asyncio.get_running_loop().time() < deadline:
        try:
            dropdown = frame.locator(COUNTRY_SELECTOR)

            if await dropdown.count():
                print(
                    "Country dropdown is now available."
                )
                return True

        except Exception:
            pass

        await frame.page.wait_for_timeout(500)

    return False


async def activate_international_tab(frame):
    """
    Activate Međunarodni promet.

    This page uses DevExpress ASPxTabControl inside an ASP.NET
    application. The visible tab is:

        #ASPxTabControl1_T1T

    Its parent <li> is:

        #ASPxTabControl1_T1

    The important behavior is that clicking the tab starts an
    ASP.NET/DevExpress postback. We therefore wait for the
    resulting international controls rather than treating a
    JavaScript exception from the DevExpress internals as a
    failure.
    """

    print("")
    print("=" * 70)
    print("SELECTING MEĐUNARODNI PROMET")
    print("=" * 70)

    link = frame.locator(INTERNATIONAL_TAB_LINK).first
    tab = frame.locator(INTERNATIONAL_TAB).first

    if await link.count() == 0:
        raise RuntimeError(
            f"International tab link {INTERNATIONAL_TAB_LINK} "
            "was not found."
        )

    print(
        f"{INTERNATIONAL_TAB_LINK} matches: "
        f"{await frame.locator(INTERNATIONAL_TAB_LINK).count()}"
    )

    try:
        html = await link.evaluate(
            "(el) => el.outerHTML"
        )
        print("International tab HTML:")
        print(html)
    except Exception:
        pass

    # --------------------------------------------------------
    # METHOD 1:
    # Click the actual <a> with force=True.
    #
    # This is the real user-facing tab element.
    # --------------------------------------------------------

    print("")
    print("Clicking actual international tab link...")

    click_started = False

    try:
        await link.click(
            force=True,
            timeout=5000,
            no_wait_after=True,
        )

        click_started = True

        print(
            "International tab click was sent."
        )

    except Exception as exc:
        print(
            "Normal tab click reported an exception:"
        )
        print(exc)

    # Give the ASP.NET request a moment to start.
    await frame.page.wait_for_timeout(1000)

    if await wait_for_international_controls(frame):
        print(
            "Međunarodni promet activated successfully."
        )
        return True

    # --------------------------------------------------------
    # METHOD 2:
    # Click the parent <li>.
    #
    # This is useful with DevExpress because the tab control
    # handles the tab container as well as the anchor.
    # --------------------------------------------------------

    print("")
    print(
        "Country dropdown did not appear."
    )
    print(
        "Trying actual tab <li>..."
    )

    if await tab.count():
        try:
            tab_html = await tab.evaluate(
                "(el) => el.outerHTML"
            )

            print("Tab <li> HTML:")
            print(tab_html)

        except Exception:
            pass

        try:
            await tab.click(
                force=True,
                timeout=5000,
                no_wait_after=True,
            )

            print(
                "Tab <li> click was sent."
            )

        except Exception as exc:
            print(
                "Tab <li> click reported an exception:"
            )
            print(exc)

        await frame.page.wait_for_timeout(
            POSTBACK_WAIT_MS
        )

        if await wait_for_international_controls(frame):
            print(
                "Međunarodni promet activated successfully "
                "through the tab container."
            )
            return True

    # --------------------------------------------------------
    # METHOD 3:
    # Dispatch a real mouse click without calling the
    # DevExpress client API ourselves.
    #
    # IMPORTANT:
    # We intentionally do NOT call ASPxTabControl1.SetActiveTab,
    # ChangeActiveTab, SendPostBack, or __doPostBack directly.
    # Those were producing the strict-mode JavaScript exception.
    # --------------------------------------------------------

    print("")
    print(
        "Trying browser mouse click on the tab..."
    )

    try:
        await link.scroll_into_view_if_needed(
            timeout=5000
        )

        box = await link.bounding_box()

        if box:
            x = box["x"] + box["width"] / 2
            y = box["y"] + box["height"] / 2

            print(
                f"Mouse click coordinates: {x:.1f}, {y:.1f}"
            )

            await frame.page.mouse.click(
                x,
                y,
            )

            print(
                "Browser mouse click was sent."
            )

            await frame.page.wait_for_timeout(
                POSTBACK_WAIT_MS
            )

            if await wait_for_international_controls(frame):
                print(
                    "Međunarodni promet activated successfully "
                    "through browser mouse click."
                )
                return True

    except Exception as exc:
        print(
            "Browser mouse click failed:"
        )
        print(exc)

    # --------------------------------------------------------
    # METHOD 4:
    # Inspect whether the international controls are already
    # present somewhere in the frame.
    #
    # This prevents a false failure if the page switched but
    # the selector timing was unusual.
    # --------------------------------------------------------

    print("")
    print(
        "Final inspection for international controls..."
    )

    try:
        html = await frame.content()

        if "ddlMeDoOdrediste" in html:
            print(
                "ddlMeDoOdrediste exists in the frame HTML."
            )

            dropdown = frame.locator(
                COUNTRY_SELECTOR
            )

            if await dropdown.count():
                print(
                    "Country dropdown is available."
                )
                return True

    except Exception as exc:
        print(
            "Final inspection failed:"
        )
        print(exc)

    print("")
    print(
        "FAILED: Međunarodni promet could not be activated."
    )

    return False


# ============================================================
# COUNTRY DROPDOWN
# ============================================================

async def get_country_dropdown(frame):
    print("")
    print("Locating country dropdown...")

    for attempt in range(30):
        try:
            locator = frame.locator(
                COUNTRY_SELECTOR
            )

            count = await locator.count()

            if count:
                options = locator.locator("option")
                option_count = await options.count()

                print(
                    "Country dropdown found."
                )

                print(
                    f"Options: {option_count}"
                )

                return locator.first

        except Exception:
            pass

        print(
            f"Waiting for country dropdown "
            f"{attempt + 1}/30..."
        )

        await frame.page.wait_for_timeout(1000)

    return None


async def read_list1(dropdown):
    """
    Read the actual HTML <option> elements.

    Nothing is filtered, renamed, sorted, or removed.

    The original order is preserved exactly.
    """

    print("")
    print("=" * 70)
    print("READING LIST 1")
    print("=" * 70)

    options = dropdown.locator("option")

    count = await options.count()

    countries = []

    for index in range(count):
        option = options.nth(index)

        name = (
            await option.inner_text()
        ).strip()

        value = (
            await option.get_attribute("value")
        )

        country = {
            "name": name,
            "value": value or "",
        }

        countries.append(country)

        print(
            f"[{index}] {name}"
        )

    print("")
    print(
        f"LIST 1 contains {len(countries)} countries."
    )

    return countries


# ============================================================
# COUNTRY SELECTION
# ============================================================

async def select_country(dropdown, country):
    value = country["value"]
    name = country["name"]

    print(
        f"Selecting country: {name}"
    )

    if value:
        await dropdown.select_option(
            value=value
        )
    else:
        await dropdown.select_option(
            label=name
        )

    await dropdown.page.wait_for_timeout(
        1200
    )


# ============================================================
# WEIGHT
# ============================================================

async def set_weight(frame):
    weight = frame.locator(
        WEIGHT_SELECTOR
    )

    count = await weight.count()

    if count == 0:
        print(
            "Weight field not found; continuing."
        )
        return

    try:
        await weight.fill("10")
        print(
            "Weight set to 10 grams."
        )
    except Exception as exc:
        print(
            "Could not fill weight field:"
        )
        print(exc)


# ============================================================
# CALCULATE
# ============================================================

async def click_calculate(frame):
    print(
        "Clicking Izračunaj..."
    )

    button = frame.locator(
        CALCULATE_SELECTOR
    )

    count = await button.count()

    print(
        f"Calculate button matches: {count}"
    )

    if count == 0:
        return False

    button = button.first

    # --------------------------------------------------------
    # Click normally.
    #
    # no_wait_after=True is intentional because this is an
    # ASP.NET form submission / postback.
    # --------------------------------------------------------

    try:
        await button.click(
            force=True,
            timeout=10000,
            no_wait_after=True,
        )

        print(
            "Izračunaj click sent."
        )

        await frame.page.wait_for_timeout(
            1500
        )

        return True

    except Exception as exc:
        print(
            "Normal calculate click failed:"
        )
        print(exc)

    # --------------------------------------------------------
    # JavaScript fallback.
    # --------------------------------------------------------

    try:
        await button.evaluate(
            "(el) => el.click()"
        )

        print(
            "JavaScript calculate click sent."
        )

        await frame.page.wait_for_timeout(
            1500
        )

        return True

    except Exception as exc:
        print(
            "JavaScript calculate click failed:"
        )
        print(exc)

    return False


# ============================================================
# MESSAGE CHECK
# ============================================================

async def check_message(frame):
    """
    Check the actual rendered page text.

    The exact message must occur in the frame body.
    """

    for attempt in range(20):
        text = await get_body_text(frame)

        if MESSAGE in text:
            print(
                "MESSAGE FOUND."
            )
            return True

        await frame.page.wait_for_timeout(
            300
        )

    return False


# ============================================================
# TEST ONE COUNTRY
# ============================================================

async def test_country(
    frame,
    dropdown,
    country,
):
    name = country["name"]

    print("")
    print(
        "=" * 70
    )
    print(
        "TESTING: " + name
    )
    print(
        "=" * 70
    )

    try:
        await select_country(
            dropdown,
            country,
        )

        await set_weight(
            frame
        )

        clicked = await click_calculate(
            frame
        )

        if not clicked:
            print(
                "Could not click Izračunaj."
            )
            return False

        found = await check_message(
            frame
        )

        if found:
            print(
                "LIST 2 ADD: " + name
            )
            return True

        print(
            "Message not found."
        )

        return False

    except Exception as exc:
        print(
            "Country test failed:"
        )
        print(
            type(exc).__name__
            + ": "
            + str(exc)
        )

        return False


# ============================================================
# MAIN
# ============================================================

async def main():
    print("=" * 70)
    print("JP BH POŠTA COUNTRY MONITOR")
    print("=" * 70)

    print(
        "URL: " + URL
    )

    print(
        "Output: " + str(OUTPUT)
    )

    # Always create an output file, even if startup fails.
    write_output(
        [],
        [],
        "STARTING",
    )

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True,
            args=[
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
        )

        page = await context.new_page()

        page.set_default_timeout(
            10000
        )

        frame = None

        try:
            # ------------------------------------------------
            # OPEN PAGE
            # ------------------------------------------------

            print("")
            print(
                "Opening calculator page..."
            )

            await page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=30000,
            )

            await page.wait_for_timeout(
                3000
            )

            # ------------------------------------------------
            # FIND IFRAME
            # ------------------------------------------------

            frame = await find_calculator_frame(
                page
            )

            if frame is None:
                raise RuntimeError(
                    "Calculator iframe not found."
                )

            print(
                "Calculator frame URL: "
                + frame.url
            )

            # ------------------------------------------------
            # INTERNATIONAL TAB
            # ------------------------------------------------

            selected = await activate_international_tab(
                frame
            )

            if not selected:
                raise RuntimeError(
                    "Could not activate Međunarodni promet."
                )

            # ------------------------------------------------
            # COUNTRY DROPDOWN
            # ------------------------------------------------

            dropdown = await get_country_dropdown(
                frame
            )

            if dropdown is None:
                raise RuntimeError(
                    "Could not find "
                    + COUNTRY_SELECTOR
                )

            # ------------------------------------------------
            # LIST 1
            # ------------------------------------------------

            list1 = await read_list1(
                dropdown
            )

            if not list1:
                raise RuntimeError(
                    "Country dropdown is empty."
                )

            # ------------------------------------------------
            # LIST 2
            # ------------------------------------------------

            list2 = []

            write_output(
                list1,
                list2,
                "TESTING",
            )

            print("")
            print("=" * 70)
            print("TESTING LIST 2")
            print("=" * 70)

            for index, country in enumerate(
                list1,
                1,
            ):
                print("")
                print(
                    f"COUNTRY {index}/{len(list1)}"
                )

                found = await test_country(
                    frame,
                    dropdown,
                    country,
                )

                if found:
                    list2.append(
                        country
                    )

                # Save progress after every country.
                write_output(
                    list1,
                    list2,
                    "TESTING",
                )

            # ------------------------------------------------
            # FINAL OUTPUT
            # ------------------------------------------------

            write_output(
                list1,
                list2,
                "COMPLETE",
            )

            print("")
            print("=" * 70)
            print("MONITOR COMPLETE")
            print("=" * 70)

            print(
                f"List 1: {len(list1)} countries"
            )

            print(
                f"List 2: {len(list2)} countries"
            )

            print("")
            print(
                "LIST 2:"
            )

            for country in list2:
                print(
                    country["name"]
                )

            print("")
            print(
                "Output file created:"
            )
            print(
                str(OUTPUT)
            )

        except Exception as exc:
            print("")
            print("=" * 70)
            print("MONITOR FAILED")
            print("=" * 70)

            print(
                type(exc).__name__
                + ": "
                + str(exc)
            )

            # Keep the file available even on failure.
            try:
                write_output(
                    [],
                    [],
                    "FAILED: "
                    + type(exc).__name__
                    + ": "
                    + str(exc),
                )
            except Exception:
                pass

            # ------------------------------------------------
            # DIAGNOSTICS
            # ------------------------------------------------

            try:
                Path(
                    "diagnostic.html"
                ).write_text(
                    await page.content(),
                    encoding="utf-8",
                )
            except Exception:
                pass

            try:
                if frame is not None:
                    Path(
                        "iframe.html"
                    ).write_text(
                        await frame.content(),
                        encoding="utf-8",
                    )

                    Path(
                        "iframe.txt"
                    ).write_text(
                        await get_body_text(frame),
                        encoding="utf-8",
                    )
            except Exception:
                pass

            try:
                await page.screenshot(
                    path="diagnostic.png",
                    full_page=True,
                )
            except Exception:
                pass

            raise

        finally:
            await context.close()
            await browser.close()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    asyncio.run(main())
