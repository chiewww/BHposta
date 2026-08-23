import asyncio
import os
from pathlib import Path

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError


URL = os.getenv(
    "CALCULATOR_URL",
    "https://www.posta.ba/kalkulator-cijena/",
)

OUTPUT = Path("posta-countries.txt")

COUNTRY_SELECTOR = "#ddlMeDoOdrediste"
INTERNATIONAL_TAB_LI = "#ASPxTabControl1_T1"
INTERNATIONAL_TAB_A = "#ASPxTabControl1_T1T"
WEIGHT_SELECTOR = "#tbxMeDoAvioTezina"
CALCULATE_SELECTOR = "#btnMeDoIzracunaj"

MESSAGE = "Prijem pošiljaka se trenutno ne vrši za odabranu državu"


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
            frame_url = frame.url or ""

            if "KalkulatorCijena_WEB_app" in frame_url:
                print(
                    f"Calculator iframe found: frame {index}"
                )
                print(
                    f"URL: {frame_url}"
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
    print("Waiting for country dropdown...")

    attempts = seconds * 2

    for attempt in range(attempts):
        try:
            dropdown = frame.locator(COUNTRY_SELECTOR)

            if await dropdown.count() > 0:
                try:
                    if await dropdown.first.is_visible():
                        print("Country dropdown is visible.")
                        return dropdown.first
                except Exception:
                    pass

                print("Country dropdown exists.")
                return dropdown.first

        except Exception:
            pass

        await frame.page.wait_for_timeout(500)

    return None


async def activate_international_tab(frame):
    print("")
    print("=" * 70)
    print("ACTIVATING MEĐUNARODNI PROMET")
    print("=" * 70)

    # First verify that the exact HTML supplied by the user exists.
    try:
        tab_li = frame.locator(INTERNATIONAL_TAB_LI)

        count = await tab_li.count()

        print(
            f"{INTERNATIONAL_TAB_LI} matches: {count}"
        )

        if count:
            html = await tab_li.first.evaluate(
                "(el) => el.outerHTML"
            )

            print("International tab <li> HTML:")
            print(html)

    except Exception as exc:
        print("Could not inspect tab <li>:")
        print(exc)

    # IMPORTANT:
    # The site's tab is a DevExpress ASPxTabControl.
    # We do NOT call its JavaScript client API because that API
    # can trigger an ASP.NET/DevExpress JavaScript error in
    # Playwright's execution context.
    #
    # Instead, click the actual tab element exactly as a user would.

    try:
        tab_li = frame.locator(INTERNATIONAL_TAB_LI).first

        if await tab_li.count() == 0:
            print("Tab <li> was not found.")
            return False

        print("Attempt 1: clicking actual tab <li>...")

        try:
            await tab_li.click(
                force=True,
                timeout=5000,
            )

            print("Actual tab <li> click completed.")

        except Exception as exc:
            print("Tab <li> click failed:")
            print(exc)

            # Use DOM click without invoking the DevExpress API ourselves.
            print("Attempt 2: DOM click on tab <li>...")

            result = await tab_li.evaluate(
                """
                (el) => {
                    el.dispatchEvent(
                        new MouseEvent('mousedown', {
                            bubbles: true,
                            cancelable: true,
                            view: window
                        })
                    );

                    el.dispatchEvent(
                        new MouseEvent('mouseup', {
                            bubbles: true,
                            cancelable: true,
                            view: window
                        })
                    );

                    el.dispatchEvent(
                        new MouseEvent('click', {
                            bubbles: true,
                            cancelable: true,
                            view: window
                        })
                    );

                    return true;
                }
                """
            )

            print(
                "DOM event dispatch result:",
                result,
            )

    except Exception as exc:
        print("Could not click tab <li>:")
        print(exc)

    # Give ASP.NET AJAX / DevExpress time to process the asynchronous
    # postback and replace the panel contents.
    print("Waiting for international controls...")

    dropdown = await wait_for_country_dropdown(
        frame,
        seconds=15,
    )

    if dropdown is not None:
        print(
            "SUCCESS: International country dropdown is available."
        )
        return True

    # One final attempt: click the exact anchor.
    print(
        "Country dropdown did not appear."
    )
    print(
        "Attempt 3: clicking exact tab anchor..."
    )

    try:
        anchor = frame.locator(
            INTERNATIONAL_TAB_A
        ).first

        if await anchor.count():
            await anchor.evaluate(
                """
                (el) => {
                    el.dispatchEvent(
                        new MouseEvent('click', {
                            bubbles: true,
                            cancelable: true,
                            view: window
                        })
                    );
                }
                """
            )

            print("Anchor DOM click dispatched.")

    except Exception as exc:
        print("Anchor DOM click failed:")
        print(exc)

    dropdown = await wait_for_country_dropdown(
        frame,
        seconds=15,
    )

    if dropdown is not None:
        print(
            "SUCCESS: International country dropdown is available."
        )
        return True

    # Save the current iframe HTML because this tells us exactly
    # what the server returned after the tab activation attempt.
    try:
        Path("international-failure.html").write_text(
            await frame.content(),
            encoding="utf-8",
        )

        print(
            "Saved international-failure.html"
        )
    except Exception:
        pass

    try:
        Path("international-failure.txt").write_text(
            await get_body_text(frame),
            encoding="utf-8",
        )

        print(
            "Saved international-failure.txt"
        )
    except Exception:
        pass

    print(
        "FAILED: International country dropdown never appeared."
    )

    return False


async def read_list1(dropdown):
    print("")
    print("=" * 70)
    print("READING LIST 1")
    print("=" * 70)

    options = dropdown.locator("option")

    count = await options.count()

    print(
        f"Actual dropdown option count: {count}"
    )

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

    await dropdown.page.wait_for_timeout(1200)


async def set_weight(frame):
    try:
        weight = frame.locator(
            WEIGHT_SELECTOR
        )

        if await weight.count():
            await weight.fill("10")

            print(
                "Weight set to 10 grams."
            )

    except Exception as exc:
        print(
            "Could not set weight:"
        )
        print(exc)


async def click_calculate(frame):
    print("Clicking Izračunaj...")

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
            "Normal calculate click failed:"
        )
        print(exc)

    try:
        await button.evaluate(
            """
            (el) => {
                el.click();
                return true;
            }
            """
        )

        print(
            "JavaScript calculate click succeeded."
        )

        return True

    except Exception as exc:
        print(
            "JavaScript calculate click failed:"
        )
        print(exc)

    return False


async def check_message(frame):
    for attempt in range(30):
        text = await get_body_text(frame)

        if MESSAGE in text:
            print(
                "MESSAGE FOUND:"
            )
            print(MESSAGE)

            return True

        await frame.page.wait_for_timeout(300)

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

        await set_weight(frame)

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

            selected = await activate_international_tab(
                frame
            )

            if not selected:
                raise RuntimeError(
                    "Could not activate Međunarodni promet."
                )

            dropdown = await wait_for_country_dropdown(
                frame,
                seconds=10,
            )

            if dropdown is None:
                raise RuntimeError(
                    "Could not find country dropdown after "
                    "activating Međunarodni promet."
                )

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

            try:
                Path("diagnostic.html").write_text(
                    await page.content(),
                    encoding="utf-8",
                )
            except Exception:
                pass

            try:
                if frame is not None:
                    Path("iframe.html").write_text(
                        await frame.content(),
                        encoding="utf-8",
                    )

                    Path("iframe.txt").write_text(
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
