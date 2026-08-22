import asyncio
import os
import re
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

CALCULATOR_IFRAME_URL_PART = "bhpwebout.posta.ba/KalkulatorCijena_WEB_app"

COUNTRIES_FILE = Path("countries.txt")
PAGE_FILE = Path("page.html")
IFRAME_FILE = Path("iframe.html")
IFRAME_TEXT_FILE = Path("iframe.txt")
DIAGNOSTIC_FILE = Path("diagnostic.txt")
DIAGNOSTIC_HTML_FILE = Path("diagnostic.html")
RESPONSE_FILE = Path("response.html")

NAVIGATION_TIMEOUT = 30_000
SHORT_TIMEOUT = 2_000
NORMAL_TIMEOUT = 5_000
TOTAL_TIMEOUT = 45_000


def section(title):
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def save_text(path, text):
    try:
        path.write_text(text or "", encoding="utf-8")
        print(f"Saved {path} ({len(text or ''):,} bytes)")
    except Exception as exc:
        print(f"Could not save {path}: {exc}")


async def safe_content(page):
    try:
        return await page.content()
    except Exception:
        return ""


async def safe_screenshot(page, path="diagnostic.png"):
    try:
        await page.screenshot(path=path, full_page=True)
        print(f"Saved {path}")
    except Exception as exc:
        print(f"Could not save screenshot: {exc}")


async def frame_content(frame):
    try:
        return await frame.content()
    except Exception:
        return ""


async def find_calculator_frame(page):
    """
    Find the actual BH Pošta calculator iframe.

    The page itself is frame 0, while the calculator normally appears
    in the bhpwebout.posta.ba iframe.
    """

    section("LOCATING CALCULATOR IFRAME")

    frames = page.frames
    print(f"Number of frames: {len(frames)}")

    # Prefer URL match.
    for index, frame in enumerate(frames):
        try:
            url = frame.url
        except Exception:
            url = ""

        print(f"Checking frame {index}: {url}")

        if CALCULATOR_IFRAME_URL_PART.lower() in url.lower():
            print(f"FOUND CALCULATOR FRAME: {index}")
            print(f"Calculator URL: {url}")
            return frame

    # Fallback: inspect frame HTML.
    print("URL match not found. Inspecting frame HTML...")

    for index, frame in enumerate(frames):
        html = await frame_content(frame)

        if not html:
            continue

        if (
            "Kalkulator cijena" in html
            and (
                "ASPxTabControl1" in html
                or "ddlUnObPiTez" in html
                or "Međunarodni promet" in html
            )
        ):
            print(f"FOUND calculator by HTML: frame {index}")
            print(f"Calculator URL: {frame.url}")
            return frame

    return None


async def save_calculator_diagnostics(frame):
    html = await frame_content(frame)
    save_text(IFRAME_FILE, html)

    try:
        text = await frame.locator("body").inner_text(timeout=NORMAL_TIMEOUT)
    except Exception:
        text = ""

    save_text(IFRAME_TEXT_FILE, text)

    return html, text


async def activate_international(frame):
    """
    Click the DevExpress tab containing 'Međunarodni promet'.

    The important detail is that the visible text is inside a SPAN:

        <span class="dx-vam">Međunarodni promet</span>

    Clicking that span or its closest clickable ancestor is more reliable
    than trying to identify a nonexistent ASP.NET control ID.
    """

    section("ACTIVATING MEĐUNARODNI PROMET")

    candidates = frame.get_by_text(
        "Međunarodni promet",
        exact=True,
    )

    count = await candidates.count()
    print(f"Text candidate count: {count}")

    if count == 0:
        # Search by substring as a fallback.
        candidates = frame.get_by_text("Međunarodni promet")
        count = await candidates.count()
        print(f"Substring candidate count: {count}")

    if count == 0:
        return False

    for i in range(count):
        candidate = candidates.nth(i)

        try:
            visible = await candidate.is_visible()
        except Exception:
            visible = False

        if not visible:
            continue

        try:
            print("Found visible Međunarodni promet element.")

            tag = await candidate.evaluate(
                "(el) => el.tagName"
            )
            outer = await candidate.evaluate(
                "(el) => el.outerHTML"
            )

            print(f"Tag: {tag}")
            print(f"HTML: {outer[:1000]}")

            # First attempt: normal click.
            try:
                await candidate.click(
                    timeout=NORMAL_TIMEOUT,
                    force=True,
                )
            except Exception as exc:
                print(f"Normal click failed: {exc}")

                # Try the closest clickable parent.
                try:
                    parent = candidate.locator(
                        "xpath=ancestor::*[self::td or self::a or "
                        "self::div or self::span][1]"
                    )

                    if await parent.count():
                        await parent.first.click(
                            timeout=NORMAL_TIMEOUT,
                            force=True,
                        )
                except Exception as exc2:
                    print(f"Parent click failed: {exc2}")

            # Give ASP.NET/DevExpress a short amount of time to update.
            await frame.page.wait_for_timeout(1000)

            return True

        except Exception as exc:
            print(f"Could not click candidate {i}: {exc}")

    return False


async def find_country_select(frame):
    """
    The international calculator's country selector is generated after
    switching tabs.

    Do NOT assume its ID is ddlMeDoOdrediste.

    We first look for any real <select>, then identify the one containing
    country names.
    """

    section("LOCATING COUNTRY DROPDOWN")

    selects = frame.locator("select")
    count = await selects.count()

    print(f"Number of select elements: {count}")

    country_markers = [
        "Afganistan",
        "Albanija",
        "Australija",
        "Austrija",
        "Belgija",
        "Bosna i Hercegovina",
        "Hrvatska",
        "Njemačka",
        "Njemacka",
        "Sjedinjene Americke Države",
        "Sjedinjene Američke Države",
        "United States",
        "Velika Britanija",
    ]

    for i in range(count):
        select = selects.nth(i)

        try:
            sid = await select.get_attribute("id")
            name = await select.get_attribute("name")
            html = await select.evaluate("(el) => el.outerHTML")
            text = await select.inner_text()

            print()
            print(f"SELECT #{i}")
            print(f"  id   = {sid}")
            print(f"  name = {name}")
            print(f"  text = {text[:1000]}")

            score = sum(
                1
                for marker in country_markers
                if marker.lower() in text.lower()
            )

            if score >= 2:
                print(f"COUNTRY SELECT FOUND: #{i}")
                return select

            # A large option list is also a strong signal.
            option_count = await select.locator("option").count()

            if option_count > 20:
                print(
                    f"COUNTRY SELECT FOUND by option count: #{i} "
                    f"({option_count} options)"
                )
                return select

        except Exception as exc:
            print(f"Error inspecting select #{i}: {exc}")

    return None


async def wait_for_country_select(frame, timeout_ms=10_000):
    """
    Wait at most 10 seconds for the dynamic ASP.NET/DevExpress update.
    """

    deadline = asyncio.get_running_loop().time() + (
        timeout_ms / 1000
    )

    while asyncio.get_running_loop().time() < deadline:
        select = await find_country_select(frame)

        if select is not None:
            return select

        await frame.page.wait_for_timeout(500)

    return None


def clean_country_name(value):
    value = re.sub(r"\s+", " ", value or "").strip()
    return value


async def extract_countries(select):
    section("EXTRACTING COUNTRIES")

    options = select.locator("option")
    count = await options.count()

    print(f"Country option count: {count}")

    countries = []

    for i in range(count):
        option = options.nth(i)

        try:
            text = clean_country_name(await option.inner_text())
            value = await option.get_attribute("value")

            if not text:
                continue

            # Ignore placeholder/non-country options.
            lowered = text.lower()

            if lowered in {
                "odredišna zemlja",
                "odredisna zemlja",
                "izaberite",
                "odaberite",
                "select",
                "select country",
            }:
                continue

            countries.append(text)

            print(
                f"[{len(countries):03d}] "
                f"{text} "
                f"(value={value})"
            )

        except Exception as exc:
            print(f"Could not read option {i}: {exc}")

    # Remove duplicates while preserving order.
    unique = []
    seen = set()

    for country in countries:
        key = country.casefold()

        if key not in seen:
            seen.add(key)
            unique.append(country)

    return unique


def save_countries(countries):
    section("SAVING COUNTRIES")

    text = "\n".join(countries) + ("\n" if countries else "")
    save_text(COUNTRIES_FILE, text)

    print(f"Saved {len(countries)} countries to {COUNTRIES_FILE}")


async def build_diagnostic(page, frame=None, extra=""):
    section("CREATING DIAGNOSTICS")

    page_html = await safe_content(page)
    save_text(DIAGNOSTIC_HTML_FILE, page_html)

    diagnostic_parts = []

    diagnostic_parts.append(
        "JP BH POŠTA CALCULATOR DIAGNOSTIC\n"
    )
    diagnostic_parts.append(
        f"URL: {URL}\n"
    )
    diagnostic_parts.append(
        f"Page URL: {page.url}\n"
    )

    diagnostic_parts.append(
        f"Number of frames: {len(page.frames)}\n"
    )

    for i, f in enumerate(page.frames):
        diagnostic_parts.append(
            f"FRAME {i}: {f.url}\n"
        )

    if frame is not None:
        html = await frame_content(frame)

        diagnostic_parts.append(
            "\nCALCULATOR FRAME HTML LENGTH: "
            f"{len(html)}\n"
        )

        try:
            body_text = await frame.locator("body").inner_text(
                timeout=3000
            )
        except Exception:
            body_text = ""

        diagnostic_parts.append(
            "\nCALCULATOR FRAME TEXT:\n"
            f"{body_text[:20000]}\n"
        )

        try:
            selects = await frame.locator("select").count()
        except Exception:
            selects = 0

        diagnostic_parts.append(
            f"\nSELECT COUNT: {selects}\n"
        )

        try:
            inputs = await frame.locator("input").count()
        except Exception:
            inputs = 0

        diagnostic_parts.append(
            f"INPUT COUNT: {inputs}\n"
        )

    if extra:
        diagnostic_parts.append(
            "\nADDITIONAL ERROR:\n"
            f"{extra}\n"
        )

    save_text(
        DIAGNOSTIC_FILE,
        "\n".join(diagnostic_parts),
    )

    await safe_screenshot(page)


async def main():
    section("JP BH POŠTA CALCULATOR MONITOR")
    print(f"URL: {URL}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-dev-shm-usage",
                "--no-sandbox",
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

        # Never allow an accidental locator to hang indefinitely.
        page.set_default_timeout(NORMAL_TIMEOUT)
        page.set_default_navigation_timeout(NAVIGATION_TIMEOUT)

        calculator_frame = None

        try:
            section("OPENING MAIN PAGE")

            response = None

            try:
                response = await page.goto(
                    URL,
                    wait_until="domcontentloaded",
                    timeout=NAVIGATION_TIMEOUT,
                )

            except PlaywrightTimeoutError as exc:
                print(
                    "WARNING: page.goto() timed out while waiting for "
                    "domcontentloaded."
                )
                print(
                    "Checking whether the page nevertheless loaded..."
                )
                print(str(exc))

            if response is not None:
                try:
                    print(
                        f"HTTP status: {response.status}"
                    )
                except Exception:
                    pass

            print(f"Final URL: {page.url}")

            try:
                print(f"Page title: {await page.title()}")
            except Exception:
                pass

            page_html = await safe_content(page)

            save_text(PAGE_FILE, page_html)

            # If navigation timed out, don't immediately fail. The iframe
            # can already have been created.
            await page.wait_for_timeout(1000)

            calculator_frame = await find_calculator_frame(page)

            # Sometimes the iframe appears shortly after DOMContentLoaded.
            if calculator_frame is None:
                print(
                    "Calculator frame not found immediately. "
                    "Waiting briefly for iframe creation..."
                )

                try:
                    await page.wait_for_selector(
                        "iframe",
                        timeout=5000,
                    )
                except Exception:
                    pass

                calculator_frame = await find_calculator_frame(page)

            if calculator_frame is None:
                raise RuntimeError(
                    "Could not locate the BH Pošta calculator iframe."
                )

            section("SAVING CALCULATOR IFRAME")

            await save_calculator_diagnostics(
                calculator_frame
            )

            section("CHECKING INITIAL CALCULATOR")

            # The internal calculator may initially be on "Unutrašnji
            # promet". We therefore deliberately look for the actual
            # country selector rather than assuming it is present.
            country_select = await find_country_select(
                calculator_frame
            )

            if country_select is None:
                print(
                    "Country dropdown is not present yet. "
                    "Attempting to activate Međunarodni promet."
                )

                activated = await activate_international(
                    calculator_frame
                )

                if not activated:
                    raise RuntimeError(
                        "Could not find or activate "
                        "Međunarodni promet."
                    )

                section("WAITING FOR INTERNATIONAL CALCULATOR")

                country_select = await wait_for_country_select(
                    calculator_frame,
                    timeout_ms=10_000,
                )

            if country_select is None:
                # Save the state after activation. This is particularly
                # useful because the previous runs proved that the
                # countries are visible even when the old ID assumption
                # was wrong.
                html, text = await save_calculator_diagnostics(
                    calculator_frame
                )

                visible_text = text[:30000]

                print()
                print("Visible calculator text:")
                print(visible_text)

                raise RuntimeError(
                    "International calculator activated, but no country "
                    "<select> element could be identified."
                )

            section("COUNTRY DROPDOWN FOUND")

            select_id = await country_select.get_attribute("id")
            select_name = await country_select.get_attribute("name")

            print(f"Country select id: {select_id}")
            print(f"Country select name: {select_name}")

            countries = await extract_countries(
                country_select
            )

            if not countries:
                raise RuntimeError(
                    "Country dropdown was found, but it contained "
                    "no country options."
                )

            # A genuine international destination list should be much
            # larger than a handful of entries.
            if len(countries) < 20:
                print(
                    f"WARNING: only {len(countries)} country options "
                    "were extracted."
                )

            save_countries(countries)

            section("SUCCESS")

            print(
                f"Successfully extracted {len(countries)} "
                "destination countries."
            )

            print()
            print("First countries:")

            for country in countries[:15]:
                print(f"  - {country}")

            print()
            print(f"Output file: {COUNTRIES_FILE}")

        except Exception as exc:
            section("MONITOR FAILED")

            print(
                f"{type(exc).__name__}: {exc}"
            )

            await build_diagnostic(
                page,
                calculator_frame,
                extra=(
                    f"{type(exc).__name__}: {exc}"
                ),
            )

            # Ensure the exception produces a failed GitHub Actions step.
            raise

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
        print("Interrupted.")
        sys.exit(130)
