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

AVAILABLE_FILE = Path("available_countries.txt")
SUSPENDED_FILE = Path("suspended_countries.txt")
UNKNOWN_FILE = Path("unknown_countries.txt")
ERROR_FILE = Path("error_countries.txt")

# ============================================================
# Dopisnica controls
# ============================================================

DESTINATION_SELECT = "ddlMeDoOdrediste"
AIR_CHECKBOX = "chbMeDoAvionski"
AIR_WEIGHT = "tbxMeDoAvioTezina"

DOPISNICA_BUTTON = "ImageButton8"

SUSPENDED_MESSAGE = (
    "Prijem pošiljaka se trenutno ne vrši za odabranu državu"
)

WEIGHT = "10"

WAIT_MS = 1500


# ============================================================
# Utility
# ============================================================

def normalize_text(text):
    if text is None:
        return ""

    text = str(text)

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def write_lines(path, values):
    values = list(values)

    if values:
        path.write_text(
            "\n".join(values) + "\n",
            encoding="utf-8",
        )
    else:
        path.write_text(
            "",
            encoding="utf-8",
        )


def save_debug(page, filename):
    try:
        Path(filename).write_text(
            page.content(),
            encoding="utf-8",
        )

        print(
            f"DEBUG: Saved {filename}"
        )

    except Exception as exc:
        print(
            f"DEBUG: Could not save {filename}: {exc}"
        )


# ============================================================
# Page inspection
# ============================================================

def selector_exists(page):
    try:
        return (
            page.locator(
                f"select#{DESTINATION_SELECT}"
            ).count() > 0
        )
    except Exception:
        return False


def get_visible_text(page):
    try:
        return normalize_text(
            page.locator("body").inner_text()
        )
    except Exception:
        return ""


def get_result_text(page):
    """
    Look specifically for the calculator result label,
    but also inspect the page text as a fallback.
    """

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
        "#lblMeObPiPoruka",
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
# International tab
# ============================================================

def select_international_tab(page):
    """
    Activate the DevExpress tab:

        Međunarodni promet

    IMPORTANT:

    We intentionally DO NOT require
    ddlMeDoOdrediste here.

    The destination selector belongs to the Dopisnica
    calculator state and may only appear after
    ImageButton8 is activated.
    """

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

    clicked = False

    # --------------------------------------------------------
    # Try visible tab text.
    # --------------------------------------------------------

    names = [
        "Međunarodni promet",
        "Međunarodni",
        "Medjunarodni promet",
        "Medjunarodni",
    ]

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
            "   Text click did not identify the tab; "
            "trying DevExpress tab elements..."
        )

        tab_selectors = [
            "#ASPxTabControl1 .dxtc-tab",
            "#ASPxTabControl1 .dxtc-tabLink",
            "#ASPxTabControl1 td[id*='T1']",
            "#ASPxTabControl1 [id*='T1']",
        ]

        for selector in tab_selectors:

            try:
                locator = page.locator(
                    selector
                )

                count = locator.count()

                print(
                    f"   Selector {selector}: {count}"
                )

                if count >= 2:

                    locator.nth(1).click(
                        timeout=10000
                    )

                    clicked = True

                    break

                elif count == 1:

                    locator.first.click(
                        timeout=10000
                    )

                    clicked = True

                    break

            except Exception:
                continue

    if not clicked:
        save_debug(
            page,
            "debug_international_click_failure.html",
        )

        raise RuntimeError(
            "Could not click Međunarodni promet tab."
        )

    # --------------------------------------------------------
    # Wait for ASP.NET AJAX / DevExpress processing.
    #
    # IMPORTANT:
    #
    # We do NOT check ddlMeDoOdrediste here.
    # --------------------------------------------------------

    print(
        "   Waiting for Međunarodni promet callback..."
    )

    try:
        page.wait_for_load_state(
            "networkidle",
            timeout=15000,
        )
    except PlaywrightTimeoutError:
        pass

    page.wait_for_timeout(
        2000
    )

    print(
        "   Međunarodni promet tab click completed."
    )

    print(
        "   Continuing to Dopisnica without requiring "
        f"#{DESTINATION_SELECT} yet."
    )


# ============================================================
# Dopisnica
# ============================================================

def select_dopisnica(page):
    """
    Activate Dopisnica.

    IMPORTANT:

    ddlMeDoOdrediste is NOT required before this click.

    We first activate ImageButton8 and only then wait for
    ddlMeDoOdrediste to appear.
    """

    print(
        "3. Selecting Dopisnica..."
    )

    clicked = False

    # --------------------------------------------------------
    # Check whether Dopisnica already appears active.
    # --------------------------------------------------------

    try:

        active = page.locator(
            "img[src*='Dopisnica_Aktivna.png']"
        )

        if active.count() > 0:

            print(
                "   Dopisnica is already active."
            )

            clicked = True

    except Exception:
        pass

    # --------------------------------------------------------
    # If not active, click ImageButton8.
    # --------------------------------------------------------

    if not clicked:

        selectors = [
            f"input#{DOPISNICA_BUTTON}",
            f"input[name='{DOPISNICA_BUTTON}']",
            f"input[id$='{DOPISNICA_BUTTON}']",
            f"img[src*='Dopisnica']",
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

                        print(
                            f"   Trying Dopisnica selector: "
                            f"{selector}"
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
            "trying DOM lookup..."
        )

        try:

            clicked = page.evaluate(
                """
                () => {
                    const el =
                        document.getElementById(
                            'ImageButton8'
                        );

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

    # --------------------------------------------------------
    # Wait for Dopisnica ASP.NET callback/postback.
    # --------------------------------------------------------

    print(
        "   Waiting for Dopisnica callback..."
    )

    try:

        page.wait_for_load_state(
            "networkidle",
            timeout=15000,
        )

    except PlaywrightTimeoutError:
        pass

    page.wait_for_timeout(
        2500
    )

    # --------------------------------------------------------
    # NOW require the destination selector.
    # --------------------------------------------------------

    if not selector_exists(page):

        print(
            "   Destination selector not immediately "
            "visible after Dopisnica."
        )

        try:

            page.wait_for_selector(
                f"select#{DESTINATION_SELECT}",
                timeout=15000,
            )

        except PlaywrightTimeoutError:
            pass

    if not selector_exists(page):

        save_debug(
            page,
            "debug_after_dopisnica_failure.html",
        )

        raise RuntimeError(
            "Dopisnica was clicked, but "
            f"#{DESTINATION_SELECT} is not present."
        )

    print(
        "   Dopisnica selected successfully."
    )

    print(
        f"   Destination selector "
        f"#{DESTINATION_SELECT} is now available."
    )


# ============================================================
# Avionski prijenos
# ============================================================

def select_air_transport(page):
    print(
        "4. Selecting Avionski prijenos..."
    )

    checkbox = page.locator(
        f"#{AIR_CHECKBOX}"
    )

    if checkbox.count() == 0:

        save_debug(
            page,
            "debug_air_checkbox_missing.html",
        )

        raise RuntimeError(
            f"#{AIR_CHECKBOX} was not found."
        )

    # --------------------------------------------------------
    # Check current state.
    # --------------------------------------------------------

    try:

        checked = checkbox.is_checked()

    except Exception:

        checked = False

    if checked:

        print(
            "   Avionski prijenos already enabled."
        )

        return

    # --------------------------------------------------------
    # Click/check checkbox.
    # --------------------------------------------------------

    print(
        "   Clicking Avionski prijenos..."
    )

    try:

        checkbox.check(
            timeout=10000
        )

    except Exception:

        checkbox.click(
            timeout=10000
        )

    # --------------------------------------------------------
    # Wait for ASP.NET postback.
    # --------------------------------------------------------

    try:

        page.wait_for_load_state(
            "networkidle",
            timeout=15000,
        )

    except PlaywrightTimeoutError:
        pass

    page.wait_for_timeout(
        1500
    )

    # --------------------------------------------------------
    # Verify.
    # --------------------------------------------------------

    try:

        if not checkbox.is_checked():

            raise RuntimeError(
                "Avionski prijenos checkbox is "
                "still unchecked."
            )

    except Exception as exc:

        save_debug(
            page,
            "debug_air_checkbox_failure.html",
        )

        raise RuntimeError(
            f"Could not enable Avionski prijenos: {exc}"
        )

    print(
        "   Avionski prijenos enabled."
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

        save_debug(
            page,
            "debug_weight_missing.html",
        )

        raise RuntimeError(
            f"#{AIR_WEIGHT} was not found."
        )

    # --------------------------------------------------------
    # Fill weight.
    # --------------------------------------------------------

    weight.fill(
        WEIGHT
    )

    # Trigger normal browser change/blur behavior.

    try:

        weight.press(
            "Tab"
        )

    except Exception:
        pass

    page.wait_for_timeout(
        500
    )

    print(
        "   Weight set."
    )


# ============================================================
# Country list
# ============================================================

def get_destinations(page):
    print(
        "6. Reading destination country list..."
    )

    select = page.locator(
        f"select#{DESTINATION_SELECT}"
    )

    if select.count() == 0:

        save_debug(
            page,
            "debug_destination_missing.html",
        )

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
# Calculator
# ============================================================

def select_country(page, code):
    select = page.locator(
        f"select#{DESTINATION_SELECT}"
    )

    if select.count() == 0:

        raise RuntimeError(
            f"#{DESTINATION_SELECT} disappeared."
        )

    # --------------------------------------------------------
    # Select country.
    # --------------------------------------------------------

    select.select_option(
        value=code
    )

    # --------------------------------------------------------
    # Allow onchange/postback JavaScript to execute.
    # --------------------------------------------------------

    try:

        page.wait_for_load_state(
            "networkidle",
            timeout=15000,
        )

    except PlaywrightTimeoutError:
        pass

    page.wait_for_timeout(
        WAIT_MS
    )


def click_calculate(page):
    """
    Find the actual Izračunaj button and click it.
    """

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

                    print(
                        f"    Clicking calculate button "
                        f"using {selector}"
                    )

                    candidate.click(
                        timeout=10000
                    )

                    try:

                        page.wait_for_load_state(
                            "networkidle",
                            timeout=15000,
                        )

                    except PlaywrightTimeoutError:
                        pass

                    page.wait_for_timeout(
                        1000
                    )

                    return

                except Exception:
                    continue

        except Exception:
            continue

    save_debug(
        page,
        "debug_calculate_button_failure.html",
    )

    raise RuntimeError(
        "Could not find or click Izračunaj."
    )


# ============================================================
# Calculate one country
# ============================================================

def calculate_country(page, code):
    """
    Select destination and calculate the 10 g price.

    Returns:

        ("AVAILABLE", price)

        ("SUSPENDED", message)

        ("UNKNOWN", detail)
    """

    # --------------------------------------------------------
    # Select country.
    # --------------------------------------------------------

    select_country(
        page,
        code,
    )

    # --------------------------------------------------------
    # Make absolutely sure weight is still 10 g.
    # --------------------------------------------------------

    weight = page.locator(
        f"#{AIR_WEIGHT}"
    )

    if weight.count() > 0:

        try:

            current_value = weight.input_value()

            if current_value != WEIGHT:

                weight.fill(
                    WEIGHT
                )

                try:
                    weight.press(
                        "Tab"
                    )
                except Exception:
                    pass

        except Exception:
            pass

    # --------------------------------------------------------
    # Calculate.
    # --------------------------------------------------------

    click_calculate(
        page
    )

    # --------------------------------------------------------
    # Read result.
    # --------------------------------------------------------

    text = get_result_text(
        page
    )

    error_text = get_error_text(
        page
    )

    combined = normalize_text(
        f"{error_text} {text}"
    )

    # --------------------------------------------------------
    # Suspended / unavailable.
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
    # Primary price format.
    #
    # Example:
    #
    # Ukupna cijena 2,00 KM
    # --------------------------------------------------------

    match = re.search(
        r"Ukupna\s+cijena\s*"
        r"([0-9]+(?:[,.][0-9]+)?)"
        r"\s*KM",
        combined,
        flags=re.IGNORECASE,
    )

    if match:

        price_text = (
            f"{match.group(1)} KM"
        )

        normalized = (
            match.group(1)
            .replace(",", ".")
        )

        try:

            price_value = float(
                normalized
            )

        except ValueError:

            price_value = None

        if price_value == 0:

            return (
                "UNKNOWN",
                f"Ukupna cijena {price_text}",
            )

        return (
            "AVAILABLE",
            price_text,
        )

    # --------------------------------------------------------
    # General KM format fallback.
    # --------------------------------------------------------

    match = re.search(
        r"\b([0-9]+(?:[,.][0-9]+)?)\s*KM\b",
        combined,
        flags=re.IGNORECASE,
    )

    if match:

        price_text = (
            f"{match.group(1)} KM"
        )

        normalized = (
            match.group(1)
            .replace(",", ".")
        )

        try:

            price_value = float(
                normalized
            )

        except ValueError:

            price_value = None

        if price_value == 0:

            return (
                "UNKNOWN",
                f"Ukupna cijena {price_text}",
            )

        return (
            "AVAILABLE",
            price_text,
        )

    # --------------------------------------------------------
    # No recognizable result.
    # --------------------------------------------------------

    return (
        "UNKNOWN",
        "Cijena nije pronađena",
    )


# ============================================================
# Main
# ============================================================

def main():

    print(
        "Opening calculator..."
    )

    with sync_playwright() as playwright:

        browser = playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
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
            20000
        )

        try:

            # =================================================
            # 1. Open calculator
            # =================================================

            page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            try:

                page.wait_for_load_state(
                    "networkidle",
                    timeout=20000,
                )

            except PlaywrightTimeoutError:
                pass

            page.wait_for_timeout(
                1500
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
            # 2. Međunarodni promet
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
            # 4. Read country list
            # =================================================

            destinations = get_destinations(
                page
            )

            # =================================================
            # 5. Avionski prijenos
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
            # Re-read destination list after all controls
            # have been configured.
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
            # 7. Check every destination
            # =================================================

            print()
            print(
                "7. Checking every destination..."
            )

            available = []
            suspended = []
            unknown = []
            errors = []

            for number, (code, country) in enumerate(
                destinations,
                start=1,
            ):

                print(
                    f"[{number}/{len(destinations)}] "
                    f"{country} ({code})",
                    flush=True,
                )

                try:

                    status, detail = calculate_country(
                        page,
                        code,
                    )

                    # -----------------------------------------
                    # Available
                    # -----------------------------------------

                    if status == "AVAILABLE":

                        print(
                            f"    -> AVAILABLE "
                            f"({detail})",
                            flush=True,
                        )

                        available.append(
                            country
                        )

                    # -----------------------------------------
                    # Suspended
                    # -----------------------------------------

                    elif status == "SUSPENDED":

                        print(
                            "    -> SUSPENDED",
                            flush=True,
                        )

                        suspended.append(
                            country
                        )

                    # -----------------------------------------
                    # Unknown
                    # -----------------------------------------

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

                # -----------------------------------------
                # Don't hammer the server.
                # -----------------------------------------

                time.sleep(
                    0.5
                )

            # =================================================
            # 8. Write output files
            # =================================================

            write_lines(
                AVAILABLE_FILE,
                available,
            )

            write_lines(
                SUSPENDED_FILE,
                suspended,
            )

            write_lines(
                UNKNOWN_FILE,
                unknown,
            )

            write_lines(
                ERROR_FILE,
                errors,
            )

            # =================================================
            # 9. Summary
            # =================================================

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
                f"Destinations: {len(destinations)}"
            )

            print(
                f"Available:    {len(available)}"
            )

            print(
                f"Suspended:    {len(suspended)}"
            )

            print(
                f"Unknown:      {len(unknown)}"
            )

            print(
                f"Errors:       {len(errors)}"
            )

            print(
                "========================================"
            )

            print(
                f"Available: {AVAILABLE_FILE}"
            )

            print(
                f"Suspended: {SUSPENDED_FILE}"
            )

            print(
                f"Unknown:   {UNKNOWN_FILE}"
            )

            print(
                f"Errors:    {ERROR_FILE}"
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
