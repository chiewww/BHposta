import re
import sys
import time
from pathlib import Path

from playwright.sync_api import (
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)


# ============================================================
# Configuration
# ============================================================

URL = (
    "https://bhpwebout.posta.ba/"
    "KalkulatorCijena_WEB_app/Bos/Default.aspx"
)

AVAILABLE_FILE = Path("available_countries.txt")
SUSPENDED_FILE = Path("suspended_countries.txt")
UNKNOWN_FILE = Path("unknown_countries.txt")
ERROR_FILE = Path("error_countries.txt")

DEBUG_ORIGINAL = Path("debug_original_page.html")
DEBUG_FAILURE = Path("debug_failure.html")

DESTINATION_SELECT = "ddlMeDoOdrediste"
AIR_CHECKBOX = "chbMeDoAvionski"
AIR_WEIGHT = "tbxMeDoAvioTezina"

# IMPORTANT:
# This is Dopisnica, not Pismo.
DOPISNICA_BUTTON = "ImageButton8"

SUSPENDED_MESSAGE = (
    "Prijem pošiljaka se trenutno ne vrši za odabranu državu"
)

WEIGHT = "10"

# ------------------------------------------------------------
# Performance settings
# ------------------------------------------------------------

# Do NOT use networkidle for every country.
COUNTRY_WAIT_MS = 350

# Maximum time to wait for a calculator result.
RESULT_TIMEOUT_MS = 5000

# Retry transient failures.
MAX_COUNTRY_RETRIES = 2

# Small pause between retries only.
RETRY_DELAY_MS = 400

# Overall safety limit.
MAX_RUNTIME_SECONDS = 14 * 60


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
        print(f"DEBUG: Saved {filename}")
    except Exception as exc:
        print(
            f"DEBUG: Could not save {filename}: {exc}"
        )


def check_runtime(start_time):
    elapsed = time.monotonic() - start_time

    if elapsed >= MAX_RUNTIME_SECONDS:
        raise RuntimeError(
            "Maximum monitor runtime reached."
        )


# ============================================================
# Page inspection
# ============================================================

def selector_exists(page):
    return (
        page.locator(
            f"select#{DESTINATION_SELECT}"
        ).count()
        > 0
    )


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
                    locator.first.inner_text(
                        timeout=1000
                    )
                )

                if text:
                    return text

        except Exception:
            pass

    return ""


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
                    locator.first.inner_text(
                        timeout=1000
                    )
                )

                if text:
                    return text

        except Exception:
            pass

    return ""


def get_result_signature(page):
    """
    Get the current visible calculator result/message.

    Used to detect when the ASP.NET callback has finished
    without waiting for networkidle.
    """

    result = get_result_text(page)
    error = get_error_text(page)

    return normalize_text(
        f"{result} {error}"
    )


# ============================================================
# International tab
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
    # Text click.
    # --------------------------------------------------------

    for name in names:

        try:
            locator = page.get_by_text(
                name,
                exact=False,
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
                    continue

                try:
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
            "   Trying DevExpress tab elements..."
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

                elif count == 1:

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
    # Do not require ddlMeDoOdrediste to appear immediately
    # in the AJAX response.
    #
    # We inspect the actual browser DOM and allow the page
    # time to finish its callback.
    # --------------------------------------------------------

    try:
        page.wait_for_timeout(1000)
    except Exception:
        pass

    if not selector_exists(page):

        try:
            page.wait_for_selector(
                f"select#{DESTINATION_SELECT}",
                timeout=12000,
                state="attached",
            )
        except PlaywrightTimeoutError:
            pass

    if not selector_exists(page):

        save_debug(
            page,
            "debug_after_international.html",
        )

        raise RuntimeError(
            "Međunarodni promet was clicked, but "
            f"#{DESTINATION_SELECT} is not present."
        )

    print(
        "   Međunarodni promet activated successfully."
    )


# ============================================================
# Dopisnica
# ============================================================

def select_dopisnica(page):
    print(
        "3. Selecting Dopisnica..."
    )

    if not selector_exists(page):
        raise RuntimeError(
            "Destination selector is missing before "
            "Dopisnica."
        )

    # --------------------------------------------------------
    # Check whether already active.
    # --------------------------------------------------------

    try:
        active = page.locator(
            "img[src*='Dopisnica_Aktivna.png']"
        )

        if active.count() > 0:
            print(
                "   Dopisnica is already active."
            )
            return

    except Exception:
        pass

    # --------------------------------------------------------
    # ImageButton8 is the known Dopisnica control.
    # --------------------------------------------------------

    selectors = [
        f"#{DOPISNICA_BUTTON}",
        f"input#{DOPISNICA_BUTTON}",
        f"input[name='{DOPISNICA_BUTTON}']",
        f"input[id$='{DOPISNICA_BUTTON}']",
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
            "   Direct click failed; trying DOM click..."
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
    # Do NOT wait for networkidle here.
    # --------------------------------------------------------

    page.wait_for_timeout(
        1000
    )

    if not selector_exists(page):

        try:
            page.wait_for_selector(
                f"select#{DESTINATION_SELECT}",
                timeout=10000,
                state="attached",
            )
        except PlaywrightTimeoutError:
            pass

    if not selector_exists(page):

        save_debug(
            page,
            "debug_after_dopisnica_failure.html",
        )

        raise RuntimeError(
            "Dopisnica click completed, but "
            f"#{DESTINATION_SELECT} disappeared."
        )

    print(
        "   Dopisnica selected successfully."
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
        raise RuntimeError(
            f"#{AIR_CHECKBOX} was not found."
        )

    try:
        if checkbox.is_checked():
            print(
                "   Avionski prijenos already enabled."
            )
            return
    except Exception:
        pass

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

    # Short targeted wait.
    page.wait_for_timeout(
        800
    )

    try:
        if not checkbox.is_checked():
            raise RuntimeError(
                "Checkbox is still unchecked."
            )
    except Exception as exc:
        raise RuntimeError(
            "Could not enable Avionski prijenos: "
            f"{exc}"
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
        raise RuntimeError(
            f"#{AIR_WEIGHT} was not found."
        )

    weight.fill(
        WEIGHT
    )

    weight.press(
        "Tab"
    )

    page.wait_for_timeout(
        300
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
                option.inner_text(
                    timeout=1000
                )
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
# Calculator controls
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

    # --------------------------------------------------------
    # The select has an ASP.NET onchange/postback.
    #
    # We deliberately do NOT wait for networkidle.
    # --------------------------------------------------------

    page.wait_for_timeout(
        COUNTRY_WAIT_MS
    )


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

                    return

                except Exception:
                    continue

        except Exception:
            continue

    raise RuntimeError(
        "Could not find or click Izračunaj."
    )


def wait_for_result(page):
    """
    Wait for a recognizable calculator result.

    This is considerably faster than networkidle.
    """

    deadline = (
        time.monotonic()
        + RESULT_TIMEOUT_MS / 1000
    )

    last_signature = ""

    while time.monotonic() < deadline:

        result = get_result_text(
            page
        )

        error = get_error_text(
            page
        )

        combined = normalize_text(
            f"{result} {error}"
        )

        if combined:

            if (
                SUSPENDED_MESSAGE.lower()
                in combined.lower()
            ):
                return combined

            if re.search(
                r"Ukupna\s+cijena",
                combined,
                flags=re.IGNORECASE,
            ):
                return combined

            if re.search(
                r"\b[0-9]+(?:[,.][0-9]+)?\s*KM\b",
                combined,
                flags=re.IGNORECASE,
            ):
                return combined

            last_signature = combined

        page.wait_for_timeout(
            100
        )

    return last_signature


# ============================================================
# Price parsing
# ============================================================

def parse_calculator_result(text):
    combined = normalize_text(
        text
    )

    # --------------------------------------------------------
    # Suspended.
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
    # Preferred exact result format.
    # --------------------------------------------------------

    match = re.search(
        r"Ukupna\s+cijena\s*"
        r"([0-9]+(?:[,.][0-9]+)?)"
        r"\s*KM",
        combined,
        flags=re.IGNORECASE,
    )

    if match:

        number = match.group(1)

        price = (
            f"{number} KM"
        )

        try:
            value = float(
                number.replace(
                    ",",
                    ".",
                )
            )
        except ValueError:
            value = None

        if value == 0:
            return (
                "UNKNOWN",
                f"Ukupna cijena {price}",
            )

        return (
            "AVAILABLE",
            price,
        )

    # --------------------------------------------------------
    # Generic KM fallback.
    # --------------------------------------------------------

    match = re.search(
        r"\b"
        r"([0-9]+(?:[,.][0-9]+)?)"
        r"\s*KM\b",
        combined,
        flags=re.IGNORECASE,
    )

    if match:

        number = match.group(1)

        price = (
            f"{number} KM"
        )

        try:
            value = float(
                number.replace(
                    ",",
                    ".",
                )
            )
        except ValueError:
            value = None

        if value == 0:
            return (
                "UNKNOWN",
                f"Ukupna cijena {price}",
            )

        return (
            "AVAILABLE",
            price,
        )

    return (
        "UNKNOWN",
        "Cijena nije pronađena",
    )


# ============================================================
# One country
# ============================================================

def calculate_country(page, code):
    """
    Calculate one country.

    The important optimization is that this function does
    not wait for networkidle.
    """

    select_country(
        page,
        code,
    )

    # --------------------------------------------------------
    # Keep weight at 10 g.
    # --------------------------------------------------------

    weight = page.locator(
        f"#{AIR_WEIGHT}"
    )

    if weight.count() > 0:

        try:
            current = weight.input_value()

            if current != WEIGHT:
                weight.fill(
                    WEIGHT
                )

        except Exception:
            try:
                weight.fill(
                    WEIGHT
                )
            except Exception:
                pass

    # --------------------------------------------------------
    # Click calculator.
    # --------------------------------------------------------

    click_calculate(
        page
    )

    # --------------------------------------------------------
    # Wait specifically for result.
    # --------------------------------------------------------

    text = wait_for_result(
        page
    )

    # --------------------------------------------------------
    # If wait_for_result returned nothing, inspect once more.
    # --------------------------------------------------------

    if not text:
        result = get_result_text(
            page
        )

        error = get_error_text(
            page
        )

        text = normalize_text(
            f"{result} {error}"
        )

    return parse_calculator_result(
        text
    )


# ============================================================
# Output
# ============================================================

def save_results(
    available,
    suspended,
    unknown,
    errors,
):
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

        # ----------------------------------------------------
        # Important:
        #
        # Keep default timeout reasonably short. A hung
        # selector should not consume minutes.
        # ----------------------------------------------------

        page.set_default_timeout(
            10000
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

            page.wait_for_timeout(
                1200
            )

            print(
                f"Initial page received: "
                f"{len(page.content()):,} bytes"
            )

            save_debug(
                page,
                DEBUG_ORIGINAL,
            )

            # =================================================
            # 2. International traffic
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
            # 4. Read destinations
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
            # 5. Air transport
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
            # Re-read after configuration.
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

                check_runtime(
                    start_time
                )

                print(
                    f"[{number}/{len(destinations)}] "
                    f"{country} ({code})",
                    flush=True,
                )

                success = False

                for attempt in range(
                    1,
                    MAX_COUNTRY_RETRIES + 1,
                ):

                    try:

                        status, detail = (
                            calculate_country(
                                page,
                                code,
                            )
                        )

                        if status == "AVAILABLE":

                            print(
                                f"    -> AVAILABLE "
                                f"({detail})",
                                flush=True,
                            )

                            available.append(
                                country
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

                        success = True
                        break

                    except Exception as exc:

                        print(
                            f"    attempt "
                            f"{attempt}/"
                            f"{MAX_COUNTRY_RETRIES} "
                            f"failed: {exc}",
                            flush=True,
                        )

                        if attempt < MAX_COUNTRY_RETRIES:

                            page.wait_for_timeout(
                                RETRY_DELAY_MS
                            )

                # ------------------------------------------------
                # All attempts failed.
                # ------------------------------------------------

                if not success:

                    print(
                        "    -> ERROR",
                        flush=True,
                    )

                    errors.append(
                        f"{country} | "
                        f"Could not calculate country"
                    )

                # ------------------------------------------------
                # SAVE PROGRESS AFTER EVERY COUNTRY.
                #
                # If GitHub Actions terminates the process,
                # already completed results are still on disk.
                # ------------------------------------------------

                save_results(
                    available,
                    suspended,
                    unknown,
                    errors,
                )

            # =================================================
            # 8. Final output
            # =================================================

            save_results(
                available,
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
                f"Runtime:      {elapsed:.1f} seconds"
            )
            print(
                "========================================"
            )

        except Exception:

            save_debug(
                page,
                DEBUG_FAILURE,
            )

            raise

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
