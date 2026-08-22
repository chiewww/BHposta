import asyncio
import os
import sys
from pathlib import Path

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

CALCULATOR_URL = os.environ.get(
    "CALCULATOR_URL",
    "https://www.posta.ba/kalkulator-cijena/",
)

OUTPUT_FILE = Path("countries.txt")

ERROR_MESSAGE = "Prijem pošiljaka se trenutno ne vrši za odabranu državu"

DESTINATION_SELECT = "#ddlMeDoOdrediste"

# From your HTML:
AIR_CHECKBOX = "#chbMeDoAvionski"
AIR_WEIGHT_INPUT = "#tbxMeDoAvioTezina"

CALCULATE_BUTTON = "#btnMeDoIzracunaj"

# The calculator is an ASP.NET UpdatePanel application, so give
# postbacks plenty of time.
TIMEOUT_MS = 30_000

# Small pause between countries. This is deliberately conservative
# to avoid hammering the website.
DELAY_BETWEEN_COUNTRIES_SECONDS = 1.0


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

async def wait_for_page_ready(page):
    await page.wait_for_load_state("domcontentloaded", timeout=TIMEOUT_MS)

    # ASP.NET may continue updating the page after DOMContentLoaded.
    await page.wait_for_timeout(1000)


async def get_destinations(page):
    """
    Read destinations directly from the live <select>.

    IMPORTANT:
    The order returned here is the order in the website's dropdown.
    We intentionally do NOT sort it.
    """

    select = page.locator(DESTINATION_SELECT)

    await select.wait_for(state="attached", timeout=TIMEOUT_MS)

    destinations = await select.locator("option").evaluate_all(
        """
        options => options.map(option => ({
            value: option.value,
            name: option.textContent.trim()
        }))
        """
    )

    if not destinations:
        raise RuntimeError("No destination options were found.")

    return destinations


async def select_air_transport(page):
    """
    Enable Avionski prijenos and enter 10 grams.

    The checkbox causes an ASP.NET postback, so wait for the
    resulting field to appear.
    """

    checkbox = page.locator(AIR_CHECKBOX)

    if not await checkbox.is_checked():
        await checkbox.check()

        # The checkbox has an onclick __doPostBack() in the supplied HTML.
        await page.wait_for_timeout(1000)

    weight = page.locator(AIR_WEIGHT_INPUT)

    await weight.wait_for(state="visible", timeout=TIMEOUT_MS)

    await weight.fill("10")


async def get_visible_page_text(page):
    """
    Get the current rendered page text.

    The unavailable message may be inserted into an UpdatePanel,
    so we inspect the rendered DOM after the calculation.
    """

    return await page.locator("body").inner_text()


async def calculate_for_destination(page, destination):
    """
    Select one destination and click Izračunaj.

    Returns True when the exact unavailable message is present.
    """

    select = page.locator(DESTINATION_SELECT)

    # Selecting the destination triggers the site's onchange
    # __doPostBack().
    await select.select_option(destination["value"])

    # Allow the ASP.NET UpdatePanel/postback to finish.
    await page.wait_for_timeout(1000)

    # The page may have reconstructed the controls during the postback.
    await select_air_transport(page)

    # Make sure the value survived the postback.
    weight = page.locator(AIR_WEIGHT_INPUT)
    await weight.fill("10")

    calculate = page.locator(CALCULATE_BUTTON)
    await calculate.wait_for(state="visible", timeout=TIMEOUT_MS)

    await calculate.click()

    # Wait for the server-side calculation/update panel.
    await page.wait_for_timeout(1500)

    text = await get_visible_page_text(page)

    return ERROR_MESSAGE in text


async def main():
    if "REPLACE-WITH-THE-ACTUAL-HOST" in CALCULATOR_URL:
        print(
            "ERROR: Set CALCULATOR_URL to the actual JP BH Pošta calculator URL.",
            file=sys.stderr,
        )
        sys.exit(1)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True
        )

        page = await browser.new_page(
            viewport={"width": 1280, "height": 1000},
            locale="hr-HR",
        )

        page.set_default_timeout(TIMEOUT_MS)

        print(f"Opening: {CALCULATOR_URL}")

        await page.goto(
            CALCULATOR_URL,
            wait_until="domcontentloaded",
            timeout=TIMEOUT_MS,
        )

        await wait_for_page_ready(page)

        # Verify that this really is the expected calculator.
        if not await page.locator(DESTINATION_SELECT).count():
            raise RuntimeError(
                f"Could not find {DESTINATION_SELECT}. "
                "The calculator URL or page structure may have changed."
            )

        destinations = await get_destinations(page)

        print(f"Found {len(destinations)} destinations.")

        unavailable = []

        for index, destination in enumerate(destinations, start=1):
            print(
                f"[{index}/{len(destinations)}] "
                f"{destination['name']} ({destination['value']})"
            )

            try:
                is_unavailable = await calculate_for_destination(
                    page,
                    destination,
                )

                if is_unavailable:
                    unavailable.append(destination)

                    print("    -> UNAVAILABLE")
                else:
                    print("    -> available / no unavailable message")

            except PlaywrightTimeoutError as exc:
                print(
                    f"    -> ERROR/TIMEOUT: {exc}",
                    file=sys.stderr,
                )

                # Do not silently classify a timeout as unavailable.
                # Failing the entire run is safer than publishing
                # incorrect data.
                raise

            except Exception as exc:
                print(
                    f"    -> ERROR: {exc}",
                    file=sys.stderr,
                )
                raise

            await page.wait_for_timeout(
                int(DELAY_BETWEEN_COUNTRIES_SECONDS * 1000)
            )

        # -------------------------------------------------------------
        # Create the monitored text file.
        #
        # Both sections retain the website's original dropdown order.
        # -------------------------------------------------------------

        lines = []

        lines.append("ALL DESTINATIONS")
        lines.append("================")
        lines.extend(destination["name"] for destination in destinations)

        lines.append("")
        lines.append("UNAVAILABLE")
        lines.append("===========")
        lines.extend(destination["name"] for destination in unavailable)

        content = "\n".join(lines) + "\n"

        OUTPUT_FILE.write_text(
            content,
            encoding="utf-8",
        )

        print()
        print(f"Destinations: {len(destinations)}")
        print(f"Unavailable:  {len(unavailable)}")
        print(f"Written:      {OUTPUT_FILE}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
