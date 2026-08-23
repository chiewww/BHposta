import asyncio
import os
from pathlib import Path

from playwright.async_api import (
    async_playwright,
    TimeoutError as PlaywrightTimeoutError,
)


URL = os.getenv(
    "CALCULATOR_URL",
    "https://www.posta.ba/kalkulator-cijena/",
)

OUTPUT_FILE = Path("posta-countries.txt")

CALCULATOR_IFRAME_URL_PART = (
    "bhpwebout.posta.ba/KalkulatorCijena_WEB_app"
)

NAVIGATION_TIMEOUT = 30_000
DEFAULT_TIMEOUT = 10_000
FRAME_TIMEOUT = 30_000

UNAVAILABLE_MESSAGE = (
    "Prijem pošiljaka se trenutno ne vrši za odabranu državu"
)


def clean_text(value):
    return " ".join((value or "").split()).strip()


def save_output(list1, list2):
    """
    Create the single text file used by changedetection.io.

    LIST 1:
        Exact contents of the international destination dropdown,
        in original order, with nothing removed.

    LIST 2:
        Countries for which the calculator displays the specific
        unavailable-service message.
    """

    lines = []

    lines.append("LIST 1")
    lines.append("======")
    lines.extend(list1)

    lines.append("")
    lines.append("LIST 2")
    lines.append("======")
    lines.extend(list2)

    OUTPUT_FILE.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    print()
    print("=" * 70)
    print(f"Saved {OUTPUT_FILE}")
    print(f"LIST 1 countries: {len(list1)}")
    print(f"LIST 2 countries: {len(list2)}")
    print("=" * 70)


async def get_body_text(frame):
    try:
        return await frame.locator(
            "body"
        ).inner_text(timeout=5_000)
    except Exception:
        return ""


async def find_calculator_frame(page):
    print("Locating calculator iframe...")

    for attempt in range(1, 31):
        frames = page.frames

        print(
            f"Frame search {attempt}/30 "
            f"({len(frames)} frames)"
        )

        # First preference: known iframe URL.
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

        # Second preference: calculator HTML markers.
        for index, frame in enumerate(frames):
            try:
                html = await frame.content()
            except Exception:
                continue

            if not html:
                continue

            markers = (
                "ddlMeDoOdrediste",
                "btnMeDoIzracunaj",
                "tbxMeDoAvioTezina",
                "Međunarodni promet",
            )

            if any(
                marker.casefold()
                in html.casefold()
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

        if attempt < 30:
            await page.wait_for_timeout(1_000)

    return None


async def click_international_tab(frame):
    """
    Click the actual DevExpress 'Međunarodni promet' tab.

    Important:
    'Međunarodni promet' is NOT a <select>.
    It is a tab containing a span with class dx-vam.

    We click the visible text or an appropriate clickable ancestor,
    then verify that the international country selector appears.
    """

    print("Selecting Međunarodni promet...")

    # ------------------------------------------------------------
    # First: locate the exact visible text.
    # ------------------------------------------------------------

    locator = frame.get_by_text(
        "Međunarodni promet",
        exact=True,
    )

    count = await locator.count()

    print(
        f"Exact 'Međunarodni promet' elements: {count}"
    )

    for i in range(count):
        element = locator.nth(i)

        try:
            if not await element.is_visible():
                continue
        except Exception:
            continue

        try:
            print(
                f"Found visible international tab text "
                f"element #{i}"
            )

            print(
                "Tag:",
                await element.evaluate(
                    "(el) => el.tagName"
                ),
            )

            print(
                "HTML:",
                (
                    await element.evaluate(
                        "(el) => el.outerHTML"
                    )
                )[:1000],
            )
        except Exception:
            pass

        # --------------------------------------------------------
        # Attempt 1: click the span itself.
        # --------------------------------------------------------

        try:
            await element.click(
                timeout=DEFAULT_TIMEOUT,
                force=True,
            )

            print(
                "Clicked Međunarodni promet text."
            )

            if await wait_for_international_selector(
                frame
            ):
                print(
                    "International calculator activated."
                )
                return True

        except Exception as exc:
            print(
                f"Direct text click failed: {exc}"
            )

        # --------------------------------------------------------
        # Attempt 2: click clickable ancestors.
        # --------------------------------------------------------

        ancestor_selectors = [
            "xpath=ancestor::a[1]",
            "xpath=ancestor::td[1]",
            "xpath=ancestor::li[1]",
            "xpath=ancestor::div[1]",
            "xpath=parent::*",
        ]

        for selector in ancestor_selectors:
            try:
                parent = element.locator(
                    selector
                ).first

                if await parent.count() == 0:
                    continue

                try:
                    visible = await parent.is_visible()
                except Exception:
                    visible = True

                if not visible:
                    continue

                print(
                    f"Trying ancestor: {selector}"
                )

                await parent.click(
                    timeout=DEFAULT_TIMEOUT,
                    force=True,
                )

                await frame.page.wait_for_timeout(
                    1_000
                )

                if await wait_for_international_selector(
                    frame,
                    timeout_ms=5_000,
                ):
                    print(
                        "International calculator activated."
                    )
                    return True

            except Exception as exc:
                print(
                    f"Ancestor click failed "
                    f"({selector}): {exc}"
                )

    # ------------------------------------------------------------
    # Fallback: locate the dx-vam span directly.
    # ------------------------------------------------------------

    print(
        "Trying direct .dx-vam search..."
    )

    spans = frame.locator(
        "span.dx-vam"
    )

    span_count = await spans.count()

    print(
        f".dx-vam spans found: {span_count}"
    )

    for i in range(span_count):
        span = spans.nth(i)

        try:
            text = clean_text(
                await span.inner_text()
            )

            if text != "Međunarodni promet":
                continue

            print(
                "Found exact international tab "
                "through span.dx-vam."
            )

            # Click the span.
            try:
                await span.click(
                    timeout=DEFAULT_TIMEOUT,
                    force=True,
                )

                if await wait_for_international_selector(
                    frame
                ):
                    return True

            except Exception:
                pass

            # Click its ancestors.
            for selector in (
                "xpath=ancestor::a[1]",
                "xpath=ancestor::td[1]",
                "xpath=ancestor::li[1]",
                "xpath=ancestor::div[1]",
                "xpath=parent::*",
            ):
                try:
                    parent = span.locator(
                        selector
                    ).first

                    await parent.click(
                        timeout=DEFAULT_TIMEOUT,
                        force=True,
                    )

                    if await wait_for_international_selector(
                        frame
                    ):
                        return True

                except Exception:
                    continue

        except Exception:
            continue

    # ------------------------------------------------------------
    # JavaScript fallback.
    #
    # We find the span whose visible text is exactly the requested
    # tab and dispatch a real mouse click on it.
    # ------------------------------------------------------------

    print(
        "Trying JavaScript mouse click fallback..."
    )

    try:
        clicked = await frame.evaluate(
            """
            () => {
                const elements =
                    Array.from(
                        document.querySelectorAll(
                            'span, a, td, div, li'
                        )
                    );

                const target = elements.find(
                    el =>
                        el.textContent.trim() ===
                        'Međunarodni promet'
                );

                if (!target) {
                    return false;
                }

                target.scrollIntoView({
                    block: 'center',
                    inline: 'center'
                });

                target.dispatchEvent(
                    new MouseEvent(
                        'click',
                        {
                            bubbles: true,
                            cancelable: true,
                            view: window
                        }
                    )
                );

                return true;
            }
            """
        )

        print(
            f"JavaScript click result: {clicked}"
        )

        if clicked:
            if await wait_for_international_selector(
                frame,
                timeout_ms=10_000,
            ):
                print(
                    "International calculator activated."
                )
                return True

    except Exception as exc:
        print(
            f"JavaScript click failed: {exc}"
        )

    return False


async def wait_for_international_selector(
    frame,
    timeout_ms=10_000,
):
    """
    Wait until ddlMeDoOdrediste exists and has options.
    """

    deadline = (
        asyncio.get_running_loop().time()
        + timeout_ms / 1000
    )

    while (
        asyncio.get_running_loop().time()
        < deadline
    ):
        try:
            select = frame.locator(
                "#ddlMeDoOdrediste"
            )

            if await select.count() > 0:
                option_count = await select.locator(
                    "option"
                ).count()

                if option_count > 0:
                    try:
                        if await select.is_visible():
                            return True
                    except Exception:
                        return True

        except Exception:
            pass

        await frame.page.wait_for_timeout(
            500
        )

    return False


async def get_country_dropdown(frame):
    """
    The exact international destination selector supplied by the
    user:

        <select id="ddlMeDoOdrediste">
    """

    selector = frame.locator(
        "#ddlMeDoOdrediste"
    )

    if await selector.count() == 0:
        return None

    try:
        if not await selector.is_visible():
            return None
    except Exception:
        pass

    option_count = await selector.locator(
        "option"
    ).count()

    print(
        f"International country dropdown options: "
        f"{option_count}"
    )

    if option_count == 0:
        return None

    return selector


async def read_dropdown_contents(select):
    """
    Read the dropdown exactly as supplied by the website.

    NOTHING is filtered out.

    Original order is preserved.

    The option text is used exactly as displayed by the browser,
    after only normalizing surrounding whitespace.
    """

    print()
    print("=" * 70)
    print("READING LIST 1")
    print("=" * 70)

    options = select.locator(
        "option"
    )

    count = await options.count()

    print(
        f"Reading {count} option elements."
    )

    countries = []

    for i in range(count):
        option = options.nth(i)

        try:
            text = clean_text(
                await option.inner_text()
            )

            # IMPORTANT:
            # Do not remove placeholders, duplicates, territories,
            # unusual entries, etc.
            #
            # Every actual <option> becomes one line.
            countries.append(text)

        except Exception as exc:
            print(
                f"Could not read option {i}: {exc}"
            )

    print(
        f"List 1 complete: {len(countries)} entries."
    )

    return countries


async def select_dopisnica(frame):
    """
    Click the exact Dopisnica image button supplied by the user:

        <input
            type="image"
            name="ImageButton8"
            id="ImageButton8"
            title="Dopisnica"
            src="Ikonice/Dopisnica_Aktivna.png"
        >
    """

    print(
        "Selecting Dopisnica..."
    )

    selector = frame.locator(
        "#ImageButton8"
    )

    if await selector.count() == 0:
        print(
            "ImageButton8 not found."
        )
        return False

    try:
        await selector.click(
            timeout=DEFAULT_TIMEOUT,
            force=True,
        )

        await frame.page.wait_for_timeout(
            1_000
        )

        print(
            "Dopisnica selected."
        )

        return True

    except Exception as exc:
        print(
            f"Dopisnica click failed: {exc}"
        )
        return False


async def select_air_transport(frame):
    """
    Select Avionski prijenos.

    The supplied HTML identifies the control as:

        id="chbMeDoAvionski"
    """

    print(
        "Selecting Avionski prijenos..."
    )

    checkbox = frame.locator(
        "#chbMeDoAvionski"
    )

    if await checkbox.count() == 0:
        print(
            "chbMeDoAvionski not found."
        )
        return False

    try:
        if not await checkbox.is_checked():
            await checkbox.check(
                force=True
            )

        await frame.page.wait_for_timeout(
            500
        )

        print(
            "Avionski prijenos selected."
        )

        return True

    except Exception as exc:
        print(
            f"Could not select Avionski prijenos: {exc}"
        )
        return False


async def enter_10_grams(frame):
    """
    Exact supplied weight input:

        id="tbxMeDoAvioTezina"
    """

    print(
        "Entering 10 grams..."
    )

    field = frame.locator(
        "#tbxMeDoAvioTezina"
    )

    if await field.count() == 0:
        print(
            "tbxMeDoAvioTezina not found."
        )
        return False

    try:
        await field.fill("10")

        print(
            "Weight set to 10 g."
        )

        return True

    except Exception as exc:
        print(
            f"Could not enter weight: {exc}"
        )
        return False


async def click_calculate(frame):
    """
    Exact supplied calculate button:

        id="btnMeDoIzracunaj"
    """

    print(
        "Clicking Izračunaj..."
    )

    button = frame.locator(
        "#btnMeDoIzracunaj"
    )

    if await button.count() == 0:
        print(
            "btnMeDoIzracunaj not found."
        )
        return False

    try:
        await button.click(
            timeout=DEFAULT_TIMEOUT,
            force=True,
        )

        await frame.page.wait_for_timeout(
            1_000
        )

        print(
            "Izračunaj clicked."
        )

        return True

    except Exception as exc:
        print(
            f"Izračunaj click failed: {exc}"
        )
        return False


async def test_country(
    frame,
    country_value,
    country_name,
):
    """
    Test one country.

    A country belongs in List 2 ONLY if the exact requested
    unavailable-service message appears after clicking Izračunaj.
    """

    select = frame.locator(
        "#ddlMeDoOdrediste"
    )

    try:
        await select.select_option(
            value=country_value
        )

        await frame.page.wait_for_timeout(
            300
        )

        # Make sure the requested transport/weight remain set.
        checkbox = frame.locator(
            "#chbMeDoAvionski"
        )

        if await checkbox.count() > 0:
            try:
                if not await checkbox.is_checked():
                    await checkbox.check(
                        force=True
                    )
                    await frame.page.wait_for_timeout(
                        300
                    )
            except Exception:
                pass

        field = frame.locator(
            "#tbxMeDoAvioTezina"
        )

        if await field.count() > 0:
            try:
                await field.fill("10")
            except Exception:
                pass

        button = frame.locator(
            "#btnMeDoIzracunaj"
        )

        if await button.count() == 0:
            return False

        await button.click(
            timeout=DEFAULT_TIMEOUT,
            force=True,
        )

        # Wait for the exact message.
        message_locator = frame.get_by_text(
            UNAVAILABLE_MESSAGE,
            exact=False,
        )

        try:
            await message_locator.first.wait_for(
                state="visible",
                timeout=5_000,
            )

            print(
                f"UNAVAILABLE: {country_name}"
            )

            return True

        except PlaywrightTimeoutError:
            pass

        # Sometimes the UpdatePanel updates body text without
        # making a newly-created locator immediately visible.
        deadline = (
            asyncio.get_running_loop().time()
            + 5
        )

        while (
            asyncio.get_running_loop().time()
            < deadline
        ):
            body = await get_body_text(
                frame
            )

            if UNAVAILABLE_MESSAGE.casefold() in body.casefold():
                print(
                    f"UNAVAILABLE: {country_name}"
                )

                return True

            await frame.page.wait_for_timeout(
                300
            )

        print(
            f"AVAILABLE/OTHER: {country_name}"
        )

        return False

    except Exception as exc:
        print(
            f"ERROR testing {country_name}: {exc}"
        )

        return False


async def main():
    print()
    print("=" * 70)
    print("JP BH POŠTA COUNTRY MONITOR")
    print("=" * 70)
    print(
        f"URL: {URL}"
    )
    print(
        f"Output: {OUTPUT_FILE}"
    )

    # Always start with an output file.
    OUTPUT_FILE.write_text(
        "",
        encoding="utf-8",
    )

    async with async_playwright() as p:

        browser = await p.chromium.launch(
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
            # ========================================================
            # OPEN PAGE
            # ========================================================

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
                    "Navigation timeout; continuing."
                )

            await page.wait_for_timeout(
                2_000
            )

            # ========================================================
            # FIND IFRAME
            # ========================================================

            frame = await find_calculator_frame(
                page
            )

            if frame is None:
                raise RuntimeError(
                    "Could not locate calculator iframe."
                )

            print(
                f"Calculator frame URL: {frame.url}"
            )

            # ========================================================
            # SELECT INTERNATIONAL TAB
            # ========================================================

            activated = await click_international_tab(
                frame
            )

            if not activated:
                raise RuntimeError(
                    "Could not select Međunarodni promet."
                )

            # ========================================================
            # FIND COUNTRY DROPDOWN
            # ========================================================

            print(
                "Waiting for international country dropdown..."
            )

            deadline = (
                asyncio.get_running_loop().time()
                + FRAME_TIMEOUT / 1000
            )

            country_select = None

            while (
                asyncio.get_running_loop().time()
                < deadline
            ):
                country_select = (
                    await get_country_dropdown(
                        frame
                    )
                )

                if country_select is not None:
                    break

                await frame.page.wait_for_timeout(
                    500
                )

            if country_select is None:
                raise RuntimeError(
                    "International country dropdown "
                    "ddlMeDoOdrediste was not found."
                )

            # ========================================================
            # LIST 1
            # ========================================================

            list1 = await read_dropdown_contents(
                country_select
            )

            if not list1:
                raise RuntimeError(
                    "Country dropdown was found but "
                    "contained no options."
                )

            # ========================================================
            # DOPISNICA
            # ========================================================

            if not await select_dopisnica(
                frame
            ):
                raise RuntimeError(
                    "Could not select Dopisnica."
                )

            # ========================================================
            # AVIONSKI PRIJENOS
            # ========================================================

            if not await select_air_transport(
                frame
            ):
                raise RuntimeError(
                    "Could not select Avionski prijenos."
                )

            # ========================================================
            # 10 GRAMS
            # ========================================================

            if not await enter_10_grams(
                frame
            ):
                raise RuntimeError(
                    "Could not enter 10 grams."
                )

            # ========================================================
            # LIST 2
            # ========================================================

            print()
            print("=" * 70)
            print("TESTING LIST 2")
            print("=" * 70)

            list2 = []

            for index, option in enumerate(
                list1,
                1,
            ):
                # We need the value associated with the exact
                # corresponding option, so retrieve it directly.
                options = country_select.locator(
                    "option"
                )

                option_element = options.nth(
                    index - 1
                )

                value = (
                    await option_element.get_attribute(
                        "value"
                    )
                )

                if value is None:
                    value = ""

                print()
                print(
                    f"[{index}/{len(list1)}] "
                    f"{option}"
                )

                unavailable = await test_country(
                    frame,
                    value,
                    option,
                )

                if unavailable:
                    list2.append(
                        option
                    )

                # Save after every country.
                #
                # This means that if GitHub Actions stops unexpectedly,
                # the file still contains the progress made so far.
                save_output(
                    list1,
                    list2,
                )

                await frame.page.wait_for_timeout(
                    200
                )

            # ========================================================
            # FINAL OUTPUT
            # ========================================================

            save_output(
                list1,
                list2,
            )

            print()
            print("=" * 70)
            print("MONITOR COMPLETE")
            print("=" * 70)

            print(
                f"List 1: {len(list1)} entries"
            )

            print(
                f"List 2: {len(list2)} entries"
            )

            print()
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
            "Interrupted."
        )
        raise
