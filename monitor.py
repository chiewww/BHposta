import re
import sys
import time
from pathlib import Path

from playwright.sync_api import (
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)


URL = (
    "https://bhpwebout.posta.ba/"
    "KalkulatorCijena_WEB_app/Bos/Default.aspx"
)

OUTPUT_FILE = Path("bh_posta_countries.txt")

DESTINATION_SELECT = "ddlMeDoOdrediste"

AIR_CHECKBOX = "chbMeDoAvionski"
AIR_WEIGHT = "tbxMeDoAvioTezina"

DOPISNICA_BUTTON = "ImageButton8"

SUSPENDED_MESSAGE = (
    "Prijem pošiljaka se trenutno ne vrši za odabranu državu"
)

WEIGHT = "10"

# Keep this reasonably small. The site can be slow, but waiting
# several seconds after every country makes 262 countries take
# a very long time.
COUNTRY_WAIT_MS = 350

# Maximum total runtime for the monitor itself.
# GitHub Actions has a much larger job timeout, but this prevents
# an accidental infinite loop.
MAX_RUNTIME_SECONDS = 22 * 60


# ============================================================
# Utility
# ============================================================

def normalize_text(text):
    if text is None:
        return ""

    text = str(text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def write_output_file(
    path,
    all_countries,
    suspended,
    unknown,
    errors,
):
    """
    Write all four result categories into one text file.
    """

    lines = [
        "========================================",
        "BH POSTA INTERNATIONAL DOPISNICA",
        "========================================",
        "",
        "========================================",
        "ALL COUNTRIES",
        "========================================",
        "",
    ]

    lines.extend(all_countries)

    lines.extend(
        [
            "",
            "========================================",
            "SUSPENDED COUNTRIES",
            "========================================",
            "",
        ]
    )

    lines.extend(suspended)

    lines.extend(
        [
            "",
            "========================================",
            "UNKNOWN COUNTRIES",
            "========================================",
            "",
        ]
    )

    lines.extend(unknown)

    lines.extend(
        [
            "",
            "========================================",
            "ERROR COUNTRIES",
            "========================================",
            "",
        ]
    )

    lines.extend(errors)

    lines.extend(
        [
            "",
            "========================================",
            "SUMMARY",
            "========================================",
            "",
            f"All countries: {len(all_countries)}",
            f"Suspended:     {len(suspended)}",
            f"Unknown:       {len(unknown)}",
            f"Errors:        {len(errors)}",
            "",
        ]
    )

    path.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def save_debug(page, filename):
    try:
        Path(filename).write_text(
            page.content(),
            encoding="utf-8",
        )
        print(f"DEBUG: Saved {filename}")
    except Exception as exc:
        print(
            f"DEBUG: Could not save {filename}: {exc}"
        )


def selector_exists(page):
    try:
        return page.locator(
            f"select#{DESTINATION_SELECT}"
        ).count() > 0
    except Exception:
        return False


def runtime_exceeded(start_time):
    return (
        time.monotonic() - start_time
        >= MAX_RUNTIME_SECONDS
    )


# ============================================================
# Page text
# ============================================================

def get_visible_text(page):
    try:
        return normalize_text(
            page.locator("body").inner_text()
        )
    except Exception:
        return ""


def get_result_text(page):
    selectors = [
        "#lblRezultat",
        "[id$='lblRezultat']",
    ]

    for selector in selectors:
        try:
            locator = page.locator(selector)

            if locator.count() > 0:
                text = normalize_text(
                    locator.first.inner_text()
                )

                if text:
                    return text
        except Exception:
            pass

    return get_visible_text(page)


def get_error_text(page):
    selectors = [
        "#lblMeDoPoruka",
        "#lblMeObPiPoruka",
        "[id$='lblMeDoPoruka']",
        "[id$='lblMeObPiPoruka']",
    ]

    for selector in selectors:
        try:
            locator = page.locator(selector)

            if locator.count() > 0:
                text = normalize_text(
                    locator.first.inner_text()
                )

                if text:
                    return text
        except Exception:
            pass

    return ""


# ============================================================
# International traffic
# ============================================================

def select_international_tab(page):
    print(
        "2. Selecting Međunarodni promet..."
    )

    tab_control = page.locator(
        "#ASPxTabControl1"
    )

    if tab_control.count() == 0:
        raise RuntimeError(
            "ASPxTabControl1 was not found."
        )

    print(
        "   ASPxTabControl1 found."
    )

    names = [
        "Međunarodni promet",
        "Međunarodni",
        "Medjunarodni promet",
        "Medjunarodni",
    ]

    clicked = False

    # --------------------------------------------------------
    # Prefer an actual visible text element.
    # --------------------------------------------------------

    for name in names:
        try:
            locator = page.get_by_text(
                name,
                exact=False,
            )

            count = locator.count()

            for i in range(count):
                try:
                    candidate = locator.nth(i)

                    if not candidate.is_visible():
                        continue

                    print(
                        f"   Clicking tab text: {name}"
                    )

                    candidate.click(
                        timeout=10000
                    )

                    clicked = True
                    break

                except Exception:
                    continue

            if clicked:
                break

        except Exception:
            continue

    # --------------------------------------------------------
    # DevExpress fallback.
    # --------------------------------------------------------

    if not clicked:

        print(
            "   Text click failed; trying "
            "DevExpress tab elements..."
        )

        selectors = [
            "#ASPxTabControl1 .dxtc-tab",
            "#ASPxTabControl1 .dxtc-tabLink",
            "#ASPxTabControl1 td[id*='T1']",
            "#ASPxTabControl1 [id*='T1']",
        ]

        for selector in selectors:
            try:
                locator = page.locator(
                    selector
                )

                count = locator.count()

                if count >= 2:
                    locator.nth(1).click(
                        timeout=10000
                    )

                    clicked = True
                    break

                if count == 1:
                    locator.first.click(
                        timeout=10000
                    )

                    clicked = True
                    break

            except Exception:
                continue

    if not clicked:
        raise RuntimeError(
            "Could not click Međunarodni promet tab."
        )

    print(
        "   Waiting for Međunarodni promet callback..."
    )

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # Do NOT wait for ddlMeDoOdrediste here.
    #
    # The destination selector is not guaranteed to be part
    # of the tab callback response. It may appear only after
    # the service/Dopisnica selection.
    # --------------------------------------------------------

    try:
        page.wait_for_load_state(
            "networkidle",
            timeout=10000,
        )
    except PlaywrightTimeoutError:
        pass

    page.wait_for_timeout(1200)

    save_debug(
        page,
        "debug_after_international.html",
    )

    print(
        "   Međunarodni promet tab callback completed."
    )


# ============================================================
# Dopisnica
# ============================================================

def select_dopisnica(page):
    print(
        "3. Selecting Dopisnica..."
    )

    # --------------------------------------------------------
    # DO NOT require the destination selector here.
    #
    # The previous failure happened because the script assumed
    # that the selector must exist immediately after activating
    # Međunarodni promet.
    # --------------------------------------------------------

    active = page.locator(
        "img[src*='Dopisnica_Aktivna.png']"
    )

    try:
        if active.count() > 0:
            print(
                "   Dopisnica is already active."
            )
            return
    except Exception:
        pass

    selectors = [
        "#ImageButton8",
        "input#ImageButton8",
        "input[name='ImageButton8']",
        "input[id$='ImageButton8']",
        "img[src*='Dopisnica']",
    ]

    clicked = False

    for selector in selectors:

        try:
            locator = page.locator(
                selector
            )

            count = locator.count()

            if count == 0:
                continue

            for i in range(count):

                candidate = locator.nth(i)

                try:
                    if not candidate.is_visible():
                        continue
                except Exception:
                    pass

                try:
                    print(
                        f"   Clicking {selector}"
                    )

                    candidate.click(
                        timeout=10000
                    )

                    clicked = True
                    break

                except Exception:
                    continue

            if clicked:
                break

        except Exception:
            continue

    # --------------------------------------------------------
    # JavaScript fallback.
    # --------------------------------------------------------

    if not clicked:

        print(
            "   Direct Dopisnica click failed; "
            "trying DOM click..."
        )

        try:
            clicked = page.evaluate(
                """
                () => {
                    const el =
                        document.getElementById('ImageButton8');

                    if (!el) {
                        return false;
                    }

                    el.click();
                    return true;
                }
                """
            )
        except Exception:
            clicked = False

    if not clicked:

        save_debug(
            page,
            "debug_before_dopisnica_failure.html",
        )

        raise RuntimeError(
            "Could not click Dopisnica."
        )

    print(
        "   Waiting for Dopisnica callback..."
    )

    try:
        page.wait_for_load_state(
            "networkidle",
            timeout=10000,
        )
    except PlaywrightTimeoutError:
        pass

    page.wait_for_timeout(1200)

    # --------------------------------------------------------
    # NOW the destination selector should exist.
    # --------------------------------------------------------

    if not selector_exists(page):

        print(
            "   Destination selector not immediately "
            "visible after Dopisnica; waiting..."
        )

        try:
            page.wait_for_selector(
                f"select#{DESTINATION_SELECT}",
                timeout=10000,
            )
        except PlaywrightTimeoutError:
            pass

    if not selector_exists(page):

        save_debug(
            page,
            "debug_after_dopisnica_failure.html",
        )

        raise RuntimeError(
            "Dopisnica was selected, but "
            f"#{DESTINATION_SELECT} is not present."
        )

    print(
        "   Destination selector is available."
    )


# ============================================================
# Air transport
# ============================================================

def select_air_transport(page):
    print(
        "4. Selecting Avionski prijenos..."
    )

    checkbox = page.locator(
        f"#{AIR_CHECKBOX}"
    )

    if checkbox.count() == 0:
        raise RuntimeError(
            f"#{AIR_CHECKBOX} was not found."
        )

    try:
        checked = checkbox.is_checked()
    except Exception:
        checked = False

    if checked:
        print(
            "   Avionski prijenos already enabled."
        )
        return

    print(
        "   Avionski prijenos enabled."
    )

    try:
        checkbox.check(
            timeout=10000
        )
    except Exception:
        checkbox.click(
            timeout=10000
        )

    try:
        page.wait_for_load_state(
            "networkidle",
            timeout=10000,
        )
    except PlaywrightTimeoutError:
        pass

    page.wait_for_timeout(700)

    try:
        if not checkbox.is_checked():
            raise RuntimeError(
                "Avionski prijenos checkbox "
                "is still unchecked."
            )
    except Exception as exc:
        raise RuntimeError(
            f"Could not enable Avionski prijenos: {exc}"
        )


# ============================================================
# Weight
# ============================================================

def set_weight(page):
    print(
        f"5. Setting weight to {WEIGHT} g..."
    )

    weight = page.locator(
        f"#{AIR_WEIGHT}"
    )

    if weight.count() == 0:
        raise RuntimeError(
            f"#{AIR_WEIGHT} was not found."
        )

    weight.fill(WEIGHT)

    try:
        weight.press("Tab")
    except Exception:
        pass

    page.wait_for_timeout(300)

    print(
        "   Weight set."
    )


# ============================================================
# Countries
# ============================================================

def get_destinations(page):
    print(
        "6. Reading destination country list..."
    )

    select = page.locator(
        f"select#{DESTINATION_SELECT}"
    )

    if select.count() == 0:
        raise RuntimeError(
            f"#{DESTINATION_SELECT} was not found."
        )

    options = select.locator(
        "option"
    )

    count = options.count()

    destinations = []

    for i in range(count):

        option = options.nth(i)

        try:
            value = option.get_attribute(
                "value"
            )

            name = normalize_text(
                option.inner_text()
            )

            if value and name:
                destinations.append(
                    (
                        value.strip(),
                        name,
                    )
                )

        except Exception:
            continue

    if not destinations:
        raise RuntimeError(
            "Destination selector exists but "
            "contains no countries."
        )

    print(
        f"   Found {len(destinations)} "
        f"destination entries."
    )

    return destinations


# ============================================================
# Country selection
# ============================================================

def select_country(page, code):
    select = page.locator(
        f"select#{DESTINATION_SELECT}"
    )

    if select.count() == 0:
        raise RuntimeError(
            f"#{DESTINATION_SELECT} disappeared."
        )

    select.select_option(
        value=code
    )

    # Allow any client-side onchange logic to run.
    page.wait_for_timeout(
        COUNTRY_WAIT_MS
    )


# ============================================================
# Calculate
# ============================================================

def click_calculate(page):
    selectors = [
        "#btnMeDoIzracunaj",
        "input[name='btnMeDoIzracunaj']",
        "input[id$='btnMeDoIzracunaj']",
        "button:has-text('Izračunaj')",
        "input[value='Izračunaj']",
    ]

    for selector in selectors:

        try:
            locator = page.locator(
                selector
            )

            count = locator.count()

            if count == 0:
                continue

            for i in range(count):

                candidate = locator.nth(i)

                try:
                    if not candidate.is_visible():
                        continue
                except Exception:
                    pass

                try:
                    candidate.click(
                        timeout=5000
                    )

                    # Do not wait for full networkidle here.
                    # The calculator may keep connections open.
                    page.wait_for_timeout(450)

                    return

                except Exception:
                    continue

        except Exception:
            continue

    raise RuntimeError(
        "Could not find or click Izračunaj."
    )


# ============================================================
# Result parsing
# ============================================================

def parse_price(text):
    text = normalize_text(text)

    # Primary format:
    #
    # Ukupna cijena 2,20 KM
    #
    match = re.search(
        r"Ukupna\s+cijena\s*"
        r"([0-9]+(?:[,.][0-9]+)?)"
        r"\s*KM",
        text,
        flags=re.IGNORECASE,
    )

    if not match:

        # Fallback:
        #
        # 2,20 KM
        #
        match = re.search(
            r"\b([0-9]+(?:[,.][0-9]+)?)"
            r"\s*KM\b",
            text,
            flags=re.IGNORECASE,
        )

    if not match:
        return None

    value_text = match.group(1)

    try:
        value = float(
            value_text.replace(",", ".")
        )
    except ValueError:
        return None

    return value_text, value


def calculate_country(page, code):
    select_country(
        page,
        code,
    )

    # Make sure weight remains 10 g.
    weight = page.locator(
        f"#{AIR_WEIGHT}"
    )

    if weight.count() > 0:
        try:
            current = weight.input_value()

            if current != WEIGHT:
                weight.fill(WEIGHT)
        except Exception:
            pass

    click_calculate(page)

    # Read result.
    text = get_result_text(page)
    error_text = get_error_text(page)

    combined = normalize_text(
        f"{error_text} {text}"
    )

    # --------------------------------------------------------
    # Suspended
    # --------------------------------------------------------

    if (
        SUSPENDED_MESSAGE.lower()
        in combined.lower()
    ):
        return (
            "SUSPENDED",
            SUSPENDED_MESSAGE,
        )

    # --------------------------------------------------------
    # Price
    # --------------------------------------------------------

    price = parse_price(
        combined
    )

    if price is not None:

        price_text, price_value = price

        if price_value == 0:
            return (
                "UNKNOWN",
                f"Ukupna cijena {price_text} KM",
            )

        return (
            "AVAILABLE",
            f"{price_text} KM",
        )

    # --------------------------------------------------------
    # Unknown
    # --------------------------------------------------------

    return (
        "UNKNOWN",
        "Cijena nije pronađena",
    )


# ============================================================
# Main
# ============================================================

def main():

    start_time = time.monotonic()

    print(
        "Opening calculator..."
    )

    with sync_playwright() as playwright:

        browser = playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )

        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 "
                "(X11; Linux x86_64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/151.0.0.0 "
                "Safari/537.36"
            ),
            locale="en-US",
            viewport={
                "width": 1440,
                "height": 1000,
            },
        )

        page = context.new_page()

        page.set_default_timeout(
            15000
        )

        try:

            # =================================================
            # 1. Open
            # =================================================

            page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            page.wait_for_timeout(
                1000
            )

            print(
                f"Initial page received: "
                f"{len(page.content()):,} bytes"
            )

            save_debug(
                page,
                "debug_original_page.html",
            )

            # =================================================
            # 2. International
            # =================================================

            select_international_tab(
                page
            )

            # =================================================
            # 3. Dopisnica
            # =================================================

            select_dopisnica(
                page
            )

            # =================================================
            # 4. Countries
            # =================================================

            destinations = get_destinations(
                page
            )

            print()
            print(
                f"Destination list contains "
                f"{len(destinations)} countries."
            )

            # =================================================
            # 5. Air
            # =================================================

            select_air_transport(
                page
            )

            # =================================================
            # 6. Weight
            # =================================================

            set_weight(
                page
            )

            # =================================================
            # Re-read countries
            # =================================================

            destinations = get_destinations(
                page
            )

            # =================================================
            # 7. Check countries
            # =================================================

            print()
            print(
                "7. Checking every destination..."
            )

            all_countries = [
                country
                for code, country in destinations
            ]

            suspended = []
            unknown = []
            errors = []

            total = len(
                destinations
            )

            for number, (code, country) in enumerate(
                destinations,
                start=1,
            ):

                # ------------------------------------------------
                # Runtime guard
                # ------------------------------------------------

                if runtime_exceeded(
                    start_time
                ):
                    raise RuntimeError(
                        "Maximum monitor runtime reached."
                    )

                print(
                    f"[{number}/{total}] "
                    f"{country} ({code})",
                    flush=True,
                )

                try:

                    status, detail = calculate_country(
                        page,
                        code,
                    )

                    if status == "AVAILABLE":

                        print(
                            f"    -> AVAILABLE "
                            f"({detail})",
                            flush=True,
                        )

                    elif status == "SUSPENDED":

                        print(
                            "    -> SUSPENDED",
                            flush=True,
                        )

                        suspended.append(
                            country
                        )

                    else:

                        print(
                            f"    -> UNKNOWN "
                            f"({detail})",
                            flush=True,
                        )

                        unknown.append(
                            country
                        )

                except Exception as exc:

                    print(
                        f"    -> ERROR: {exc}",
                        flush=True,
                    )

                    errors.append(
                        f"{country} | {exc}"
                    )

                    # --------------------------------------------
                    # Do not restart the entire browser for every
                    # individual error. That was one of the major
                    # causes of excessive runtime.
                    # --------------------------------------------

                    try:
                        if not selector_exists(page):
                            print(
                                "    Selector disappeared; "
                                "attempting page recovery...",
                                flush=True,
                            )

                            page.reload(
                                wait_until="domcontentloaded",
                                timeout=30000,
                            )

                            page.wait_for_timeout(
                                1000
                            )

                            select_international_tab(
                                page
                            )

                            select_dopisnica(
                                page
                            )

                            select_air_transport(
                                page
                            )

                            set_weight(
                                page
                            )

                    except Exception as recovery_exc:

                        print(
                            "    Recovery failed: "
                            f"{recovery_exc}",
                            flush=True,
                        )

                # Small pause to avoid hammering the site.
                time.sleep(0.15)

            # =================================================
            # 8. Write ONE combined output file
            # =================================================

            write_output_file(
                OUTPUT_FILE,
                all_countries,
                suspended,
                unknown,
                errors,
            )

            # =================================================
            # 9. Summary
            # =================================================

            elapsed = (
                time.monotonic()
                - start_time
            )

            print()
            print(
                "========================================"
            )
            print(
                "Finished."
            )
            print(
                "========================================"
            )
            print(
                f"Destinations: {total}"
            )
            print(
                f"All countries: {len(all_countries)}"
            )
            print(
                f"Suspended:     {len(suspended)}"
            )
            print(
                f"Unknown:       {len(unknown)}"
            )
            print(
                f"Errors:        {len(errors)}"
            )
            print(
                f"Runtime:       {elapsed:.1f} seconds"
            )
            print(
                "========================================"
            )

            print(
                f"Output:        {OUTPUT_FILE}"
            )

        finally:

            browser.close()


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":

    try:
        main()

    except Exception as exc:

        print(
            f"FATAL ERROR: {exc}",
            file=sys.stderr,
        )

        sys.exit(1)
