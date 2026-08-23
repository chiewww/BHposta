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

OUTPUT_FILE = Path("countries.txt")

# Exact selectors supplied from the calculator HTML.
COUNTRY_SELECT = "#ddlMeDoOdrediste"
DOPISNICA_BUTTON = "#ImageButton8"
AVIONSKI_CHECKBOX = "#chbMeDoAvionski"
WEIGHT_INPUT = "#tbxMeDoAvioTezina"
CALCULATE_BUTTON = "#btnMeDoIzracunaj"

NAVIGATION_TIMEOUT = 30_000
DEFAULT_TIMEOUT = 10_000
FRAME_TIMEOUT = 30_000
RESULT_TIMEOUT = 7_000


def save_text(path, text):
    path.write_text(text, encoding="utf-8")
    print(f"Saved {path}")


def clean_text(text):
    return " ".join((text or "").split())


def is_error_message(text):
    """
    Detect calculator messages indicating that the service is
    unavailable for a destination.
    """

    text = (text or "").casefold()

    error_markers = [
        "nije moguće",
        "nije moguce",
        "nije dostupno",
        "nije dostupna",
        "nije dostupan",
        "ne može se",
        "ne moze se",
        "ne postoji usluga",
        "usluga nije",
        "trenutno nije",
        "odredište nije",
        "odrediste nije",
        "zabranjeno",
        "nedostupno",
        "nedostupna",
        "nedostupan",
        "cannot",
        "not available",
        "unavailable",
        "not permitted",
        "not allowed",
    ]

    return any(
        marker in text
        for marker in error_markers
    )


def looks_like_calculation_result(text):
    """
    Determine whether the calculator appears to have produced
    a result.

    We intentionally do NOT care what the price is. We only care
    whether a result was produced.
    """

    if not text:
        return False

    if is_error_message(text):
        return False

    lowered = text.casefold()

    result_markers = [
        "cijena",
        "cijene",
        "iznos",
        "km",
        "bam",
    ]

    return any(
        marker in lowered
        for marker in result_markers
    )


async def find_calculator_frame(page):
    """
    Find the BH Pošta calculator iframe.

    We identify it by the actual controls rather than depending
    solely on its URL.
    """

    for attempt in range(30):
        for frame in page.frames:

            try:
                if await frame.locator(
                    COUNTRY_SELECT
                ).count() > 0:
                    print(
                        f"Calculator frame found: {frame.url}"
                    )
                    return frame

            except Exception:
                pass

        if attempt < 29:
            await page.wait_for_timeout(1_000)

    return None


async def select_dopisnica(frame):
    """
    Click the Dopisnica image button.
    """

    print("Selecting Dopisnica...")

    button = frame.locator(DOPISNICA_BUTTON)

    await button.wait_for(
        state="visible",
        timeout=FRAME_TIMEOUT,
    )

    await button.click(
        timeout=DEFAULT_TIMEOUT,
        force=True,
    )

    # ASP.NET AJAX may update the calculator after the click.
    await frame.page.wait_for_timeout(1_000)

    print("Dopisnica selected.")


async def read_country_options(frame):
    """
    Read the country dropdown EXACTLY as supplied by the website.

    Important:
    - original order preserved
    - duplicates preserved
    - capitalization preserved
    - spelling preserved
    - accents preserved
    - option text is not normalized
    """

    select = frame.locator(COUNTRY_SELECT)

    await select.wait_for(
        state="visible",
        timeout=FRAME_TIMEOUT,
    )

    options = select.locator("option")
    count = await options.count()

    print(f"Country options found: {count}")

    countries = []

    for i in range(count):
        option = options.nth(i)

        # inner_text() gives us the actual visible option text.
        name = await option.inner_text()

        # Only remove surrounding whitespace.
        # DO NOT normalize, deduplicate, sort, or alter anything else.
        name = name.strip()

        if not name:
            continue

        value = await option.get_attribute("value")

        countries.append(
            {
                "name": name,
                "value": value or "",
            }
        )

    return countries


async def select_air_transport(frame):
    """
    Enable Avionski prijenos.
    """

    checkbox = frame.locator(AVIONSKI_CHECKBOX)

    await checkbox.wait_for(
        state="visible",
        timeout=DEFAULT_TIMEOUT,
    )

    checked = await checkbox.is_checked()

    if not checked:
        await checkbox.check(
            timeout=DEFAULT_TIMEOUT,
            force=True,
        )

    await frame.page.wait_for_timeout(300)


async def set_weight(frame):
    """
    Enter exactly 10 grams.
    """

    weight = frame.locator(WEIGHT_INPUT)

    await weight.wait_for(
        state="visible",
        timeout=DEFAULT_TIMEOUT,
    )

    await weight.fill("10")

    await frame.page.wait_for_timeout(200)


async def get_body_text(frame):
    try:
        return await frame.locator(
            "body"
        ).inner_text(
            timeout=3_000
        )
    except Exception:
        return ""


async def click_calculate(frame):
    button = frame.locator(CALCULATE_BUTTON)

    await button.wait_for(
        state="visible",
        timeout=DEFAULT_TIMEOUT,
    )

    await button.click(
        timeout=DEFAULT_TIMEOUT,
        force=True,
    )


async def calculate_country(
    frame,
    country,
):
    """
    Test one country.

    Returns True if the calculator produces a result.
    Returns False if it produces an unavailable/error message.
    """

    select = frame.locator(COUNTRY_SELECT)

    try:
        # Use the actual option value whenever possible.
        await select.select_option(
            value=country["value"]
        )

        # Selecting the country causes ASP.NET to post back.
        # Give the page time to process that update.
        await frame.page.wait_for_timeout(700)

        # Re-enable/confirm the required settings after the
        # country postback.
        await select_air_transport(frame)
        await set_weight(frame)

        before = await get_body_text(frame)

        await click_calculate(frame)

        deadline = (
            asyncio.get_running_loop().time()
            + RESULT_TIMEOUT / 1000
        )

        while (
            asyncio.get_running_loop().time()
            < deadline
        ):
            await frame.page.wait_for_timeout(400)

            text = await get_body_text(frame)

            if is_error_message(text):
                return False

            if (
                text != before
                and looks_like_calculation_result(text)
            ):
                return True

            if looks_like_calculation_result(text):
                return True

        # If no explicit result was detected, treat it as unavailable.
        return False

    except PlaywrightTimeoutError:
        print(
            f"  Timeout while testing {country['name']}"
        )
        return False

    except Exception as exc:
        print(
            f"  Error while testing {country['name']}: {exc}"
        )
        return False


async def main():

    print("=" * 70)
    print("JP BH POŠTA DAILY COUNTRY MONITOR")
    print("=" * 70)

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

            print(f"Opening: {URL}")

            try:
                await page.goto(
                    URL,
                    wait_until="domcontentloaded",
                    timeout=NAVIGATION_TIMEOUT,
                )

            except PlaywrightTimeoutError:
                print(
                    "Navigation timed out; continuing..."
                )

            await page.wait_for_timeout(2_000)

            frame = await find_calculator_frame(page)

            if frame is None:
                raise RuntimeError(
                    "Could not find calculator iframe."
                )

            # --------------------------------------------------
            # 1. Select Međunarodni promet
            # --------------------------------------------------
            #
            # We locate it by visible text because the exact tab
            # selector was not supplied. This is deliberately
            # limited to the calculator frame.
            #
            international = frame.get_by_text(
                "Međunarodni promet",
                exact=True,
            )

            if await international.count() > 0:
                for i in range(
                    await international.count()
                ):
                    candidate = international.nth(i)

                    try:
                        if await candidate.is_visible():
                            await candidate.click(
                                force=True
                            )
                            await page.wait_for_timeout(1_000)
                            break
                    except Exception:
                        continue

            # --------------------------------------------------
            # 2. Select Dopisnica
            # --------------------------------------------------

            await select_dopisnica(frame)

            # --------------------------------------------------
            # 3. Read List 1
            # --------------------------------------------------

            countries = await read_country_options(frame)

            if not countries:
                raise RuntimeError(
                    "No countries found in #ddlMeDoOdrediste."
                )

            print(
                f"Read {len(countries)} country entries."
            )

            # --------------------------------------------------
            # 4. Test each country
            # --------------------------------------------------

            available = []

            for index, country in enumerate(
                countries,
                1,
            ):

                print(
                    f"[{index}/{len(countries)}] "
                    f"{country['name']}"
                )

                result = await calculate_country(
                    frame,
                    country,
                )

                if result:
                    print("  AVAILABLE")
                    available.append(
                        country["name"]
                    )
                else:
                    print("  UNAVAILABLE")

            # --------------------------------------------------
            # 5. Write exactly two lists
            # --------------------------------------------------

            output = []

            output.append(
                "LIST 1 — MEĐUNARODNI PROMET / DOPISNICA"
            )
            output.append(
                "=========================================="
            )

            for country in countries:
                output.append(
                    country["name"]
                )

            output.append("")
            output.append(
                "LIST 2 — AVAILABLE WITH AVIONSKI PRIJENOS, 10 g"
            )
            output.append(
                "================================================"
            )

            for country in available:
                output.append(country)

            output.append("")

            save_text(
                OUTPUT_FILE,
                "\n".join(output),
            )

            print()
            print("=" * 70)
            print("DONE")
            print("=" * 70)

        finally:
            await context.close()
            await browser.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Interrupted.")
        sys.exit(130)
