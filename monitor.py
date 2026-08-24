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
DEBUG_INTERNATIONAL = Path("debug_after_international.html")
DEBUG_DOPISNICA = Path("debug_after_dopisnica.html")
DEBUG_ERROR = Path("debug_error.html")

DESTINATION_SELECT = "ddlMeDoOdrediste"

AIR_CHECKBOX = "chbMeDoAvionski"
AIR_WEIGHT = "tbxMeDoAvioTezina"

DOPISNICA_BUTTON = "ImageButton8"

SUSPENDED_MESSAGE = (
    "Prijem pošiljaka se trenutno ne vrši za odabranu državu"
)

WEIGHT = "10"

# ------------------------------------------------------------
# Important:
#
# Do NOT use page.wait_for_load_state("networkidle") for this
# site. The old ASP.NET/DevExpress application can keep network
# activity alive and make GitHub Actions wait indefinitely.
# ------------------------------------------------------------

SHORT_WAIT = 300
CALLBACK_WAIT = 1000
POSTBACK_WAIT = 1500

# Maximum amount of time one country is allowed to consume.
COUNTRY_TIMEOUT_MS = 12000

# Overall safety limit for the monitoring operation.
MAX_RUNTIME_SECONDS = 12 * 60


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


def safe_wait(page, milliseconds):
    try:
        page.wait_for_timeout(milliseconds)
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


def dopisnica_exists(page):
    selectors = [
        f"#{DOPISNICA_BUTTON}",
        f"[name='{DOPISNICA_BUTTON}']",
        f"[id$='{DOPISNICA_BUTTON}']",
        "img[src*='Dopisnica']",
    ]

    for selector in selectors:
        try:
            if page.locator(selector).count() > 0:
                return True
        except Exception:
            pass

    return False


def get_body_text(page):
    try:
        return normalize_text(
            page.locator("body").inner_text(
                timeout=3000
            )
        )
    except Exception:
        return ""


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
                    timeout=2000
                )
            )

            if text:
                return text

        except Exception:
            pass

    return ""


def get_result_text(page):
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
                    timeout=2000
                )
            )

            if text:
                return text

        except Exception:
            pass

    return get_body_text(page)


# ============================================================
# Waiting for the actual browser DOM
# ============================================================

def wait_for_destination(page, timeout_ms=10000):
    """
    Wait for the actual rendered destination selector.

    IMPORTANT:
    We deliberately do NOT assume that the selector must appear
    immediately after the DevExpress tab callback.
    """

    deadline = time.monotonic() + (
        timeout_ms / 1000.0
    )

    while time.monotonic() < deadline:

        if selector_exists(page):
            return True

        safe_wait(page, SHORT_WAIT)

    return selector_exists(page)


def wait_for_dopisnica(page, timeout_ms=8000):
    deadline = time.monotonic() + (
        timeout_ms / 1000.0
    )

    while time.monotonic() < deadline:

        if dopisnica_exists(page):
            return True

        safe_wait(page, SHORT_WAIT)

    return dopisnica_exists(page)


# ============================================================
# International tab
# ============================================================

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

    # --------------------------------------------------------
    # First try the actual text.
    # --------------------------------------------------------

    clicked = False

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
                        timeout=5000
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
    #
    # The page previously showed:
    #
    #   tabs: [['',,,,,],['',,,,,]]
    #
    # so the second tab is the important target.
    # --------------------------------------------------------

    if not clicked:

        print(
            "   Text click failed; trying DevExpress "
            "tab elements...",
            flush=True,
        )

        selectors = [
            "#ASPxTabControl1 .dxtc-tab",
            "#ASPxTabControl1 .dxtc-tabLink",
            "#ASPxTabControl1 td[id*='T1']",
            "#ASPxTabControl1 [id*='T1']",
            "#ASPxTabControl1 td",
        ]

        for selector in selectors:

            try:
                locator = page.locator(
                    selector
                )

                count = locator.count()

                print(
                    f"   {selector}: {count}",
                    flush=True,
                )

                if count >= 2:

                    locator.nth(1).click(
                        timeout=5000
                    )

                    clicked = True
                    break

            except Exception:
                continue

    # --------------------------------------------------------
    # Last fallback: invoke the DevExpress client API.
    # --------------------------------------------------------

    if not clicked:

        print(
            "   Trying DevExpress client-side callback...",
            flush=True,
        )

        try:
            result = page.evaluate(
                """
                () => {
                    const control =
                        window.ASPxClientControl
                            ? ASPxClientControl.GetControlCollection()
                                .GetByName('ASPxTabControl1')
                            : null;

                    if (!control) {
                        return false;
                    }

                    if (typeof control.SetActiveTab === 'function') {
                        control.SetActiveTab(1);
                        return true;
                    }

                    if (typeof control.SetActiveTabIndex === 'function') {
                        control.SetActiveTabIndex(1);
                        return true;
                    }

                    return false;
                }
                """
            )

            clicked = bool(result)

        except Exception:
            clicked = False

    if not clicked:
        save_debug(
            page,
            DEBUG_INTERNATIONAL,
        )

        raise RuntimeError(
            "Could not activate Međunarodni promet."
        )

    print(
        "   Međunarodni promet click issued.",
        flush=True,
    )

    # --------------------------------------------------------
    # DO NOT use networkidle here.
    #
    # Wait for actual DOM changes instead.
    # --------------------------------------------------------

    safe_wait(
        page,
        CALLBACK_WAIT,
    )

    # --------------------------------------------------------
    # Important:
    #
    # We no longer require ddlMeDoOdrediste to appear here.
    # We only verify that the tab has had time to update and
    # then proceed to Dopisnica.
    # --------------------------------------------------------

    if selector_exists(page):

        print(
            "   Destination selector already present.",
            flush=True,
        )

    elif dopisnica_exists(page):

        print(
            "   Dopisnica control is present; "
            "continuing without requiring destination selector.",
            flush=True,
        )

    else:

        print(
            "   Destination selector not yet present; "
            "waiting for Dopisnica/content...",
            flush=True,
        )

        wait_for_dopisnica(
            page,
            timeout_ms=5000,
        )

    print(
        "   Međunarodni promet request processed.",
        flush=True,
    )


# ============================================================
# Dopisnica
# ============================================================

def select_dopisnica(page):
    print(
        "3. Selecting Dopisnica...",
        flush=True,
    )

    # --------------------------------------------------------
    # We intentionally DO NOT require the destination selector
    # before clicking Dopisnica.
    #
    # This was the failure in the previous implementation.
    # --------------------------------------------------------

    active_selectors = [
        "img[src*='Dopisnica_Aktivna']",
        "img[src*='Dopisnica'][src*='Aktivna']",
    ]

    for selector in active_selectors:

        try:
            if page.locator(selector).count() > 0:

                print(
                    "   Dopisnica is already active.",
                    flush=True,
                )

                # The selector may already exist or may appear
                # shortly after the active tab is rendered.
                if wait_for_destination(
                    page,
                    timeout_ms=5000,
                ):
                    return

                break

        except Exception:
            pass

    selectors = [
        f"#{DOPISNICA_BUTTON}",
        f"input#{DOPISNICA_BUTTON}",
        f"input[name='{DOPISNICA_BUTTON}']",
        f"input[id$='{DOPISNICA_BUTTON}']",
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
                        f"   Clicking {selector}",
                        flush=True,
                    )

                    candidate.click(
                        timeout=5000
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
            "trying DOM click...",
            flush=True,
        )

        try:
            clicked = page.evaluate(
                """
                () => {
                    const candidates = [
                        document.getElementById('ImageButton8'),
                        document.querySelector(
                            "input[name='ImageButton8']"
                        ),
                        document.querySelector(
                            "input[id$='ImageButton8']"
                        )
                    ];

                    for (const el of candidates) {
                        if (el) {
                            el.click();
                            return true;
                        }
                    }

                    return false;
                }
                """
            )

            clicked = bool(clicked)

        except Exception:
            clicked = False

    if not clicked:

        save_debug(
            page,
            DEBUG_DOPISNICA,
        )

        raise RuntimeError(
            "Could not click Dopisnica."
        )

    print(
        "   Dopisnica click issued.",
        flush=True,
    )

    # --------------------------------------------------------
    # Wait for the actual selector, NOT networkidle.
    # --------------------------------------------------------

    if not wait_for_destination(
        page,
        timeout_ms=10000,
    ):

        save_debug(
            page,
            DEBUG_DOPISNICA,
        )

        raise RuntimeError(
            "Dopisnica was clicked, but "
            f"#{DESTINATION_SELECT} did not appear."
        )

    print(
        "   Dopisnica activated successfully.",
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
                "   Already enabled.",
                flush=True,
            )

            return

    except Exception:
        pass

    try:

        checkbox.check(
            timeout=5000
        )

    except Exception:

        checkbox.click(
            timeout=5000
        )

    # --------------------------------------------------------
    # ASP.NET may process this as a postback.
    # Do not wait for networkidle.
    # --------------------------------------------------------

    safe_wait(
        page,
        POSTBACK_WAIT,
    )

    try:
        if not checkbox.is_checked():

            # One more click attempt.
            checkbox.click(
                timeout=3000
            )

            safe_wait(
                page,
                POSTBACK_WAIT,
            )

    except Exception:
        pass

    try:
        if not checkbox.is_checked():
            raise RuntimeError(
                "Avionski prijenos remained unchecked."
            )
    except Exception as exc:
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
        timeout=5000,
    )

    # Trigger normal browser events.
    weight.press("Tab")

    safe_wait(
        page,
        SHORT_WAIT,
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

        if not wait_for_destination(
            page,
            timeout_ms=5000,
        ):

            raise RuntimeError(
                f"#{DESTINATION_SELECT} was not found."
            )

    select = page.locator(
        f"select#{DESTINATION_SELECT}"
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
        f"destination entries.",
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
    # select_option triggers the browser change event.
    # --------------------------------------------------------

    select.select_option(
        value=code,
        timeout=5000,
    )

    # Give ASP.NET onchange/postback a bounded amount of time.
    safe_wait(
        page,
        POSTBACK_WAIT,
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

                    safe_wait(
                        page,
                        POSTBACK_WAIT,
                    )

                    return

                except Exception:
                    continue

        except Exception:
            continue

    raise RuntimeError(
        "Could not find or click Izračunaj."
    )


# ============================================================
# Price extraction
# ============================================================

def extract_price(text):
    if not text:
        return None

    text = normalize_text(text)

    patterns = [
        (
            r"Ukupna\s+cijena\s*"
            r"([0-9]+(?:[,.][0-9]+)?)"
            r"\s*\*?\s*KM"
        ),
        (
            r"\b([0-9]+(?:[,.][0-9]+)?)"
            r"\s*\*?\s*KM\b"
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

        raw = match.group(1)

        try:
            numeric = float(
                raw.replace(",", ".")
            )
        except ValueError:
            numeric = None

        return (
            f"{raw} KM",
            numeric,
        )

    return None


# ============================================================
# Calculate one country
# ============================================================

def calculate_country(page, code):
    """
    Calculate one country with a strict timeout.

    Returns:
        ("AVAILABLE", "10 KM")
        ("SUSPENDED", "...")
        ("UNKNOWN", "...")
    """

    started = time.monotonic()

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
                weight.fill(
                    WEIGHT,
                    timeout=3000,
                )

        except Exception:
            pass

    if (
        time.monotonic() - started
        > COUNTRY_TIMEOUT_MS / 1000
    ):
        raise RuntimeError(
            "Country processing timeout before calculation."
        )

    click_calculate(
        page
    )

    # --------------------------------------------------------
    # Give result a short opportunity to appear.
    # --------------------------------------------------------

    deadline = (
        time.monotonic()
        + 5.0
    )

    result_text = ""
    error_text = ""

    while time.monotonic() < deadline:

        result_text = get_result_text(
            page
        )

        error_text = get_error_text(
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

        extracted = extract_price(
            combined
        )

        if extracted is not None:

            price_text, price_value = extracted

            if price_value == 0:

                return (
                    "UNKNOWN",
                    f"Ukupna cijena {price_text}",
                )

            return (
                "AVAILABLE",
                price_text,
            )

        safe_wait(
            page,
            250,
        )

    # --------------------------------------------------------
    # Final inspection.
    # --------------------------------------------------------

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

    extracted = extract_price(
        combined
    )

    if extracted is not None:

        price_text, price_value = extracted

        if price_value == 0:
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
# Rebuild calculator state
# ============================================================

def rebuild_state(page):
    """
    Recover from a broken ASP.NET callback.

    This deliberately rebuilds the complete UI state rather
    than trying to continue with a potentially corrupted page.
    """

    print(
        "   Recovering browser state...",
        flush=True,
    )

    page.goto(
        URL,
        wait_until="domcontentloaded",
        timeout=30000,
    )

    safe_wait(
        page,
        1000,
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

    print(
        "   Browser state recovered.",
        flush=True,
    )


# ============================================================
# Main
# ============================================================

def main():

    program_started = time.monotonic()

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

        # ----------------------------------------------------
        # Keep all Playwright operations bounded.
        # ----------------------------------------------------

        page.set_default_timeout(
            8000
        )

        try:

            # =================================================
            # 1. Open calculator
            # =================================================

            page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=45000,
            )

            safe_wait(
                page,
                1000,
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
            # 4. Country list
            # =================================================

            destinations = get_destinations(
                page
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

            # Re-read because an ASP.NET callback can replace
            # the select element.
            destinations = get_destinations(
                page
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

            available = []
            suspended = []
            unknown = []
            errors = []

            for number, (code, country) in enumerate(
                destinations,
                start=1,
            ):

                # ------------------------------------------------
                # Global runtime protection.
                # ------------------------------------------------

                elapsed = (
                    time.monotonic()
                    - program_started
                )

                if elapsed > MAX_RUNTIME_SECONDS:

                    print(
                        "Maximum runtime reached. "
                        "Stopping country checks.",
                        flush=True,
                    )

                    errors.append(
                        f"{country} | "
                        "Monitoring runtime limit reached"
                    )

                    # Mark remaining countries as errors.
                    for remaining_code, remaining_country in (
                        destinations[number:]
                    ):
                        errors.append(
                            f"{remaining_country} | "
                            "Not checked because maximum runtime "
                            "was reached"
                        )

                    break

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

                except Exception as exc:

                    print(
                        f"    -> ERROR: {exc}",
                        flush=True,
                    )

                    errors.append(
                        f"{country} | {exc}"
                    )

                    # ------------------------------------------------
                    # Try one recovery.
                    #
                    # We do NOT repeatedly retry a country forever.
                    # ------------------------------------------------

                    try:

                        rebuild_state(
                            page
                        )

                    except Exception as recovery_exc:

                        print(
                            "    Recovery failed: "
                            f"{recovery_exc}",
                            flush=True,
                        )

                        # There is no reason to keep hammering a
                        # broken page.
                        break

                # Small delay to avoid hammering the server.
                time.sleep(
                    0.3
                )

            # =================================================
            # 8. Write output
            # =================================================

            print()
            print(
                "8. Writing output files...",
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

        except Exception:

            # Save the final page when something unexpected
            # happens. This is extremely useful in Actions.
            save_debug(
                page,
                DEBUG_ERROR,
            )

            raise

        finally:

            context.close()
            browser.close()


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
