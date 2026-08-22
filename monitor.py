import asyncio
import os
import re
from pathlib import Path

from playwright.async_api import async_playwright


URL = os.environ.get(
    "CALCULATOR_URL",
    "https://www.posta.ba/kalkulator-cijena/",
)

CALCULATOR_FRAME_URL = "bhpwebout.posta.ba/KalkulatorCijena_WEB_app/Bos/Default.aspx"

ERROR_TEXT = "Prijem pošiljaka se trenutno ne vrši za odabranu državu"

COUNTRIES_FILE = Path("countries.txt")


def section(title):
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def clean_text(text):
    return re.sub(r"\s+", " ", text or "").strip()


async def save_text(path, text):
    Path(path).write_text(text or "", encoding="utf-8")


async def dump_frame(frame, filename_html, filename_txt):
    try:
        html = await frame.content()
    except Exception as exc:
        html = f"ERROR GETTING FRAME HTML:\n{exc}"

    await save_text(filename_html, html)

    try:
        text = await frame.locator("body").inner_text(timeout=5000)
    except Exception:
        text = ""

    await save_text(filename_txt, clean_text(text))

    return html, text


async def find_calculator_frame(page):
    """
    The calculator is hosted in the external bhpwebout.posta.ba iframe.
    Do NOT assume frame 0 is the calculator.
    """

    section("LOCATING CALCULATOR IFRAME")

    for index, frame in enumerate(page.frames):
        print(f"Checking frame {index}: {frame.url}")

        if CALCULATOR_FRAME_URL.lower() in frame.url.lower():
            print(f"FOUND CALCULATOR FRAME: {index}")
            print(f"Calculator URL: {frame.url}")
            return frame

    return None


async def activate_international(frame):
    """
    The initial calculator page is the domestic calculator.

    The international calculator is activated through the tab control.
    We deliberately inspect several possible ASPx/HTML representations
    instead of depending on one exact selector.
    """

    section("ACTIVATING MEĐUNARODNI PROMET")

    # First look for exact text in the calculator frame.
    candidates = [
        frame.get_by_text("Međunarodni promet", exact=True),
        frame.get_by_text("Međunarodni promet"),
    ]

    for locator in candidates:
        try:
            count = await locator.count()
            print(f"Text candidate count: {count}")

            for i in range(count):
                item = locator.nth(i)

                try:
                    if await item.is_visible():
                        print("Found visible Međunarodni promet element.")
                        print("Tag:", await item.evaluate("(e) => e.tagName"))
                        print(
                            "HTML:",
                            (await item.evaluate("(e) => e.outerHTML"))[:2000],
                        )

                        await item.click(force=True)

                        await frame.wait_for_timeout(2500)

                        return True

                except Exception as exc:
                    print(f"Candidate {i} failed: {exc}")

        except Exception as exc:
            print(f"Text locator failed: {exc}")

    # ASPx controls may not expose the visible text as a simple element.
    # Search the DOM for anything containing the text.
    print("Searching DOM for Međunarodni promet...")

    try:
        matches = await frame.locator(
            "xpath=//*[contains(normalize-space(.), 'Međunarodni promet')]"
        ).count()

        print(f"DOM matches: {matches}")

        for i in range(min(matches, 30)):
            item = frame.locator(
                "xpath=//*[contains(normalize-space(.), 'Međunarodni promet')]"
            ).nth(i)

            try:
                if not await item.is_visible():
                    continue

                tag = await item.evaluate("(e) => e.tagName")
                text = clean_text(await item.inner_text())
                html = (await item.evaluate("(e) => e.outerHTML"))[:3000]

                print(f"DOM candidate {i}:")
                print(f"  tag: {tag}")
                print(f"  text: {text}")
                print(f"  html: {html}")

                await item.click(force=True)
                await frame.wait_for_timeout(2500)

                return True

            except Exception as exc:
                print(f"DOM candidate {i} failed: {exc}")

    except Exception as exc:
        print(f"DOM search failed: {exc}")

    return False


async def find_country_select(frame):
    """
    Search for the international destination dropdown.

    Expected ID from the original HTML supplied by the user:
        ddlMeDoOdrediste
    """

    selectors = [
        "#ddlMeDoOdrediste",
        "select[name='ddlMeDoOdrediste']",
        "select[id*='MeDoOdrediste']",
        "select[name*='Odrediste']",
        "select[id*='Odrediste']",
    ]

    for selector in selectors:
        try:
            locator = frame.locator(selector)
            count = await locator.count()

            if count:
                print(f"FOUND COUNTRY DROPDOWN: {selector}")
                return locator.first

        except Exception as exc:
            print(f"Selector {selector} failed: {exc}")

    return None


async def get_country_options(select):
    options = await select.locator("option").evaluate_all(
        """
        options => options.map(o => ({
            value: o.value,
            text: (o.textContent || '').trim()
        }))
        """
    )

    countries = []

    for option in options:
        name = clean_text(option.get("text", ""))

        if name:
            countries.append(
                {
                    "name": name,
                    "value": option.get("value", ""),
                }
            )

    return countries


async def find_checkbox(frame):
    selectors = [
        "#chbMeDoAvionski",
        "input[name='chbMeDoAvionski']",
        "input[id*='MeDoAvionski']",
        "input[name*='Avionski']",
    ]

    for selector in selectors:
        try:
            locator = frame.locator(selector)

            if await locator.count():
                print(f"FOUND AIR checkbox: {selector}")
                return locator.first

        except Exception:
            pass

    return None


async def find_weight_input(frame):
    selectors = [
        "#tbxMeDoAvioTezina",
        "input[name='tbxMeDoAvioTezina']",
        "input[id*='MeDoAvioTezina']",
        "input[name*='AvioTezina']",
    ]

    for selector in selectors:
        try:
            locator = frame.locator(selector)

            if await locator.count():
                print(f"FOUND AIR WEIGHT INPUT: {selector}")
                return locator.first

        except Exception:
            pass

    return None


async def find_calculate_button(frame):
    selectors = [
        "#btnMeDoIzracunaj",
        "input[name='btnMeDoIzracunaj']",
        "input[value='Izračunaj']",
        "input[type='submit'][value*='Izračunaj']",
        "input[type='submit']",
    ]

    for selector in selectors:
        try:
            locator = frame.locator(selector)
            count = await locator.count()

            if count:
                print(f"FOUND CALCULATE CONTROL: {selector}")

                for i in range(count):
                    candidate = locator.nth(i)

                    try:
                        if await candidate.is_visible():
                            return candidate
                    except Exception:
                        pass

                return locator.first

        except Exception:
            pass

    return None


async def error_message_present(frame):
    try:
        body_text = clean_text(await frame.locator("body").inner_text())

        if ERROR_TEXT in body_text:
            return True

    except Exception:
        pass

    # Also inspect HTML, because the message may be in a hidden/updated
    # ASP.NET element whose text isn't immediately represented in body text.
    try:
        html = await frame.content()

        if ERROR_TEXT in html:
            return True

    except Exception:
        pass

    return False


async def wait_for_result(frame):
    """
    Give ASP.NET postback/update-panel processing time to complete.
    """

    for _ in range(20):
        await frame.wait_for_timeout(500)

        if await error_message_present(frame):
            return True

        # If a visible price/result appeared, stop waiting.
        try:
            text = clean_text(await frame.locator("body").inner_text())

            price_patterns = [
                r"\d+,\d+\s*KM",
                r"\d+\.\d+\s*KM",
                r"\d+\s*KM",
            ]

            if any(re.search(pattern, text, re.I) for pattern in price_patterns):
                return False

        except Exception:
            pass

    return await error_message_present(frame)


async def write_countries_file(all_countries, unavailable):
    """
    Output format:

    ALL COUNTRIES
    -------------
    Afganistan
    Albanija
    ...

    UNAVAILABLE COUNTRIES
    ---------------------
    ...
    """

    lines = []

    lines.append("ALL COUNTRIES")
    lines.append("=============")

    for country in all_countries:
        lines.append(country)

    lines.append("")
    lines.append("UNAVAILABLE COUNTRIES")
    lines.append("=====================")

    for country in unavailable:
        lines.append(country)

    lines.append("")

    COUNTRIES_FILE.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


async def diagnostic_snapshot(frame, filename="diagnostic.png"):
    try:
        await frame.screenshot(
            path=filename,
            full_page=True,
        )
        print(f"Screenshot saved: {filename}")
    except Exception as exc:
        print(f"Could not save screenshot: {exc}")


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

        # ------------------------------------------------------------
        # MAIN PAGE
        # ------------------------------------------------------------

        section("OPENING MAIN PAGE")

        response = await page.goto(
            URL,
            wait_until="domcontentloaded",
            timeout=60000,
        )

        print(f"HTTP status: {response.status if response else 'unknown'}")
        print(f"Final URL: {page.url}")
        print(f"Page title: {await page.title()}")

        await page.wait_for_timeout(5000)

        # Save main page.
        try:
            html = await page.content()
            await save_text("page.html", html)
            print(f"Saved: page.html ({len(html):,} bytes)")
        except Exception as exc:
            print(f"Could not save page.html: {exc}")

        # ------------------------------------------------------------
        # FIND REAL CALCULATOR FRAME
        # ------------------------------------------------------------

        frame = await find_calculator_frame(page)

        if frame is None:
            section("CALCULATOR IFRAME NOT FOUND")

            for i, f in enumerate(page.frames):
                print(i, f.url)

            await page.screenshot(
                path="diagnostic.png",
                full_page=True,
            )

            raise RuntimeError(
                "Could not find the bhpwebout.posta.ba calculator iframe."
            )

        # Give iframe scripts time to initialize.
        await frame.wait_for_timeout(3000)

        # ------------------------------------------------------------
        # SAVE IFRAME
        # ------------------------------------------------------------

        section("SAVING CALCULATOR IFRAME")

        iframe_html, iframe_text = await dump_frame(
            frame,
            "iframe.html",
            "iframe.txt",
        )

        print(f"Saved iframe.html ({len(iframe_html):,} bytes)")
        print(f"Saved iframe.txt ({len(iframe_text):,} bytes)")

        # ------------------------------------------------------------
        # IMPORTANT:
        # DO NOT USE FRAME 0.
        # The real calculator is the external frame.
        # ------------------------------------------------------------

        section("CHECKING INITIAL CALCULATOR")

        country_select = await find_country_select(frame)

        if country_select is not None:
            print(
                "Country dropdown is already present before "
                "activating international traffic."
            )
        else:
            print(
                "Country dropdown is not present yet. "
                "Attempting to activate Međunarodni promet."
            )

        # ------------------------------------------------------------
        # ACTIVATE INTERNATIONAL
        # ------------------------------------------------------------

        if country_select is None:

            activated = await activate_international(frame)

            if not activated:
                await dump_frame(
                    frame,
                    "iframe_after_activation_failure.html",
                    "iframe_after_activation_failure.txt",
                )

                await diagnostic_snapshot(frame)

                raise RuntimeError(
                    "Could not locate/click Međunarodni promet."
                )

            await frame.wait_for_timeout(3000)

            country_select = await find_country_select(frame)

        # ------------------------------------------------------------
        # COUNTRY DROPDOWN
        # ------------------------------------------------------------

        section("LOCATING COUNTRY DROPDOWN")

        if country_select is None:

            # Save everything again after attempted activation.
            await dump_frame(
                frame,
                "iframe_after_activation.html",
                "iframe_after_activation.txt",
            )

            await diagnostic_snapshot(frame)

            print()
            print("Visible calculator text:")
            try:
                print(clean_text(await frame.locator("body").inner_text()))
            except Exception:
                pass

            raise RuntimeError(
                "International calculator activated, but "
                "#ddlMeDoOdrediste was not found."
            )

        print("Country dropdown found.")

        countries = await get_country_options(country_select)

        section("COUNTRIES FOUND")

        print(f"Number of countries/options: {len(countries)}")

        for index, country in enumerate(countries, start=1):
            print(
                f"{index:3d}. "
                f"{country['name']} "
                f"(value={country['value']})"
            )

        if not countries:
            raise RuntimeError(
                "Country dropdown exists but contains no options."
            )

        # ------------------------------------------------------------
        # AIR TRANSPORT
        # ------------------------------------------------------------

        section("SETTING AVIONSKI PRIJENOS")

        air_checkbox = await find_checkbox(frame)

        if air_checkbox is None:
            print(
                "Avionski Prijenos checkbox not found. "
                "This may be because the current service type "
                "does not expose it."
            )
        else:
            try:
                checked = await air_checkbox.is_checked()

                if not checked:
                    print("Checking Avionski Prijenos...")
                    await air_checkbox.check(force=True)
                    await frame.wait_for_timeout(1000)
                else:
                    print("Avionski Prijenos already checked.")

            except Exception as exc:
                print(f"Could not check Avionski Prijenos: {exc}")

        weight_input = await find_weight_input(frame)

        if weight_input is not None:
            try:
                await weight_input.fill("10")
                print("Air weight set to 10 grams.")
            except Exception as exc:
                print(f"Could not enter weight: {exc}")
        else:
            print("Air weight input not found.")

        # ------------------------------------------------------------
        # CALCULATE
        # ------------------------------------------------------------

        calculate_button = await find_calculate_button(frame)

        if calculate_button is None:
            await dump_frame(
                frame,
                "iframe_before_calculation_failure.html",
                "iframe_before_calculation_failure.txt",
            )

            await diagnostic_snapshot(frame)

            raise RuntimeError(
                "Could not find the international Izračunaj button."
            )

        print("Calculate control found.")

        # ------------------------------------------------------------
        # SCAN COUNTRIES IN ORIGINAL DROPDOWN ORDER
        # ------------------------------------------------------------

        section("CHECKING COUNTRIES")

        unavailable = []

        for index, country in enumerate(countries, start=1):

            name = country["name"]
            value = country["value"]

            print()
            print(
                f"[{index}/{len(countries)}] "
                f"{name} ({value})"
            )

            try:
                # Re-find the select every iteration. ASP.NET postbacks
                # can replace the DOM element.
                select = await find_country_select(frame)

                if select is None:
                    print("ERROR: country dropdown disappeared.")

                    await dump_frame(
                        frame,
                        "failure_dropdown_disappeared.html",
                        "failure_dropdown_disappeared.txt",
                    )

                    raise RuntimeError(
                        "Country dropdown disappeared during country scan."
                    )

                await select.select_option(value=value)

                # ASP.NET onchange may perform a postback.
                await frame.wait_for_timeout(1200)

                # The DOM may have been replaced.
                select = await find_country_select(frame)

                if select is None:
                    raise RuntimeError(
                        "Country dropdown disappeared after selection."
                    )

                # Re-find calculation control too.
                calculate_button = await find_calculate_button(frame)

                if calculate_button is None:
                    raise RuntimeError(
                        "Calculate button disappeared after selecting "
                        f"{name}."
                    )

                # Click and wait for the ASP.NET result.
                print("  Clicking Izračunaj...")

                try:
                    await calculate_button.click(
                        force=True,
                        timeout=10000,
                    )
                except Exception as click_exc:
                    print(f"  Normal click failed: {click_exc}")
                    print("  Trying form submit...")

                    await calculate_button.evaluate(
                        "(element) => element.click()"
                    )

                has_error = await wait_for_result(frame)

                if has_error:
                    print(
                        "  RESULT: UNAVAILABLE "
                        f"('{ERROR_TEXT}')"
                    )
                    unavailable.append(name)
                else:
                    print("  RESULT: price/result returned")

            except Exception as exc:
                print(f"  ERROR while checking {name}: {exc}")

                # Save diagnostic state but continue with remaining countries.
                try:
                    await frame.screenshot(
                        path=f"diagnostic_country_{index}.png",
                        full_page=True,
                    )
                except Exception:
                    pass

                # We do NOT automatically classify an unexpected
                # technical failure as unavailable.
                continue

        # ------------------------------------------------------------
        # WRITE OUTPUT
        # ------------------------------------------------------------

        section("WRITING COUNTRIES.TXT")

        await write_countries_file(
            [country["name"] for country in countries],
            unavailable,
        )

        print(f"Saved: {COUNTRIES_FILE}")
        print(f"All countries: {len(countries)}")
        print(f"Unavailable countries: {len(unavailable)}")

        # ------------------------------------------------------------
        # FINAL DIAGNOSTIC
        # ------------------------------------------------------------

        section("FINAL RESULT")

        print()
        print("ALL COUNTRIES")
        print("-------------")

        for country in countries:
            print(country["name"])

        print()
        print("UNAVAILABLE COUNTRIES")
        print("---------------------")

        for country in unavailable:
            print(country)

        await dump_frame(
            frame,
            "final_iframe.html",
            "final_iframe.txt",
        )

        await diagnostic_snapshot(
            frame,
            "diagnostic.png",
        )

        await browser.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print()
        print("=" * 70)
        print("MONITOR FAILED")
        print("=" * 70)
        print(f"{type(exc).__name__}: {exc}")
        raise
