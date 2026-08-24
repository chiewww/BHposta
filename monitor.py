import re
import sys
import time
from pathlib import Path

from playwright.sync_api import (
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)


# ============================================================
# BH POSTA DOPISNICA MONITOR
#
# Purpose:
#   Check international "Dopisnica" availability/prices
#   for every destination at 10 g with air transport.
#
# Designed for:
#   GitHub Actions
#   Old ASP.NET + ASP.NET AJAX + DevExpress
#
# Important:
#   We intentionally DO NOT use networkidle.
#   We intentionally DO NOT require the destination selector
#   immediately after activating "Međunarodni promet".
# ============================================================


# ============================================================
# Configuration
# ============================================================

URL = (
    "https://bhpwebout.posta.ba/"
    "KalkulatorCijena_WEB_app/Bos/Default.aspx"
)

DESTINATION_SELECT = "ddlMeDoOdrediste"
AIR_CHECKBOX = "chbMeDoAvionski"
AIR_WEIGHT = "tbxMeDoAvioTezina"
DOPISNICA_BUTTON = "ImageButton8"

WEIGHT = "10"

SUSPENDED_MESSAGE = (
    "Prijem pošiljaka se trenutno ne vrši za odabranu državu"
)

AVAILABLE_FILE = Path("available_countries.txt")
SUSPENDED_FILE = Path("suspended_countries.txt")
UNKNOWN_FILE = Path("unknown_countries.txt")
ERROR_FILE = Path("error_countries.txt")

DEBUG_ORIGINAL = Path("debug_original_page.html")
DEBUG_FAILURE = Path("debug_failure.html")

# ------------------------------------------------------------
# Runtime limits.
#
# These are intentionally conservative for GitHub Actions.
# ------------------------------------------------------------

MAX_RUNTIME_SECONDS = 180

PAGE_LOAD_TIMEOUT = 30000
ACTION_TIMEOUT = 5000

# How long to wait for a DOM element to appear.
DOM_WAIT_SECONDS = 8

# How long to wait after an ASP.NET callback.
CALLBACK_WAIT_MS = 700

# Small delay between countries.
COUNTRY_DELAY = 0.15


# ============================================================
# Utility
# ============================================================

def normalize_text(value):
    if value is None:
        return ""

    value = str(value)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


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


def save_debug(page, path):
    try:
        path.write_text(
            page.content(),
            encoding="utf-8",
        )

        print(
            f"DEBUG: Saved {path}",
            flush=True,
        )

    except Exception as exc:
        print(
            f"DEBUG: Could not save {path}: {exc}",
            flush=True,
        )


def wait_ms(page, milliseconds):
    try:
        page.wait_for_timeout(
            milliseconds
        )
    except Exception:
        pass


# ============================================================
# Runtime guard
# ============================================================

class RuntimeLimit(Exception):
    pass


def check_runtime(started):
    elapsed = time.monotonic() - started

    if elapsed >= MAX_RUNTIME_SECONDS:
        raise RuntimeLimit(
            "Maximum monitor runtime reached."
        )


# ============================================================
# DOM helpers
# ============================================================

def destination_selector(page):
    return page.locator(
        f"select#{DESTINATION_SELECT}"
    )


def destination_exists(page):
    try:
        return (
            destination_selector(page).count()
            > 0
        )
    except Exception:
        return False


def get_body_text(page):
    try:
        return normalize_text(
            page.locator(
                "body"
            ).inner_text(
                timeout=2000
            )
        )
    except Exception:
        return ""


def get_element_text(page, selectors):
    for selector in selectors:

        try:
            locator = page.locator(
                selector
            )

            if locator.count() == 0:
                continue

            text = normalize_text(
                locator.first.inner_text(
                    timeout=1500
                )
            )

            if text:
                return text

        except Exception:
            pass

    return ""


def get_error_text(page):
    return get_element_text(
        page,
        [
            "#lblMeObPiPoruka",
            "[id$='lblMeObPiPoruka']",
        ],
    )


def get_result_text(page):
    text = get_element_text(
        page,
        [
            "#lblRezultat",
            "[id$='lblRezultat']",
        ],
    )

    if text:
        return text

    return get_body_text(page)


# ============================================================
# Wait for actual DOM
# ============================================================

def wait_for_destination(page, seconds=DOM_WAIT_SECONDS):
    deadline = (
        time.monotonic()
        + seconds
    )

    while time.monotonic() < deadline:

        if destination_exists(page):
            return True

        wait_ms(
            page,
            250,
        )

    return destination_exists(page)


# ============================================================
# International tab
# ============================================================

def click_international_tab(page):
    print(
        "2. Selecting Međunarodni promet...",
        flush=True,
    )

    tab = page.locator(
        "#ASPxTabControl1"
    )

    if tab.count() == 0:
        raise RuntimeError(
            "ASPxTabControl1 was not found."
        )

    print(
        "   ASPxTabControl1 found.",
        flush=True,
    )

    # --------------------------------------------------------
    # Preferred method: visible text.
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

            for index in range(count):

                candidate = locator.nth(
                    index
                )

                try:
                    if not candidate.is_visible():
                        continue
                except Exception:
                    continue

                try:

                    print(
                        f"   Clicking tab text: {name}",
                        flush=True,
                    )

                    candidate.click(
                        timeout=ACTION_TIMEOUT
                    )

                    wait_ms(
                        page,
                        CALLBACK_WAIT_MS,
                    )

                    return

                except Exception:
                    continue

        except Exception:
            continue

    # --------------------------------------------------------
    # DevExpress fallback.
    # --------------------------------------------------------

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

                print(
                    f"   Clicking DevExpress second tab: "
                    f"{selector}",
                    flush=True,
                )

                locator.nth(1).click(
                    timeout=ACTION_TIMEOUT
                )

                wait_ms(
                    page,
                    CALLBACK_WAIT_MS,
                )

                return

        except Exception:
            continue

    # --------------------------------------------------------
    # JavaScript fallback.
    # --------------------------------------------------------

    try:

        result = page.evaluate(
            """
            () => {
                const collection =
                    window.ASPxClientControl &&
                    ASPxClientControl
                        .GetControlCollection();

                if (!collection) {
                    return false;
                }

                const control =
                    collection.GetByName(
                        'ASPxTabControl1'
                    );

                if (!control) {
                    return false;
                }

                if (
                    typeof control.SetActiveTab ===
                    'function'
                ) {
                    control.SetActiveTab(1);
                    return true;
                }

                return false;
            }
            """
        )

        if result:

            wait_ms(
                page,
                CALLBACK_WAIT_MS,
            )

            return

    except Exception:
        pass

    save_debug(
        page,
        DEBUG_FAILURE,
    )

    raise RuntimeError(
        "Could not activate Međunarodni promet."
    )


# ============================================================
# Dopisnica
# ============================================================

def click_dopisnica(page):
    print(
        "3. Selecting Dopisnica...",
        flush=True,
    )

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # Do NOT require ddlMeDoOdrediste here.
    #
    # The site can populate the calculator only after
    # Dopisnica is activated.
    # --------------------------------------------------------

    selectors = [
        f"#{DOPISNICA_BUTTON}",
        f"input#{DOPISNICA_BUTTON}",
        f"input[name='{DOPISNICA_BUTTON}']",
        f"input[id$='{DOPISNICA_BUTTON}']",
        "img[src*='Dopisnica']",
    ]

    for selector in selectors:

        try:

            locator = page.locator(
                selector
            )

            count = locator.count()

            if count == 0:
                continue

            for index in range(count):

                candidate = locator.nth(
                    index
                )

                try:
                    if not candidate.is_visible():
                        continue
                except Exception:
                    pass

                try:

                    print(
                        f"   Clicking {selector}",
                        flush=True,
                    )

                    candidate.click(
                        timeout=ACTION_TIMEOUT
                    )

                    wait_ms(
                        page,
                        CALLBACK_WAIT_MS,
                    )

                    return

                except Exception:
                    continue

        except Exception:
            continue

    # --------------------------------------------------------
    # JavaScript fallback.
    # --------------------------------------------------------

    try:

        result = page.evaluate(
            """
            () => {
                const ids = [
                    'ImageButton8'
                ];

                for (const id of ids) {
                    const el =
                        document.getElementById(id);

                    if (el) {
                        el.click();
                        return true;
                    }
                }

                const el =
                    document.querySelector(
                        "input[name='ImageButton8']"
                    );

                if (el) {
                    el.click();
                    return true;
                }

                return false;
            }
            """
        )

        if result:

            wait_ms(
                page,
                CALLBACK_WAIT_MS,
            )

            return

    except Exception:
        pass

    save_debug(
        page,
        DEBUG_FAILURE,
    )

    raise RuntimeError(
        "Could not click Dopisnica."
    )


# ============================================================
# Initialize calculator
# ============================================================

def initialize_calculator(page):
    """
    Build the calculator state exactly once.
    """

    # --------------------------------------------------------
    # International tab
    # --------------------------------------------------------

    click_international_tab(
        page
    )

    # --------------------------------------------------------
    # Dopisnica
    # --------------------------------------------------------

    click_dopisnica(
        page
    )

    # --------------------------------------------------------
    # Destination selector
    #
    # THIS is where it must exist.
    # --------------------------------------------------------

    if not wait_for_destination(
        page,
        seconds=DOM_WAIT_SECONDS,
    ):
        raise RuntimeError(
            "Dopisnica was activated, but "
            f"#{DESTINATION_SELECT} did not appear."
        )

    print(
        "   Destination selector is available.",
        flush=True,
    )

    # --------------------------------------------------------
    # Air transport
    # --------------------------------------------------------

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
        already_checked = checkbox.is_checked()
    except Exception:
        already_checked = False

    if not already_checked:

        try:
            checkbox.check(
                timeout=ACTION_TIMEOUT
            )

        except Exception:

            checkbox.click(
                timeout=ACTION_TIMEOUT
            )

        wait_ms(
            page,
            CALLBACK_WAIT_MS,
        )

    print(
        "   Avionski prijenos enabled.",
        flush=True,
    )

    # --------------------------------------------------------
    # Weight
    # --------------------------------------------------------

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
        timeout=ACTION_TIMEOUT,
    )

    weight.press(
        "Tab"
    )

    wait_ms(
        page,
        300,
    )

    print(
        "   Weight set.",
        flush=True,
    )


# ============================================================
# Country list
# ============================================================

def get_destinations(page):
    select = destination_selector(
        page
    )

    if select.count() == 0:
        raise RuntimeError(
            f"#{DESTINATION_SELECT} was not found."
        )

    options = select.locator(
        "option"
    )

    destinations = []

    for index in range(
        options.count()
    ):

        option = options.nth(
            index
        )

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
            "Destination selector contains no countries."
        )

    return destinations


# ============================================================
# Country selection
# ============================================================

def select_country(page, code):
    select = destination_selector(
        page
    )

    if select.count() == 0:
        raise RuntimeError(
            "Destination selector disappeared."
        )

    select.select_option(
        value=code,
        timeout=ACTION_TIMEOUT,
    )

    # Small bounded wait for ASP.NET onchange.
    wait_ms(
        page,
        CALLBACK_WAIT_MS,
    )


# ============================================================
# Calculate button
# ============================================================

def click_calculate(page):
    selectors = [
        "#btnMeDoIzracunaj",
        "input[name='btnMeDoIzracunaj']",
        "input[id$='btnMeDoIzracunaj']",
        "input[value='Izračunaj']",
        "button:has-text('Izračunaj')",
    ]

    for selector in selectors:

        try:

            locator = page.locator(
                selector
            )

            count = locator.count()

            if count == 0:
                continue

            for index in range(count):

                candidate = locator.nth(
                    index
                )

                try:
                    if not candidate.is_visible():
                        continue
                except Exception:
                    pass

                try:

                    candidate.click(
                        timeout=ACTION_TIMEOUT
                    )

                    wait_ms(
                        page,
                        CALLBACK_WAIT_MS,
                    )

                    return True

                except Exception:
                    continue

        except Exception:
            continue

    return False


# ============================================================
# Price parsing
# ============================================================

def extract_price(text):
    text = normalize_text(
        text
    )

    patterns = [
        (
            r"Ukupna\s+cijena\s*"
            r"([0-9]+(?:[,.][0-9]+)?)"
            r"\s*\*?\s*KM"
        ),
        (
            r"\b"
            r"([0-9]+(?:[,.][0-9]+)?)"
            r"\s*\*?\s*KM"
        ),
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        if not match:
            continue

        raw = match.group(
            1
        )

        try:

            numeric = float(
                raw.replace(
                    ",",
                    ".",
                )
            )

        except ValueError:

            numeric = None

        return (
            f"{raw} KM",
            numeric,
        )

    return None


# ============================================================
# One country
# ============================================================

def check_country(page, code):
    """
    Returns:

        AVAILABLE
        SUSPENDED
        UNKNOWN
    """

    select_country(
        page,
        code,
    )

    # --------------------------------------------------------
    # Ensure weight remains 10 g.
    # --------------------------------------------------------

    weight = page.locator(
        f"#{AIR_WEIGHT}"
    )

    if weight.count() > 0:

        try:

            if weight.input_value() != WEIGHT:

                weight.fill(
                    WEIGHT,
                    timeout=2000,
                )

                weight.press(
                    "Tab"
                )

        except Exception:
            pass

    # --------------------------------------------------------
    # Calculate.
    # --------------------------------------------------------

    if not click_calculate(
        page
    ):
        return (
            "UNKNOWN",
            "Izračunaj button not found",
        )

    # --------------------------------------------------------
    # Wait only for the result.
    #
    # Maximum: 4 seconds.
    # --------------------------------------------------------

    deadline = (
        time.monotonic()
        + 4.0
    )

    while time.monotonic() < deadline:

        error_text = get_error_text(
            page
        )

        result_text = get_result_text(
            page
        )

        combined = normalize_text(
            f"{error_text} {result_text}"
        )

        if (
            SUSPENDED_MESSAGE.lower()
            in combined.lower()
        ):

            return (
                "SUSPENDED",
                SUSPENDED_MESSAGE,
            )

        price = extract_price(
            combined
        )

        if price is not None:

            price_text, numeric = price

            if numeric == 0:

                return (
                    "UNKNOWN",
                    f"Ukupna cijena {price_text}",
                )

            return (
                "AVAILABLE",
                price_text,
            )

        wait_ms(
            page,
            200,
        )

    # --------------------------------------------------------
    # Final result inspection.
    # --------------------------------------------------------

    combined = normalize_text(
        f"{get_error_text(page)} "
        f"{get_result_text(page)}"
    )

    if (
        SUSPENDED_MESSAGE.lower()
        in combined.lower()
    ):
        return (
            "SUSPENDED",
            SUSPENDED_MESSAGE,
        )

    price = extract_price(
        combined
    )

    if price is not None:

        price_text, numeric = price

        if numeric == 0:

            return (
                "UNKNOWN",
                f"Ukupna cijena {price_text}",
            )

        return (
            "AVAILABLE",
            price_text,
        )

    return (
        "UNKNOWN",
        "Cijena nije pronađena",
    )


# ============================================================
# Main
# ============================================================

def main():
    started = time.monotonic()

    print(
        "Opening calculator...",
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
            ACTION_TIMEOUT
        )

        available = []
        suspended = []
        unknown = []
        errors = []

        try:

            # =================================================
            # 1. Open calculator
            # =================================================

            page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=PAGE_LOAD_TIMEOUT,
            )

            wait_ms(
                page,
                800,
            )

            print(
                f"Initial page received: "
                f"{len(page.content()):,} bytes",
                flush=True,
            )

            save_debug(
                page,
                DEBUG_ORIGINAL,
            )

            # =================================================
            # 2-5. Build calculator
            # =================================================

            initialize_calculator(
                page
            )

            # =================================================
            # 6. Read destinations
            # =================================================

            print(
                "6. Reading destination country list...",
                flush=True,
            )

            destinations = get_destinations(
                page
            )

            print(
                f"   Found {len(destinations)} "
                f"destination entries.",
                flush=True,
            )

            print()
            print(
                f"Destination list contains "
                f"{len(destinations)} countries.",
                flush=True,
            )

            # =================================================
            # 7. Check countries
            # =================================================

            print()
            print(
                "7. Checking every destination...",
                flush=True,
            )

            for number, (code, country) in enumerate(
                destinations,
                start=1,
            ):

                # ------------------------------------------------
                # Global 3-minute limit.
                # ------------------------------------------------

                check_runtime(
                    started
                )

                print(
                    f"[{number}/{len(destinations)}] "
                    f"{country} ({code})",
                    flush=True,
                )

                try:

                    status, detail = check_country(
                        page,
                        code,
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

                except RuntimeLimit:
                    raise

                except Exception as exc:

                    print(
                        f"    -> ERROR: {exc}",
                        flush=True,
                    )

                    errors.append(
                        f"{country} | {exc}"
                    )

                # ------------------------------------------------
                # Do not hammer BH Posta.
                # ------------------------------------------------

                wait_ms(
                    page,
                    int(
                        COUNTRY_DELAY * 1000
                    ),
                )

            # =================================================
            # 8. Write results
            # =================================================

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

            # =================================================
            # 9. Summary
            # =================================================

            elapsed = (
                time.monotonic()
                - started
            )

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
                f"Runtime:      {elapsed:.1f} seconds",
                flush=True,
            )
            print(
                "========================================",
                flush=True,
            )

        except RuntimeLimit as exc:

            print(
                f"RUNTIME LIMIT: {exc}",
                file=sys.stderr,
                flush=True,
            )

            # ------------------------------------------------
            # Save whatever we have collected so far.
            # ------------------------------------------------

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

            save_debug(
                page,
                DEBUG_FAILURE,
            )

            raise

        except Exception:

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

            save_debug(
                page,
                DEBUG_FAILURE,
            )

            raise

        finally:

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
