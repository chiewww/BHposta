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

DESTINATION_SELECT = "ddlMeDoOdrediste"
AIR_CHECKBOX = "chbMeDoAvionski"
AIR_WEIGHT = "tbxMeDoAvioTezina"

# IMPORTANT:
# Dopisnica = ImageButton8
DOPISNICA_BUTTON = "ImageButton8"

SUSPENDED_MESSAGE = (
    "Prijem pošiljaka se trenutno ne vrši za odabranu državu"
)

WEIGHT = "10"

# ------------------------------------------------------------
# Timing
# ------------------------------------------------------------

PAGE_TIMEOUT = 30_000
TAB_TIMEOUT = 15_000
CONTROL_TIMEOUT = 10_000
COUNTRY_TIMEOUT = 25_000

SHORT_WAIT_MS = 500
CALLBACK_WAIT_MS = 1_000
COUNTRY_PAUSE = 0.5

MAX_RECOVERY_ATTEMPTS = 2


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
            f"DEBUG: Saved {filename}",
            flush=True,
        )

    except Exception as exc:
        print(
            f"DEBUG: Could not save {filename}: {exc}",
            flush=True,
        )


def wait_briefly(page, milliseconds=CALLBACK_WAIT_MS):
    try:
        page.wait_for_timeout(milliseconds)
    except Exception:
        pass


def safe_network_wait(page, timeout=3_000):
    """
    Network-idle is intentionally used only as a short,
    best-effort wait.

    The old version repeatedly waited 15 seconds for
    networkidle. ASP.NET/DevExpress pages can keep connections
    alive, which caused very long runs.
    """

    try:
        page.wait_for_load_state(
            "networkidle",
            timeout=timeout,
        )
    except PlaywrightTimeoutError:
        pass
    except Exception:
        pass


# ============================================================
# DOM helpers
# ============================================================

def selector_exists(page):
    try:
        return (
            page.locator(
                f"select#{DESTINATION_SELECT}"
            ).count()
            > 0
        )
    except Exception:
        return False


def selector_has_options(page):
    try:
        select = page.locator(
            f"select#{DESTINATION_SELECT}"
        )

        if select.count() == 0:
            return False

        return select.locator("option").count() > 0

    except Exception:
        return False


def get_visible_text(page):
    try:
        return normalize_text(
            page.locator("body").inner_text(
                timeout=5_000
            )
        )
    except Exception:
        return ""


def get_result_text(page):
    """
    Read the calculator result.

    Prefer the result label. Fall back to body text.
    """

    selectors = [
        "#lblRezultat",
        "[id$='lblRezultat']",
    ]

    for selector in selectors:

        try:
            locator = page.locator(selector)

            if locator.count() == 0:
                continue

            text = normalize_text(
                locator.first.inner_text(
                    timeout=3_000
                )
            )

            if text:
                return text

        except Exception:
            continue

    return get_visible_text(page)


def get_error_text(page):
    selectors = [
        "#lblMeObPiPoruka",
        "[id$='lblMeObPiPoruka']",
    ]

    for selector in selectors:

        try:
            locator = page.locator(selector)

            if locator.count() == 0:
                continue

            text = normalize_text(
                locator.first.inner_text(
                    timeout=3_000
                )
            )

            if text:
                return text

        except Exception:
            continue

    return ""


# ============================================================
# Page creation
# ============================================================

def create_page(browser):
    """
    Create a fresh browser page.

    A fresh page is considerably safer than trying to repair
    an ASP.NET/DevExpress page after a failed callback.
    """

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
        CONTROL_TIMEOUT
    )

    return context, page


def open_calculator(page):
    print(
        "Opening calculator...",
        flush=True,
    )

    page.goto(
        URL,
        wait_until="domcontentloaded",
        timeout=PAGE_TIMEOUT,
    )

    # Short best-effort wait only.
    safe_network_wait(
        page,
        timeout=3_000,
    )

    wait_briefly(
        page,
        1_000,
    )

    print(
        f"Initial page received: "
        f"{len(page.content()):,} bytes",
        flush=True,
    )


# ============================================================
# International tab
# ============================================================

def find_international_tab(page):
    """
    Find the actual rendered DevExpress tab.

    We deliberately do not make the presence of the destination
    selector part of this function. The tab callback itself does
    not necessarily contain the calculator controls in the
    immediate response.
    """

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

                candidate = locator.nth(i)

                try:
                    if candidate.is_visible():
                        return candidate
                except Exception:
                    continue

        except Exception:
            continue

    # DevExpress fallback.
    selectors = [
        "#ASPxTabControl1 .dxtc-tab",
        "#ASPxTabControl1 .dxtc-tabLink",
        "#ASPxTabControl1 td[id*='T1']",
        "#ASPxTabControl1 [id*='T1']",
    ]

    for selector in selectors:

        try:
            locator = page.locator(selector)

            count = locator.count()

            if count >= 2:
                return locator.nth(1)

            if count == 1:
                return locator.first

        except Exception:
            continue

    return None


def select_international_tab(page):
    print(
        "2. Selecting Međunarodni promet...",
        flush=True,
    )

    tab_control = page.locator(
        "#ASPxTabControl1"
    )

    if tab_control.count() == 0:
        raise RuntimeError(
            "ASPxTabControl1 was not found."
        )

    print(
        "   ASPxTabControl1 found.",
        flush=True,
    )

    tab = find_international_tab(page)

    if tab is None:
        save_debug(
            page,
            "debug_international_tab_not_found.html",
        )

        raise RuntimeError(
            "Could not find Međunarodni promet tab."
        )

    try:
        text = normalize_text(
            tab.inner_text()
        )
    except Exception:
        text = ""

    print(
        f"   Clicking tab: {text or 'Međunarodni promet'}",
        flush=True,
    )

    try:
        tab.click(
            timeout=TAB_TIMEOUT
        )

    except Exception as exc:

        print(
            f"   Normal click failed: {exc}",
            flush=True,
        )

        # JavaScript click fallback.
        try:
            tab.evaluate(
                "(element) => element.click()"
            )
        except Exception as js_exc:

            save_debug(
                page,
                "debug_international_click_failure.html",
            )

            raise RuntimeError(
                "Could not click Međunarodni promet: "
                f"{js_exc}"
            )

    print(
        "   Waiting briefly for Međunarodni promet callback...",
        flush=True,
    )

    # IMPORTANT:
    # Do NOT wait 15-30 seconds for networkidle here.
    safe_network_wait(
        page,
        timeout=3_000,
    )

    wait_briefly(
        page,
        1_500,
    )

    print(
        "   Međunarodni promet request processed.",
        flush=True,
    )


# ============================================================
# Dopisnica
# ============================================================

def find_dopisnica(page):
    selectors = [
        f"#{DOPISNICA_BUTTON}",
        f"input[name='{DOPISNICA_BUTTON}']",
        f"input[id$='{DOPISNICA_BUTTON}']",
        "img[src*='Dopisnica']",
    ]

    for selector in selectors:

        try:
            locator = page.locator(selector)

            count = locator.count()

            if count == 0:
                continue

            for i in range(count):

                candidate = locator.nth(i)

                try:
                    if candidate.is_visible():
                        return candidate
                except Exception:
                    continue

        except Exception:
            continue

    return None


def select_dopisnica(page):
    print(
        "3. Selecting Dopisnica...",
        flush=True,
    )

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # We do NOT require ddlMeDoOdrediste to be present before
    # clicking Dopisnica.
    #
    # This was the source of the earlier failure.
    # The destination list can be created/replaced by the
    # Dopisnica callback itself.
    # --------------------------------------------------------

    button = find_dopisnica(page)

    if button is None:

        save_debug(
            page,
            "debug_dopisnica_not_found.html",
        )

        raise RuntimeError(
            "Dopisnica button ImageButton8 was not found."
        )

    print(
        "   Dopisnica button found.",
        flush=True,
    )

    try:
        button.click(
            timeout=CONTROL_TIMEOUT
        )

    except Exception as exc:

        print(
            f"   Normal Dopisnica click failed: {exc}",
            flush=True,
        )

        try:
            button.evaluate(
                "(element) => element.click()"
            )

        except Exception as js_exc:

            save_debug(
                page,
                "debug_dopisnica_click_failure.html",
            )

            raise RuntimeError(
                "Could not click Dopisnica: "
                f"{js_exc}"
            )

    print(
        "   Waiting briefly for Dopisnica callback...",
        flush=True,
    )

    safe_network_wait(
        page,
        timeout=3_000,
    )

    # Give ASP.NET AJAX enough time to replace the panel.
    wait_briefly(
        page,
        1_500,
    )

    # --------------------------------------------------------
    # Now wait specifically for the destination selector.
    #
    # This is the correct place to require it.
    # --------------------------------------------------------

    try:
        page.wait_for_selector(
            f"select#{DESTINATION_SELECT}",
            state="attached",
            timeout=10_000,
        )

    except PlaywrightTimeoutError:

        save_debug(
            page,
            "debug_after_dopisnica_no_destination.html",
        )

        raise RuntimeError(
            "Dopisnica was clicked, but "
            f"#{DESTINATION_SELECT} did not appear."
        )

    if not selector_has_options(page):

        save_debug(
            page,
            "debug_after_dopisnica_empty_destination.html",
        )

        raise RuntimeError(
            "Dopisnica activated, but "
            f"#{DESTINATION_SELECT} contains no options."
        )

    print(
        "   Dopisnica selected successfully.",
        flush=True,
    )


# ============================================================
# Avionski prijenos
# ============================================================

def select_air_transport(page):
    print(
        "4. Selecting Avionski prijenos...",
        flush=True,
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
                "   Avionski prijenos already enabled.",
                flush=True,
            )

            return

    except Exception:
        pass

    print(
        "   Clicking Avionski prijenos...",
        flush=True,
    )

    try:
        checkbox.check(
            timeout=CONTROL_TIMEOUT
        )

    except Exception:

        try:
            checkbox.click(
                timeout=CONTROL_TIMEOUT
            )

        except Exception as exc:

            save_debug(
                page,
                "debug_air_transport_failure.html",
            )

            raise RuntimeError(
                "Could not enable Avionski prijenos: "
                f"{exc}"
            )

    # Short wait only.
    safe_network_wait(
        page,
        timeout=3_000,
    )

    wait_briefly(
        page,
        1_000,
    )

    try:
        if not checkbox.is_checked():
            raise RuntimeError(
                "Avionski prijenos checkbox remains unchecked."
            )

    except Exception as exc:

        save_debug(
            page,
            "debug_air_transport_unchecked.html",
        )

        raise RuntimeError(
            f"Could not enable Avionski prijenos: {exc}"
        )

    print(
        "   Avionski prijenos enabled.",
        flush=True,
    )


# ============================================================
# Weight
# ============================================================

def set_weight(page):
    print(
        f"5. Setting weight to {WEIGHT} g...",
        flush=True,
    )

    weight = page.locator(
        f"#{AIR_WEIGHT}"
    )

    if weight.count() == 0:

        raise RuntimeError(
            f"#{AIR_WEIGHT} was not found."
        )

    weight.fill(
        WEIGHT,
        timeout=CONTROL_TIMEOUT,
    )

    # Trigger normal browser events.
    try:
        weight.press("Tab")
    except Exception:
        pass

    wait_briefly(
        page,
        SHORT_WAIT_MS,
    )

    print(
        "   Weight set.",
        flush=True,
    )


# ============================================================
# Destination list
# ============================================================

def get_destinations(page):
    print(
        "6. Reading destination country list...",
        flush=True,
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
        f"   Found {len(destinations)} destination entries.",
        flush=True,
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

    # --------------------------------------------------------
    # Read current selection first.
    # --------------------------------------------------------

    try:
        current = select.input_value()

    except Exception:
        current = ""

    # --------------------------------------------------------
    # Selecting the same country again does not necessarily
    # trigger onchange. That's okay because calculation is
    # explicitly clicked afterward.
    # --------------------------------------------------------

    select.select_option(
        value=code,
        timeout=CONTROL_TIMEOUT,
    )

    if current != code:

        # Give onchange/client-side handlers a short chance.
        wait_briefly(
            page,
            SHORT_WAIT_MS,
        )

    # Do NOT wait for networkidle here.
    #
    # The old implementation could spend up to 15 seconds
    # here for every country.
    wait_briefly(
        page,
        SHORT_WAIT_MS,
    )


# ============================================================
# Calculate button
# ============================================================

def find_calculate_button(page):
    selectors = [
        "#btnMeDoIzracunaj",
        "input[name='btnMeDoIzracunaj']",
        "input[id$='btnMeDoIzracunaj']",
        "button:has-text('Izračunaj')",
        "input[value='Izračunaj']",
    ]

    for selector in selectors:

        try:
            locator = page.locator(selector)

            count = locator.count()

            if count == 0:
                continue

            for i in range(count):

                candidate = locator.nth(i)

                try:
                    if candidate.is_visible():
                        return candidate
                except Exception:
                    continue

        except Exception:
            continue

    return None


def click_calculate(page):
    button = find_calculate_button(page)

    if button is None:

        save_debug(
            page,
            "debug_calculate_button_missing.html",
        )

        raise RuntimeError(
            "Could not find Izračunaj button."
        )

    # --------------------------------------------------------
    # Capture current result text.
    #
    # We use this to detect that the calculator actually
    # changed after the click.
    # --------------------------------------------------------

    try:
        before = get_result_text(page)
    except Exception:
        before = ""

    try:
        button.click(
            timeout=CONTROL_TIMEOUT
        )

    except Exception as exc:

        print(
            f"    Normal calculate click failed: {exc}",
            flush=True,
        )

        try:
            button.evaluate(
                "(element) => element.click()"
            )

        except Exception as js_exc:

            save_debug(
                page,
                "debug_calculate_click_failure.html",
            )

            raise RuntimeError(
                "Could not click Izračunaj: "
                f"{js_exc}"
            )

    # --------------------------------------------------------
    # Do not wait for long networkidle.
    # --------------------------------------------------------

    wait_briefly(
        page,
        CALLBACK_WAIT_MS,
    )

    # Give ASP.NET AJAX another short chance.
    safe_network_wait(
        page,
        timeout=2_000,
    )

    wait_briefly(
        page,
        CALLBACK_WAIT_MS,
    )

    return before


# ============================================================
# Price parsing
# ============================================================

def parse_price(text):
    if not text:
        return None

    text = normalize_text(text)

    # Primary format:
    # Ukupna cijena 1,50 KM
    match = re.search(
        r"Ukupna\s+cijena\s*"
        r"([0-9]+(?:[,.][0-9]+)?)"
        r"\s*KM",
        text,
        flags=re.IGNORECASE,
    )

    if not match:

        # Fallback:
        # 1,50 KM
        match = re.search(
            r"\b([0-9]+(?:[,.][0-9]+)?)"
            r"\s*KM\b",
            text,
            flags=re.IGNORECASE,
        )

    if not match:
        return None

    raw = match.group(1)

    normalized = raw.replace(
        ",",
        ".",
    )

    try:
        value = float(normalized)

    except ValueError:
        return None

    return raw, value


# ============================================================
# Country calculation
# ============================================================

def calculate_country(page, code):
    """
    Calculate one country.

    The function deliberately avoids long network waits.
    """

    select_country(
        page,
        code,
    )

    # --------------------------------------------------------
    # Make sure weight remains 10 g.
    # --------------------------------------------------------

    weight = page.locator(
        f"#{AIR_WEIGHT}"
    )

    if weight.count() > 0:

        try:
            current_weight = weight.input_value()

        except Exception:
            current_weight = ""

        if current_weight != WEIGHT:

            try:
                weight.fill(
                    WEIGHT
                )

                weight.press("Tab")

            except Exception:
                pass

    # --------------------------------------------------------
    # Clear old result if possible.
    #
    # This is best effort. Some ASP.NET labels are replaced
    # only after the callback.
    # --------------------------------------------------------

    before_text = get_result_text(page)

    # --------------------------------------------------------
    # Click calculate.
    # --------------------------------------------------------

    click_calculate(
        page
    )

    # --------------------------------------------------------
    # Poll for a result for a bounded amount of time.
    #
    # This is much safer than repeated networkidle waits.
    # --------------------------------------------------------

    deadline = time.monotonic() + COUNTRY_TIMEOUT / 1000

    last_combined = ""

    while time.monotonic() < deadline:

        error_text = get_error_text(page)
        result_text = get_result_text(page)

        combined = normalize_text(
            f"{error_text} {result_text}"
        )

        last_combined = combined

        # ----------------------------------------------------
        # Suspended
        # ----------------------------------------------------

        if (
            SUSPENDED_MESSAGE.lower()
            in combined.lower()
        ):
            return (
                "SUSPENDED",
                SUSPENDED_MESSAGE,
            )

        # ----------------------------------------------------
        # Price
        # ----------------------------------------------------

        parsed = parse_price(
            combined
        )

        if parsed is not None:

            raw, value = parsed

            price_text = f"{raw} KM"

            if value == 0:

                return (
                    "UNKNOWN",
                    f"Ukupna cijena {price_text}",
                )

            return (
                "AVAILABLE",
                price_text,
            )

        # ----------------------------------------------------
        # Wait a little and poll again.
        # ----------------------------------------------------

        wait_briefly(
            page,
            500,
        )

    # --------------------------------------------------------
    # Timed out.
    # --------------------------------------------------------

    return (
        "UNKNOWN",
        "Cijena nije pronađena nakon "
        f"{COUNTRY_TIMEOUT / 1000:.0f} sekundi",
    )


# ============================================================
# Build complete calculator state
# ============================================================

def build_calculator_state(page):
    """
    Rebuild the complete calculator state.

    This is used for initial setup and recovery.

    IMPORTANT:
    We intentionally do not assume that the destination
    selector exists immediately after the International tab
    callback. Dopisnica is clicked first, then we require the
    destination selector.
    """

    open_calculator(
        page
    )

    select_international_tab(
        page
    )

    select_dopisnica(
        page
    )

    destinations = get_destinations(
        page
    )

    select_air_transport(
        page
    )

    set_weight(
        page
    )

    # Re-read after all controls are configured.
    destinations = get_destinations(
        page
    )

    return destinations


# ============================================================
# Recovery
# ============================================================

def recover_page(browser, old_context, old_page, attempt):
    """
    Close the current broken page/context and create a fresh
    calculator state.
    """

    print(
        f"    Recovery attempt {attempt}/"
        f"{MAX_RECOVERY_ATTEMPTS}...",
        flush=True,
    )

    try:
        old_page.close()
    except Exception:
        pass

    try:
        old_context.close()
    except Exception:
        pass

    context, page = create_page(
        browser
    )

    page.set_default_timeout(
        CONTROL_TIMEOUT
    )

    destinations = build_calculator_state(
        page
    )

    return context, page, destinations


# ============================================================
# Main
# ============================================================

def main():

    print(
        "========================================",
        flush=True,
    )

    print(
        "BH POSTA DOPISNICA MONITOR",
        flush=True,
    )

    print(
        "========================================",
        flush=True,
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

        context = None
        page = None

        try:

            # ------------------------------------------------
            # Build initial state.
            # ------------------------------------------------

            context, page = create_page(
                browser
            )

            destinations = build_calculator_state(
                page
            )

            print()
            print(
                f"Destination list contains "
                f"{len(destinations)} countries.",
                flush=True,
            )

            # ------------------------------------------------
            # Result containers.
            # ------------------------------------------------

            available = []
            suspended = []
            unknown = []
            errors = []

            # ------------------------------------------------
            # Check every destination.
            # ------------------------------------------------

            print()
            print(
                "7. Checking every destination...",
                flush=True,
            )

            print(
                "----------------------------------------",
                flush=True,
            )

            for number, (code, country) in enumerate(
                destinations,
                start=1,
            ):

                print(
                    f"[{number}/{len(destinations)}] "
                    f"{country} ({code})",
                    flush=True,
                )

                completed = False

                # ------------------------------------------------
                # First attempt + limited recovery attempts.
                # ------------------------------------------------

                for attempt in range(
                    MAX_RECOVERY_ATTEMPTS + 1
                ):

                    try:

                        started = time.monotonic()

                        status, detail = calculate_country(
                            page,
                            code,
                        )

                        elapsed = (
                            time.monotonic()
                            - started
                        )

                        # ----------------------------------------
                        # Categorize result.
                        # ----------------------------------------

                        if status == "AVAILABLE":

                            print(
                                f"    -> AVAILABLE "
                                f"({detail}) "
                                f"[{elapsed:.1f}s]",
                                flush=True,
                            )

                            available.append(
                                country
                            )

                        elif status == "SUSPENDED":

                            print(
                                f"    -> SUSPENDED "
                                f"[{elapsed:.1f}s]",
                                flush=True,
                            )

                            suspended.append(
                                country
                            )

                        else:

                            print(
                                f"    -> UNKNOWN "
                                f"({detail}) "
                                f"[{elapsed:.1f}s]",
                                flush=True,
                            )

                            unknown.append(
                                country
                            )

                        completed = True

                        break

                    except Exception as exc:

                        print(
                            f"    -> ERROR on attempt "
                            f"{attempt + 1}: {exc}",
                            flush=True,
                        )

                        # ----------------------------------------
                        # If attempts remain, rebuild the entire
                        # calculator state.
                        # ----------------------------------------

                        if attempt < MAX_RECOVERY_ATTEMPTS:

                            try:

                                (
                                    context,
                                    page,
                                    new_destinations,
                                ) = recover_page(
                                    browser,
                                    context,
                                    page,
                                    attempt + 1,
                                )

                                # The destination list should
                                # normally remain identical.
                                #
                                # If the site changes it during
                                # the run, use the newly returned
                                # list for subsequent operations.
                                destinations = new_destinations

                                # Make sure the current code is
                                # still available.
                                available_codes = {
                                    item[0]
                                    for item in destinations
                                }

                                if code not in available_codes:

                                    raise RuntimeError(
                                        "Country code disappeared "
                                        "after recovery."
                                    )

                            except Exception as recovery_exc:

                                print(
                                    f"    Recovery failed: "
                                    f"{recovery_exc}",
                                    flush=True,
                                )

                                # Continue to the next attempt.
                                continue

                        else:

                            # ------------------------------------
                            # Final failure for this country.
                            # ------------------------------------

                            errors.append(
                                f"{country} | {exc}"
                            )

                if not completed:

                    print(
                        "    -> FINAL ERROR; "
                        "moving to next country.",
                        flush=True,
                    )

                # ------------------------------------------------
                # Gentle delay between countries.
                # ------------------------------------------------

                time.sleep(
                    COUNTRY_PAUSE
                )

            # ------------------------------------------------
            # Write result files.
            # ------------------------------------------------

            print()
            print(
                "8. Writing result files...",
                flush=True,
            )

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

            # ------------------------------------------------
            # Summary.
            # ------------------------------------------------

            print()
            print(
                "========================================",
                flush=True,
            )

            print(
                "Finished.",
                flush=True,
            )

            print(
                "========================================",
                flush=True,
            )

            print(
                f"Destinations: {len(destinations)}",
                flush=True,
            )

            print(
                f"Available:    {len(available)}",
                flush=True,
            )

            print(
                f"Suspended:    {len(suspended)}",
                flush=True,
            )

            print(
                f"Unknown:      {len(unknown)}",
                flush=True,
            )

            print(
                f"Errors:       {len(errors)}",
                flush=True,
            )

            print(
                "========================================",
                flush=True,
            )

            print(
                f"Available: {AVAILABLE_FILE}",
                flush=True,
            )

            print(
                f"Suspended: {SUSPENDED_FILE}",
                flush=True,
            )

            print(
                f"Unknown:   {UNKNOWN_FILE}",
                flush=True,
            )

            print(
                f"Errors:    {ERROR_FILE}",
                flush=True,
            )

        finally:

            if page is not None:

                try:
                    page.close()
                except Exception:
                    pass

            if context is not None:

                try:
                    context.close()
                except Exception:
                    pass

            try:
                browser.close()
            except Exception:
                pass


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":

    try:
        main()

    except KeyboardInterrupt:

        print(
            "Interrupted.",
            file=sys.stderr,
        )

        sys.exit(130)

    except Exception as exc:

        print(
            f"FATAL ERROR: {exc}",
            file=sys.stderr,
        )

        sys.exit(1)
