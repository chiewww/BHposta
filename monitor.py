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

CALCULATOR_IFRAME_URL_PART = (
    "bhpwebout.posta.ba/KalkulatorCijena_WEB_app"
)

COUNTRIES_FILE = Path("countries.txt")
RESULTS_FILE = Path("calculator-results.txt")
PAGE_FILE = Path("page.html")
IFRAME_FILE = Path("iframe.html")
IFRAME_TEXT_FILE = Path("iframe.txt")
DIAGNOSTIC_FILE = Path("diagnostic.txt")
DIAGNOSTIC_HTML_FILE = Path("diagnostic.html")
DIAGNOSTIC_PNG_FILE = Path("diagnostic.png")

NAVIGATION_TIMEOUT = 30_000
DEFAULT_TIMEOUT = 5_000
TOTAL_TIMEOUT = 60_000


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


async def safe_screenshot(page):
    try:
        await page.screenshot(
            path=str(DIAGNOSTIC_PNG_FILE),
            full_page=True,
        )
        print(f"Saved {DIAGNOSTIC_PNG_FILE}")
    except Exception as exc:
        print(f"Could not save screenshot: {exc}")


async def frame_content(frame):
    try:
        return await frame.content()
    except Exception:
        return ""


async def find_calculator_frame(page):
    section("LOCATING CALCULATOR IFRAME")

    frames = page.frames
    print(f"Number of frames: {len(frames)}")

    for index, frame in enumerate(frames):
        url = frame.url or ""
        print(f"Checking frame {index}: {url}")

        if CALCULATOR_IFRAME_URL_PART.lower() in url.lower():
            print(f"FOUND CALCULATOR FRAME: {index}")
            print(f"Calculator URL: {url}")
            return frame

    print("URL match not found. Inspecting frame HTML...")

    for index, frame in enumerate(frames):
        html = await frame_content(frame)

        if not html:
            continue

        markers = (
            "ddlUnObPiTez",
            "ddlMeObPiOderdiste",
            "Međunarodni promet",
            "Kalkulator cijena",
        )

        if any(marker in html for marker in markers):
            print(f"FOUND calculator by HTML: frame {index}")
            print(f"Calculator URL: {frame.url}")
            return frame

    return None


async def save_calculator_diagnostics(frame):
    html = await frame_content(frame)
    save_text(IFRAME_FILE, html)

    try:
        text = await frame.locator("body").inner_text(
            timeout=DEFAULT_TIMEOUT
        )
    except Exception:
        text = ""

    save_text(IFRAME_TEXT_FILE, text)

    return html, text


async def activate_international(frame):
    section("ACTIVATING MEĐUNARODNI PROMET")

    selectors = [
        "text=Međunarodni promet",
        "span.dx-vam",
    ]

    for selector in selectors:
        try:
            locator = frame.locator(selector)
            count = await locator.count()
            print(f"Selector {selector!r}: {count} matches")

            for i in range(count):
                candidate = locator.nth(i)

                try:
                    if not await candidate.is_visible():
                        continue
                except Exception:
                    continue

                try:
                    text = (await candidate.inner_text()).strip()
                except Exception:
                    text = ""

                if (
                    "Međunarodni promet" not in text
                    and selector != "text=Međunarodni promet"
                ):
                    continue

                print("Found visible Međunarodni promet element.")

                try:
                    print(
                        "Tag:",
                        await candidate.evaluate(
                            "(el) => el.tagName"
                        ),
                    )
                    print(
                        "HTML:",
                        (
                            await candidate.evaluate(
                                "(el) => el.outerHTML"
                            )
                        )[:1000],
                    )
                except Exception:
                    pass

                try:
                    await candidate.click(
                        timeout=DEFAULT_TIMEOUT,
                        force=True,
                    )
                    print("Clicked Međunarodni promet.")
                    await frame.page.wait_for_timeout(1000)
                    return True
                except Exception as exc:
                    print(f"Direct click failed: {exc}")

                # Try clickable ancestors.
                for xpath in [
                    "xpath=ancestor::td[1]",
                    "xpath=ancestor::a[1]",
                    "xpath=ancestor::div[1]",
                ]:
                    try:
                        parent = candidate.locator(xpath)

                        if await parent.count():
                            await parent.first.click(
                                timeout=DEFAULT_TIMEOUT,
                                force=True,
                            )
                            print(
                                f"Clicked ancestor using {xpath}."
                            )
                            await frame.page.wait_for_timeout(1000)
                            return True
                    except Exception:
                        pass

        except Exception as exc:
            print(
                f"Error with selector {selector!r}: {exc}"
            )

    return False


async def inspect_selects(frame):
    selects = frame.locator("select")
    count = await selects.count()

    print(f"Number of select elements: {count}")

    for i in range(count):
        select = selects.nth(i)

        try:
            sid = await select.get_attribute("id")
            name = await select.get_attribute("name")
            options = select.locator("option")
            option_count = await options.count()
            text = await select.inner_text()

            print()
            print(f"SELECT #{i}")
            print(f"  id      = {sid}")
            print(f"  name    = {name}")
            print(f"  options = {option_count}")
            print(f"  text    = {text[:1000]}")

        except Exception as exc:
            print(f"Error inspecting select #{i}: {exc}")


async def find_country_select(frame):
    section("LOCATING COUNTRY DROPDOWN")

    selects = frame.locator("select")
    count = await selects.count()

    print(f"Number of select elements: {count}")

    markers = [
        "Afganistan",
        "Albanija",
        "Alžir",
        "Australija",
        "Austrija",
        "Belgija",
        "Bosna i Hercegovina",
        "Hrvatska",
        "Njemacka",
        "Njemačka",
        "SAD",
        "Sjedinjene",
        "Velika Britanija",
    ]

    best = None
    best_score = 0

    for i in range(count):
        select = selects.nth(i)

        try:
            sid = await select.get_attribute("id")
            name = await select.get_attribute("name")
            text = await select.inner_text()
            option_count = await select.locator("option").count()

            print()
            print(f"SELECT #{i}")
            print(f"  id   = {sid}")
            print(f"  name = {name}")
            print(f"  options = {option_count}")
            print(f"  text = {text[:1000]}")

            lower = text.casefold()

            score = sum(
                1
                for marker in markers
                if marker.casefold() in lower
            )

            if option_count >= 20:
                score += 10

            if score > best_score:
                best = select
                best_score = score

        except Exception as exc:
            print(
                f"Error inspecting select #{i}: {exc}"
            )

    if best is not None and best_score >= 10:
        try:
            sid = await best.get_attribute("id")
            print(f"COUNTRY SELECT FOUND: {sid}")
        except Exception:
            print("COUNTRY SELECT FOUND")

        return best

    return None


async def wait_for_country_select(frame, timeout_ms=15_000):
    deadline = (
        asyncio.get_running_loop().time()
        + timeout_ms / 1000
    )

    while asyncio.get_running_loop().time() < deadline:
        select = await find_country_select(frame)

        if select is not None:
            return select

        await frame.page.wait_for_timeout(500)

    return None


def clean_name(value):
    return re.sub(r"\s+", " ", value or "").strip()


async def extract_country_options(select):
    section("EXTRACTING DESTINATIONS")

    options = select.locator("option")
    count = await options.count()

    print(f"Total option elements: {count}")

    rows = []

    for i in range(count):
        option = options.nth(i)

        try:
            text = clean_name(await option.inner_text())
            value = await option.get_attribute("value")
            disabled = await option.is_disabled()

            if not text:
                continue

            rows.append(
                {
                    "text": text,
                    "value": value or "",
                    "disabled": disabled,
                }
            )

        except Exception as exc:
            print(
                f"Could not read option {i}: {exc}"
            )

    return rows


def save_country_files(rows):
    section("SAVING DESTINATIONS")

    available = []
    unavailable = []

    placeholders = {
        "odredišna zemlja",
        "odredisna zemlja",
        "izaberite",
        "odaberite",
        "select",
        "select country",
    }

    seen = set()

    for row in rows:
        name = row["text"]
        key = name.casefold()

        if key in placeholders:
            continue

        if key in seen:
            continue

        seen.add(key)

        if row["disabled"]:
            unavailable.append(row)
        else:
            available.append(row)

    lines = []

    lines.append(
        "JP BH POŠTA DESTINATION AVAILABILITY"
    )
    lines.append("=" * 60)
    lines.append("")
    lines.append(
        f"TOTAL SELECT OPTIONS: {len(rows)}"
    )
    lines.append(
        f"AVAILABLE DESTINATIONS: {len(available)}"
    )
    lines.append(
        f"UNAVAILABLE DESTINATIONS: {len(unavailable)}"
    )
    lines.append("")

    lines.append("AVAILABLE DESTINATIONS")
    lines.append("-" * 60)

    for index, row in enumerate(available, 1):
        lines.append(
            f"{index:03d}. {row['text']} "
            f"[value={row['value']}]"
        )

    lines.append("")
    lines.append("UNAVAILABLE DESTINATIONS")
    lines.append("-" * 60)

    if unavailable:
        for index, row in enumerate(unavailable, 1):
            lines.append(
                f"{index:03d}. {row['text']} "
                f"[value={row['value']}]"
            )
    else:
        lines.append(
            "None identified as disabled in the HTML."
        )

    save_text(
        RESULTS_FILE,
        "\n".join(lines) + "\n",
    )

    # countries.txt is deliberately only the available list.
    countries_text = "\n".join(
        row["text"] for row in available
    )

    if countries_text:
        countries_text += "\n"

    save_text(
        COUNTRIES_FILE,
        countries_text,
    )

    print(
        f"Available destinations: {len(available)}"
    )
    print(
        f"Unavailable destinations: {len(unavailable)}"
    )


async def build_diagnostic(page, frame, error):
    section("CREATING DIAGNOSTICS")

    page_html = await safe_content(page)
    save_text(
        DIAGNOSTIC_HTML_FILE,
        page_html,
    )

    parts = [
        "JP BH POŠTA CALCULATOR DIAGNOSTIC",
        "",
        f"URL: {URL}",
        f"PAGE URL: {page.url}",
        f"FRAME COUNT: {len(page.frames)}",
        "",
    ]

    for i, f in enumerate(page.frames):
        parts.append(
            f"FRAME {i}: {f.url}"
        )

    if frame is not None:
        html = await frame_content(frame)

        parts.extend(
            [
                "",
                f"CALCULATOR HTML LENGTH: {len(html)}",
                "",
                "CALCULATOR HTML:",
                html[:50000],
            ]
        )

        try:
            body = await frame.locator(
                "body"
            ).inner_text(timeout=3000)
        except Exception:
            body = ""

        parts.extend(
            [
                "",
                "CALCULATOR TEXT:",
                body[:30000],
            ]
        )

        try:
            select_count = await frame.locator(
                "select"
            ).count()
        except Exception:
            select_count = 0

        parts.append(
            f"SELECT COUNT: {select_count}"
        )

        await inspect_selects(frame)

    parts.extend(
        [
            "",
            "ERROR:",
            f"{type(error).__name__}: {error}",
        ]
    )

    save_text(
        DIAGNOSTIC_FILE,
        "\n".join(parts),
    )

    await safe_screenshot(page)


async def main():
    section("JP BH POŠTA CALCULATOR MONITOR")
    print(f"URL: {URL}")

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
                    "WARNING: main page navigation timed out."
                )
                print(
                    "The page may still have loaded."
                )
                print(str(exc))

            if response is not None:
                print(
                    f"HTTP status: {response.status}"
                )

            print(f"Final URL: {page.url}")

            try:
                print(
                    f"Page title: {await page.title()}"
                )
            except Exception:
                pass

            save_text(
                PAGE_FILE,
                await safe_content(page),
            )

            # Give iframe creation a little time, but never wait
            # indefinitely.
            await page.wait_for_timeout(1500)

            frame = await find_calculator_frame(page)

            if frame is None:
                section("WAITING FOR CALCULATOR IFRAME")

                try:
                    await page.wait_for_selector(
                        "iframe",
                        timeout=5000,
                    )
                except Exception:
                    pass

                frame = await find_calculator_frame(page)

            if frame is None:
                raise RuntimeError(
                    "Could not locate the BH Pošta calculator iframe."
                )

            section("SAVING CALCULATOR IFRAME")

            await save_calculator_diagnostics(
                frame
            )

            section("CHECKING INITIAL CALCULATOR")

            country_select = (
                await find_country_select(frame)
            )

            if country_select is None:
                print(
                    "Country dropdown not present. "
                    "Activating Međunarodni promet."
                )

                activated = (
                    await activate_international(frame)
                )

                if not activated:
                    raise RuntimeError(
                        "Could not find or activate "
                        "Međunarodni promet."
                    )

                section(
                    "WAITING FOR INTERNATIONAL CALCULATOR"
                )

                country_select = (
                    await wait_for_country_select(
                        frame,
                        timeout_ms=15_000,
                    )
                )

            if country_select is None:
                await save_calculator_diagnostics(
                    frame
                )

                raise RuntimeError(
                    "International calculator activated, "
                    "but no country select was found."
                )

            section("COUNTRY DROPDOWN FOUND")

            print(
                "Country select id:",
                await country_select.get_attribute(
                    "id"
                ),
            )
            print(
                "Country select name:",
                await country_select.get_attribute(
                    "name"
                ),
            )

            rows = await extract_country_options(
                country_select
            )

            if len(rows) < 20:
                raise RuntimeError(
                    "Suspiciously small destination list: "
                    f"{len(rows)} options."
                )

            save_country_files(rows)

            section("SUCCESS")

            print(
                "Destination extraction completed."
            )
            print(
                f"Total options: {len(rows)}"
            )
            print(
                f"Results file: {RESULTS_FILE}"
            )
            print(
                f"Countries file: {COUNTRIES_FILE}"
            )

        except Exception as exc:
            section("MONITOR FAILED")
            print(
                f"{type(exc).__name__}: {exc}"
            )

            try:
                await build_diagnostic(
                    page,
                    frame,
                    exc,
                )
            except Exception as diagnostic_error:
                print(
                    "Diagnostic creation also failed:",
                    diagnostic_error,
                )

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
