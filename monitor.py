import asyncio
import os
import re
from pathlib import Path
from typing import Optional

from playwright.async_api import (
    async_playwright,
    TimeoutError as PlaywrightTimeoutError,
)


# ============================================================
# CONFIGURATION
# ============================================================

URL = os.environ.get(
    "CALCULATOR_URL",
    "https://www.posta.ba/kalkulator-cijena/",
)

COUNTRIES_FILE = Path("countries.txt")

PAGE_HTML = Path("page.html")
IFRAME_HTML = Path("iframe.html")
IFRAME_TEXT = Path("iframe.txt")
DIAGNOSTIC_HTML = Path("diagnostic.html")
DIAGNOSTIC_TXT = Path("diagnostic.txt")
DIAGNOSTIC_PNG = Path("diagnostic.png")
DEBUG_TXT = Path("debug.txt")

# Keep all waits deliberately short.
DEFAULT_TIMEOUT = 5_000
SHORT_WAIT = 500
ACTIVATION_WAIT = 2_000


# ============================================================
# OUTPUT HELPERS
# ============================================================

def section(title: str) -> None:
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def clean_text(value: str) -> str:
    value = value.replace("\xa0", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


# ============================================================
# COUNTRY FILTERING
# ============================================================

# These are obviously not countries and should never become
# entries in countries.txt.
NON_COUNTRY_TEXT = {
    "",
    "odredišna zemlja",
    "odrediste",
    "odredište",
    "kalkulator cijena",
    "unutrašnji promet",
    "međunarodni promet",
    "preporučeno",
    "hitno",
    "sa povratnicom",
    "avionski prijenos",
    "vrijednosna pošiljka",
    "izračunaj",
    "napomena",
    "bos",
    "eng",
}


def looks_like_country(text: str) -> bool:
    """
    Conservative filter.

    The BH Pošta calculator contains a mixture of:
      - countries
      - UI labels
      - weight bands
      - service names

    We primarily rely on DOM structure and then use this filter
    to remove obvious non-country values.
    """
    text = clean_text(text)

    if not text:
        return False

    lowered = text.casefold()

    if lowered in NON_COUNTRY_TEXT:
        return False

    # Weight/service/UI entries are not countries.
    blocked_fragments = [
        "stopa:",
        "preko ",
        "do ",
        "promet",
        "izračun",
        "pošilj",
        "povratnic",
        "prijenos",
        "napomena",
        "kalkulator",
    ]

    if any(fragment in lowered for fragment in blocked_fragments):
        return False

    # A country option should normally be relatively short.
    if len(text) > 100:
        return False

    return True


def unique_preserve_order(items):
    result = []
    seen = set()

    for item in items:
        item = clean_text(item)

        if not item:
            continue

        key = item.casefold()

        if key in seen:
            continue

        seen.add(key)
        result.append(item)

    return result


# ============================================================
# FRAME DISCOVERY
# ============================================================

async def find_calculator_frame(page):
    """
    Find the BH Pošta calculator iframe.

    We deliberately identify the frame by URL rather than assuming
    it is frame #1, because the outer page can change.
    """
    section("LOCATING CALCULATOR IFRAME")

    frames = page.frames

    print(f"Number of frames: {len(frames)}")

    # Strongest match: the bhpwebout calculator host.
    for index, frame in enumerate(frames):
        print(f"Checking frame {index}: {frame.url}")

        if "bhpwebout.posta.ba" in frame.url.lower():
            print(f"FOUND CALCULATOR FRAME: {index}")
            print(f"Calculator URL: {frame.url}")
            return frame

    # Fallback: look for a frame containing calculator-specific text.
    for index, frame in enumerate(frames):
        try:
            html = await frame.content()
        except Exception:
            continue

        if (
            "Kalkulator cijena" in html
            and "Međunarodni promet" in html
        ):
            print(f"FOUND CALCULATOR FRAME BY CONTENT: {index}")
            print(f"Calculator URL: {frame.url}")
            return frame

    return None


# ============================================================
# FRAME DIAGNOSTICS
# ============================================================

async def save_frame_diagnostics(frame) -> None:
    section("SAVING CALCULATOR IFRAME")

    try:
        html = await frame.content()
        write_text(IFRAME_HTML, html)
        print(f"Saved iframe.html ({len(html):,} bytes)")
    except Exception as exc:
        print(f"Could not save iframe.html: {exc}")
        html = ""

    try:
        text = await frame.locator("body").inner_text(timeout=DEFAULT_TIMEOUT)
        text = clean_text(text)
        write_text(IFRAME_TEXT, text)
        print(f"Saved iframe.txt ({len(text):,} bytes)")
    except Exception as exc:
        print(f"Could not save iframe.txt: {exc}")


async def save_page_diagnostics(page) -> None:
    try:
        html = await page.content()
        write_text(PAGE_HTML, html)
        print(f"Saved page.html ({len(html):,} bytes)")
    except Exception as exc:
        print(f"Could not save page.html: {exc}")

    try:
        await page.screenshot(
            path=str(DIAGNOSTIC_PNG),
            full_page=True,
        )
        print(f"Saved {DIAGNOSTIC_PNG}")
    except Exception as exc:
        print(f"Could not save screenshot: {exc}")


async def save_frame_screenshot(page, frame) -> None:
    """
    A Frame object does not have screenshot().
    Screenshot the actual iframe element on the PAGE instead.
    """
    try:
        iframe_locator = page.locator("iframe").filter(
            has=page.locator("body")
        )

        # The filter above is not guaranteed to work across browsers,
        # so use the iframe whose src contains bhpwebout instead.
        iframe_locator = page.locator(
            'iframe[src*="bhpwebout.posta.ba"]'
        )

        if await iframe_locator.count():
            await iframe_locator.first.screenshot(
                path=str(DIAGNOSTIC_PNG)
            )
            print(f"Saved iframe screenshot: {DIAGNOSTIC_PNG}")
            return

    except Exception as exc:
        print(f"Could not save iframe screenshot: {exc}")

    # Safe fallback: screenshot the whole page.
    try:
        await page.screenshot(
            path=str(DIAGNOSTIC_PNG),
            full_page=True,
        )
        print(f"Saved page screenshot: {DIAGNOSTIC_PNG}")
    except Exception as exc:
        print(f"Could not save fallback screenshot: {exc}")


# ============================================================
# TAB ACTIVATION
# ============================================================

async def activate_international_tab(frame) -> bool:
    """
    Activate 'Međunarodni promet'.

    The diagnostics showed that the visible text is:

        <span class="dx-vam">Međunarodni promet</span>

    Therefore we do not depend on a specific ASPx control ID.
    """

    section("ACTIVATING MEĐUNARODNI PROMET")

    candidates = frame.get_by_text(
        "Međunarodni promet",
        exact=True,
    )

    count = await candidates.count()
    print(f"Text candidate count: {count}")

    if count == 0:
        # Secondary locator: text containing the phrase.
        candidates = frame.locator(
            "text=Međunarodni promet"
        )
        count = await candidates.count()
        print(f"Fallback candidate count: {count}")

    if count == 0:
        print("Could not find Međunarodni promet.")
        return False

    # Try every candidate until one actually causes the international
    # form to appear.
    for i in range(count):
        candidate = candidates.nth(i)

        try:
            if not await candidate.is_visible():
                continue
        except Exception:
            continue

        try:
            print("Found visible Međunarodni promet element.")

            try:
                tag = await candidate.evaluate(
                    "(el) => el.tagName"
                )
                print(f"Tag: {tag}")
            except Exception:
                pass

            try:
                html = await candidate.evaluate(
                    "(el) => el.outerHTML"
                )
                print(f"HTML: {html[:1000]}")
            except Exception:
                pass

            await candidate.scroll_into_view_if_needed(
                timeout=DEFAULT_TIMEOUT
            )

            await candidate.click(
                timeout=DEFAULT_TIMEOUT,
                force=True,
            )

            print("Clicked Međunarodni promet.")

            # Give the ASP.NET/DevExpress UI a short amount of time
            # to update. We intentionally do NOT use a long networkidle
            # wait because these pages can keep background connections
            # alive.
            await page_wait(frame, ACTIVATION_WAIT)

            return True

        except PlaywrightTimeoutError as exc:
            print(f"Candidate {i} timed out: {exc}")
        except Exception as exc:
            print(f"Candidate {i} failed: {exc}")

    return False


async def page_wait(frame, milliseconds: int) -> None:
    """
    Short non-blocking-ish wait using the frame's page context.
    """
    try:
        await frame.wait_for_timeout(milliseconds)
    except Exception:
        await asyncio.sleep(milliseconds / 1000)


# ============================================================
# CONTROL DISCOVERY
# ============================================================

async def inspect_selects(frame):
    """
    Return metadata for every native <select> in the calculator.
    """
    result = []

    selects = frame.locator("select")
    count = await selects.count()

    print(f"Number of <select> elements: {count}")

    for i in range(count):
        select = selects.nth(i)

        try:
            info = await select.evaluate(
                """
                (el) => ({
                    id: el.id || "",
                    name: el.name || "",
                    className: el.className || "",
                    disabled: !!el.disabled,
                    multiple: !!el.multiple,
                    options: Array.from(el.options).map(o => ({
                        value: o.value || "",
                        text: (o.textContent || "").trim(),
                        selected: !!o.selected
                    }))
                })
                """
            )

            result.append(info)

            print()
            print(f"SELECT #{i}")
            print(f"  id      = {info['id']}")
            print(f"  name    = {info['name']}")
            print(f"  class   = {info['className']}")
            print(f"  options = {len(info['options'])}")

            for j, option in enumerate(info["options"][:20]):
                print(
                    f"    [{j}] value={option['value']!r} "
                    f"text={option['text']!r}"
                )

            if len(info["options"]) > 20:
                print(
                    f"    ... {len(info['options']) - 20} more"
                )

        except Exception as exc:
            print(f"Could not inspect select #{i}: {exc}")

    return result


def select_looks_like_country_list(info) -> bool:
    options = info.get("options", [])

    if len(options) < 20:
        return False

    texts = [
        clean_text(o.get("text", ""))
        for o in options
    ]

    joined = " | ".join(texts).casefold()

    # Strong signals from the actual BH Pošta calculator.
    strong_names = [
        "afganistan",
        "albanija",
        "alžir",
        "argentina",
        "australija",
        "austrija",
        "belgija",
        "bosna i hercegovina",
        "hrvatska",
        "njemačka",
        "japan",
        "kanada",
        "kina",
        "kosovo",
        "mađarska",
        "njemačka",
        "poljska",
        "portugal",
        "srbija",
        "švicarska",
        "turska",
        "ukrajina",
        "velika britanija",
    ]

    matches = sum(
        1 for name in strong_names if name in joined
    )

    return matches >= 2


# ============================================================
# COUNTRY EXTRACTION
# ============================================================

async def extract_countries_from_select(
    frame,
) -> Optional[list[str]]:
    """
    Find the native select containing the country options.

    We do NOT use #ddlMeDoOdrediste because the diagnostics proved
    that this ID is not reliable.
    """

    section("DISCOVERING COUNTRY CONTROL")

    select_infos = await inspect_selects(frame)

    candidates = [
        info
        for info in select_infos
        if select_looks_like_country_list(info)
    ]

    if candidates:
        # If several candidates exist, use the one with the most
        # options.
        candidates.sort(
            key=lambda x: len(x.get("options", [])),
            reverse=True,
        )

        chosen = candidates[0]

        print()
        print("COUNTRY SELECT FOUND")
        print(f"ID: {chosen.get('id')}")
        print(f"Name: {chosen.get('name')}")
        print(
            f"Option count: "
            f"{len(chosen.get('options', []))}"
        )

        countries = []

        for option in chosen.get("options", []):
            text = clean_text(option.get("text", ""))

            if looks_like_country(text):
                countries.append(text)

        countries = unique_preserve_order(countries)

        if countries:
            return countries

    print()
    print("No native country <select> was found.")

    return None


# ============================================================
# FALLBACK DOM EXTRACTION
# ============================================================

async def extract_countries_from_options(frame) -> list[str]:
    """
    Fallback: inspect all <option> elements.

    This is useful if the country control exists but its ID/name
    differs from what we expect.
    """

    section("FALLBACK OPTION EXTRACTION")

    options = frame.locator("option")
    count = await options.count()

    print(f"Total <option> elements: {count}")

    values = []

    for i in range(count):
        try:
            text = await options.nth(i).inner_text()
            text = clean_text(text)

            if looks_like_country(text):
                values.append(text)

        except Exception:
            continue

    values = unique_preserve_order(values)

    print(f"Potential country options: {len(values)}")

    return values


async def extract_countries_from_dom_text(frame) -> list[str]:
    """
    Last-resort fallback.

    The diagnostics demonstrated that the entire country list is
    visible in the calculator after activating international traffic.

    We therefore inspect DOM elements containing known country
    names and attempt to identify their surrounding list structure.
    """

    section("DOM COUNTRY FALLBACK")

    try:
        html = await frame.content()
    except Exception as exc:
        print(f"Could not read frame HTML: {exc}")
        return []

    # Save the post-activation HTML separately.
    write_text(DIAGNOSTIC_HTML, html)
    print(
        f"Saved {DIAGNOSTIC_HTML} "
        f"({len(html):,} bytes)"
    )

    # First try all option tags using raw HTML as an additional
    # safety net.
    option_matches = re.findall(
        r"<option\b[^>]*>(.*?)</option>",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )

    values = []

    for raw in option_matches:
        # Strip HTML tags.
        text = re.sub(r"<[^>]+>", " ", raw)
        text = clean_text(text)

        if looks_like_country(text):
            values.append(text)

    values = unique_preserve_order(values)

    if values:
        print(
            f"Raw HTML extraction found "
            f"{len(values)} potential countries."
        )
        return values

    print("Raw HTML did not contain country <option> elements.")

    return []


# ============================================================
# COUNTRY FILE
# ============================================================

def save_countries(countries: list[str]) -> None:
    section("SAVING COUNTRIES")

    countries = unique_preserve_order(countries)

    if not countries:
        raise RuntimeError(
            "No countries were extracted."
        )

    # Sort alphabetically for stable Git diffs.
    countries_sorted = sorted(
        countries,
        key=lambda x: x.casefold(),
    )

    text = "\n".join(countries_sorted) + "\n"

    write_text(COUNTRIES_FILE, text)

    print(
        f"Saved {COUNTRIES_FILE} "
        f"({len(countries_sorted)} countries)"
    )

    print()
    print("First countries:")

    for country in countries_sorted[:20]:
        print(f"  {country}")

    if len(countries_sorted) > 20:
        print(
            f"  ... "
            f"{len(countries_sorted) - 20} more"
        )


# ============================================================
# DIAGNOSTIC REPORT
# ============================================================

async def write_diagnostic_report(
    page,
    frame,
    countries=None,
) -> None:
    lines = []

    lines.append(
        "JP BH POŠTA CALCULATOR MONITOR DIAGNOSTIC"
    )
    lines.append("")
    lines.append(f"URL: {URL}")
    lines.append(f"Final URL: {page.url}")
    lines.append(f"Calculator frame URL: {frame.url}")
    lines.append("")

    try:
        body_text = await frame.locator("body").inner_text(
            timeout=DEFAULT_TIMEOUT
        )
        body_text = clean_text(body_text)
    except Exception as exc:
        body_text = f"ERROR: {exc}"

    lines.append("CALCULATOR TEXT")
    lines.append("=" * 70)
    lines.append(body_text[:100000])
    lines.append("")

    try:
        selects = await inspect_selects(frame)
    except Exception as exc:
        selects = []
        lines.append(f"SELECT INSPECTION ERROR: {exc}")

    lines.append("")
    lines.append("SELECT SUMMARY")
    lines.append("=" * 70)

    for i, info in enumerate(selects):
        lines.append(
            f"SELECT #{i}: "
            f"id={info.get('id')!r}, "
            f"name={info.get('name')!r}, "
            f"options={len(info.get('options', []))}"
        )

    if countries is not None:
        lines.append("")
        lines.append(
            f"EXTRACTED COUNTRIES: {len(countries)}"
        )

    write_text(
        DIAGNOSTIC_TXT,
        "\n".join(lines),
    )

    print(
        f"Saved diagnostic.txt "
        f"({DIAGNOSTIC_TXT.stat().st_size:,} bytes)"
    )


# ============================================================
# MAIN
# ============================================================

async def main():
    section("JP BH POŠTA CALCULATOR MONITOR")

    print(f"URL: {URL}")

    if not URL:
        raise RuntimeError(
            "CALCULATOR_URL is empty"
        )

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-dev-shm-usage",
                "--no-sandbox",
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

        # Critical: keep Playwright from silently waiting 30 seconds
        # on every failed locator.
        page.set_default_timeout(DEFAULT_TIMEOUT)
        page.set_default_navigation_timeout(
            DEFAULT_TIMEOUT
        )

        try:
            # ----------------------------------------------------
            # OPEN MAIN PAGE
            # ----------------------------------------------------

            section("OPENING MAIN PAGE")

            response = await page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=DEFAULT_TIMEOUT,
            )

            if response:
                print(
                    f"HTTP status: "
                    f"{response.status}"
                )
            else:
                print("No navigation response.")

            print(f"Final URL: {page.url}")

            try:
                print(
                    f"Page title: "
                    f"{await page.title()}"
                )
            except Exception:
                pass

            await page.wait_for_timeout(
                SHORT_WAIT
            )

            await save_page_diagnostics(page)

            # ----------------------------------------------------
            # FIND CALCULATOR FRAME
            # ----------------------------------------------------

            frame = await find_calculator_frame(page)

            if frame is None:
                # Save all frame information.
                lines = [
                    f"URL: {page.url}",
                    "",
                    f"Number of frames: "
                    f"{len(page.frames)}",
                ]

                for i, fr in enumerate(page.frames):
                    lines.append(
                        f"FRAME {i}: {fr.url}"
                    )

                write_text(
                    DEBUG_TXT,
                    "\n".join(lines),
                )

                raise RuntimeError(
                    "Could not locate the BH Pošta "
                    "calculator iframe."
                )

            await save_frame_diagnostics(frame)

            # ----------------------------------------------------
            # INITIAL COUNTRY SEARCH
            # ----------------------------------------------------

            section("CHECKING INITIAL CALCULATOR")

            initial_selects = await inspect_selects(
                frame
            )

            countries = (
                await extract_countries_from_select(
                    frame
                )
            )

            # If the international calculator is already active,
            # we do not click the tab.
            if not countries:
                print(
                    "Country dropdown is not present yet."
                )
                print(
                    "Attempting to activate "
                    "Međunarodni promet."
                )

                activated = (
                    await activate_international_tab(
                        frame
                    )
                )

                if not activated:
                    await save_frame_diagnostics(
                        frame
                    )

                    await save_frame_screenshot(
                        page,
                        frame,
                    )

                    raise RuntimeError(
                        "Could not activate "
                        "Međunarodni promet."
                    )

                # ------------------------------------------------
                # WAIT FOR DYNAMIC CONTENT
                # ------------------------------------------------

                section(
                    "WAITING FOR INTERNATIONAL CALCULATOR"
                )

                # Do NOT use networkidle here.
                # ASP.NET/DevExpress pages can maintain
                # background requests.
                await page_wait(
                    frame,
                    ACTIVATION_WAIT,
                )

                await save_frame_diagnostics(
                    frame
                )

                # ------------------------------------------------
                # FIND COUNTRY CONTROL
                # ------------------------------------------------

                countries = (
                    await extract_countries_from_select(
                        frame
                    )
                )

            # ----------------------------------------------------
            # FALLBACKS
            # ----------------------------------------------------

            if not countries:
                countries = (
                    await extract_countries_from_options(
                        frame
                    )
                )

            if not countries:
                countries = (
                    await extract_countries_from_dom_text(
                        frame
                    )
                )

            # ----------------------------------------------------
            # VALIDATE
            # ----------------------------------------------------

            section("VALIDATING COUNTRY DATA")

            countries = unique_preserve_order(
                countries or []
            )

            print(
                f"Countries extracted: "
                f"{len(countries)}"
            )

            if len(countries) < 20:
                # Save maximum diagnostics before failing.
                try:
                    body = await frame.locator(
                        "body"
                    ).inner_text(
                        timeout=DEFAULT_TIMEOUT
                    )
                    write_text(
                        DEBUG_TXT,
                        body,
                    )
                except Exception:
                    pass

                await save_frame_diagnostics(
                    frame
                )

                await save_frame_screenshot(
                    page,
                    frame,
                )

                raise RuntimeError(
                    "The international calculator was "
                    "activated, but fewer than 20 "
                    "country entries could be extracted. "
                    "See iframe.html, iframe.txt, "
                    "diagnostic.txt and diagnostic.png."
                )

            # ----------------------------------------------------
            # SAVE RESULT
            # ----------------------------------------------------

            save_countries(countries)

            await write_diagnostic_report(
                page,
                frame,
                countries,
            )

            # ----------------------------------------------------
            # FINAL OUTPUT
            # ----------------------------------------------------

            section("MONITOR SUCCESS")

            print(
                f"Successfully extracted "
                f"{len(countries)} countries."
            )

            print(
                f"Output file: "
                f"{COUNTRIES_FILE}"
            )

        except Exception as exc:
            section("MONITOR FAILED")

            print(
                f"{type(exc).__name__}: {exc}"
            )

            # Always attempt to leave diagnostics behind.
            try:
                await save_page_diagnostics(page)
            except Exception:
                pass

            try:
                if "frame" in locals() and frame:
                    await save_frame_diagnostics(
                        frame
                    )

                    await save_frame_screenshot(
                        page,
                        frame,
                    )
            except Exception:
                pass

            raise

        finally:
            await context.close()
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
