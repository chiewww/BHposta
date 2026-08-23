import asyncio
import os
from pathlib import Path

from playwright.async_api import async_playwright


URL = os.getenv(
    "CALCULATOR_URL",
    "https://www.posta.ba/kalkulator-cijena/",
)

OUTPUT = Path("posta-countries.txt")

COUNTRY_SELECTOR = "#ddlMeDoOdrediste"
INTERNATIONAL_TAB = "#ASPxTabControl1_T1T"
INTERNATIONAL_TAB_LI = "#ASPxTabControl1_T1"
WEIGHT_SELECTOR = "#tbxMeDoAvioTezina"
CALCULATE_SELECTOR = "#btnMeDoIzracunaj"

MESSAGE = (
    "Prijem pošiljaka se trenutno ne vrši za odabranu državu"
)


def write_output(list1, list2, status):
    lines = []

    lines.append("JP BH POŠTA COUNTRY MONITOR")
    lines.append("=" * 70)
    lines.append("STATUS: " + status)
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

        for index, frame in enumerate(frames):
            url = frame.url or ""

            if "KalkulatorCijena_WEB_app" in url:
                print(
                    f"Calculator iframe found: frame {index}"
                )
                print(
                    f"URL: {url}"
                )
                return frame

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


async def wait_for_country_dropdown(frame, seconds=15):
    print(
        "Waiting for country dropdown..."
    )

    attempts = int(seconds * 2)

    for attempt in range(attempts):
        try:
            dropdown = frame.locator(
                COUNTRY_SELECTOR
            )

            if await dropdown.count():
                print(
                    "Country dropdown is present."
                )
                return True

        except Exception:
            pass

        await frame.page.wait_for_timeout(500)

    return False


async def select_international(frame):
    print("Selecting Međunarodni promet...")

    try:
        tab = frame.locator(
            INTERNATIONAL_TAB
        )

        tab_count = await tab.count()

        print(
            f"{INTERNATIONAL_TAB} matches: "
            f"{tab_count}"
        )

        if tab_count == 0:
            raise RuntimeError(
                "International tab anchor was not found."
            )

        print("International tab HTML:")

        try:
            print(
                await tab.first.evaluate(
                    "(el) => el.outerHTML"
                )
            )
        except Exception:
            pass

        # --------------------------------------------------------
        # METHOD 1:
        # Use the DevExpress client-side tab-control API.
        #
        # The HTML identifies the control as:
        # ASPxTabControl1
        #
        # Tab index 0 = Unutrašnji promet
        # Tab index 1 = Međunarodni promet
        # --------------------------------------------------------

        print(
            "Trying DevExpress ASPxTabControl client API..."
        )

        try:
            result = await frame.evaluate(
                """
                () => {
                    if (
                        typeof ASPxClientTabControl === "undefined"
                    ) {
                        return {
                            success: false,
                            reason: "ASPxClientTabControl undefined"
                        };
                    }

                    const control =
                        ASPxClientTabControl.Cast(
                            "ASPxTabControl1"
                        );

                    if (!control) {
                        return {
                            success: false,
                            reason: "ASPxTabControl1 not found"
                        };
                    }

                    control.SetActiveTabIndex(1);

                    return {
                        success: true,
                        activeIndex:
                            control.GetActiveTabIndex()
                    };
                }
                """
            )

            print(
                "DevExpress result:"
            )
            print(result)

            await frame.page.wait_for_timeout(3000)

            if await wait_for_country_dropdown(
                frame,
                seconds=10,
            ):
                print(
                    "SUCCESS: Međunarodni promet "
                    "activated through DevExpress API."
                )
                return True

        except Exception as exc:
            print(
                "DevExpress API attempt failed:"
            )
            print(exc)

        # --------------------------------------------------------
        # METHOD 2:
        # Click the actual <li> tab rather than the <a>.
        # --------------------------------------------------------

        print(
            "Trying the actual tab <li>..."
        )

        try:
            tab_li = frame.locator(
                INTERNATIONAL_TAB_LI
            )

            if await tab_li.count():
                print(
                    "Tab <li> found."
                )

                print(
                    await tab_li.first.evaluate(
                        "(el) => el.outerHTML"
                    )
                )

                await tab_li.first.scroll_into_view_if_needed()

                await tab_li.first.click(
                    force=True,
                    timeout=10000,
                )

                await frame.page.wait_for_timeout(3000)

                if await wait_for_country_dropdown(
                    frame,
                    seconds=10,
                ):
                    print(
                        "SUCCESS: Međunarodni promet "
                        "activated by clicking the <li>."
                    )
                    return True

        except Exception as exc:
            print(
                "<li> click failed:"
            )
            print(exc)

        # --------------------------------------------------------
        # METHOD 3:
        # JavaScript click on the <li>.
        # --------------------------------------------------------

        print(
            "Trying JavaScript click on tab <li>..."
        )

        try:
            result = await frame.evaluate(
                """
                () => {
                    const li =
                        document.getElementById(
                            "ASPxTabControl1_T1"
                        );

                    if (!li) {
                        return false;
                    }

                    li.click();

                    return true;
                }
                """
            )

            print(
                "JavaScript <li> click result: "
                + str(result)
            )

            await frame.page.wait_for_timeout(3000)

            if await wait_for_country_dropdown(
                frame,
                seconds=10,
            ):
                print(
                    "SUCCESS: Međunarodni promet "
                    "activated through JavaScript <li> click."
                )
                return True

        except Exception as exc:
            print(
                "JavaScript <li> click failed:"
            )
            print(exc)

        # --------------------------------------------------------
        # METHOD 4:
        # Direct anchor click as final fallback.
        # --------------------------------------------------------

        print(
            "Trying direct anchor click as final fallback..."
        )

        try:
            await tab.first.scroll_into_view_if_needed()

            await tab.first.click(
                force=True,
                timeout=10000,
            )

            await frame.page.wait_for_timeout(3000)

            if await wait_for_country_dropdown(
                frame,
                seconds=10,
            ):
                print(
                    "SUCCESS: Međunarodni promet "
                    "activated by anchor click."
                )
                return True

        except Exception as exc:
            print(
                "Anchor click failed:"
            )
            print(exc)

    except Exception as exc:
        print(
            "Could not access international tab:"
        )
        print(exc)

    print(
        "FAILED: Could not activate Međunarodni promet."
    )

    return False


async def get_country_dropdown(frame):
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

    print(
        f"LIST 1 contains {len(countries)} countries."
    )

    return countries


async def select_country(dropdown, country):
    value = country["value"]
    name = country["name"]

    print(
        f"Selecting country: {name} "
        f"(value={value})"
    )

    if value:
        await dropdown.select_option(
            value=value
        )
    else:
        await dropdown.select_option(
            label=name
        )

    # The actual HTML you supplied contains:
    #
    # onchange="javascript:setTimeout(
    #   '__doPostBack(\'ddlMeDoOdrediste\',\'\')',
    #   0
    # )"
    #
    # Give that ASP.NET postback time to complete.
    await dropdown.page.wait_for_timeout(2000)


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

    try:
        await button.scroll_into_view_if_needed()

        await button.click(
            force=True,
            timeout=10000,
        )

        print(
            "Izračunaj clicked."
        )

        return True

    except Exception as exc:
        print(
            "Normal click failed:"
        )
        print(exc)

    try:
        result = await button.evaluate(
            """
            (el) => {
                el.click();
                return true;
            }
            """
        )

        print(
            "JavaScript click result: "
            + str(result)
        )

        return bool(result)

    except Exception as exc:
        print(
            "JavaScript click failed:"
        )
        print(exc)

    return False


async def check_message(frame):
    # Wait up to approximately 10 seconds for the
    # ASP.NET update panel/postback to finish.
    for attempt in range(40):
        text = await get_body_text(frame)

        if MESSAGE in text:
            print(
                f"Message found on check {attempt + 1}."
            )
            return True

        await frame.page.wait_for_timeout(250)

    return False


async def test_country(frame, dropdown, country):
    name = country["name"]

    print("")
    print("-" * 70)
    print(
        "Testing: " + name
    )
    print("-" * 70)

    try:
        await select_country(
            dropdown,
            country,
        )

        weight = frame.locator(
            WEIGHT_SELECTOR
        )

        if await weight.count():
            try:
                await weight.fill("10")

                print(
                    "Weight set to 10 grams."
                )

            except Exception as exc:
                print(
                    "Could not fill weight:"
                )
                print(exc)

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
            print("")
            print(
                "MESSAGE FOUND:"
            )
            print(
                MESSAGE
            )
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
        print(exc)

        return False


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

    # Always create the output file immediately.
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
            print(
                "Opening calculator page..."
            )

            await page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=30000,
            )

            await page.wait_for_timeout(3000)

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

            selected = await select_international(
                frame
            )

            if not selected:
                raise RuntimeError(
                    "Could not select Međunarodni promet."
                )

            dropdown = await get_country_dropdown(
                frame
            )

            if dropdown is None:
                raise RuntimeError(
                    "Could not find "
                    + COUNTRY_SELECTOR
                )

            # IMPORTANT:
            # List 1 is captured only after
            # Međunarodni promet is activated.
            list1 = await read_list1(
                dropdown
            )

            if not list1:
                raise RuntimeError(
                    "Country dropdown is empty."
                )

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
            print("LIST 2:")

            for country in list2:
                print(
                    country["name"]
                )

            print("")
            print(
                "Output file created: "
                + str(OUTPUT)
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

            # Preserve progress.
            try:
                if "list1" in locals():
                    current_list1 = list1
                else:
                    current_list1 = []

                if "list2" in locals():
                    current_list2 = list2
                else:
                    current_list2 = []

                write_output(
                    current_list1,
                    current_list2,
                    "FAILED",
                )

            except Exception:
                pass

            # Diagnostics.
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


if __name__ == "__main__":
    asyncio.run(main())
