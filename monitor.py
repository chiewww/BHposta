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
MAX_RUNTIME_SECONDS = 22 * 60


# ============================================================
# Postcrossing country numbers
# ============================================================

POSTCROSSING_NUMBERS = {
    "Afghanistan": 1,
    "Åland Islands": 2,
    "Albania": 3,
    "Algeria": 4,
    "American Samoa": 5,
    "Andorra": 6,
    "Angola": 7,
    "Anguilla": 8,
    "Antarctica": 9,
    "Antigua & Barbuda": 10,
    "Argentina": 11,
    "Armenia": 12,
    "Aruba": 13,
    "Australia": 14,
    "Austria": 15,
    "Azerbaijan": 16,
    "Bahamas": 17,
    "Bahrain": 18,
    "Bangladesh": 19,
    "Barbados": 20,
    "Belarus": 21,
    "Belgium": 22,
    "Belize": 23,
    "Benin": 24,
    "Bermuda": 25,
    "Bhutan": 26,
    "Bolivia": 27,
    "Bonaire, Sint Eustatius and Saba": 28,
    "Bosnia-Herzegovina": 29,
    "Botswana": 30,
    "Brazil": 31,
    "British Indian Ocean Territory": 32,
    "Brunei": 33,
    "Bulgaria": 34,
    "Burkina Faso": 35,
    "Burundi": 36,
    "Cabo Verde": 37,
    "Cambodia": 38,
    "Cameroon": 39,
    "Canada": 40,
    "Cayman Islands": 41,
    "Central African Republic": 42,
    "Chad": 43,
    "Chile": 44,
    "China": 45,
    "Christmas Island": 46,
    "Cocos Islands": 47,
    "Colombia": 48,
    "Comoros": 49,
    "Congo": 50,
    "Dem. Rep. Of Congo": 51,
    "Cook Islands": 52,
    "Costa Rica": 53,
    "Côte d'Ivoire": 54,
    "Croatia": 55,
    "Cuba": 56,
    "Curaçao": 57,
    "Cyprus": 58,
    "Czechia": 59,
    "Denmark": 60,
    "Djibouti": 61,
    "Dominica": 62,
    "Dominican Republic": 63,
    "Ecuador": 64,
    "Egypt": 65,
    "El Salvador": 66,
    "Equatorial Guinea": 67,
    "Eritrea": 68,
    "Estonia": 69,
    "Eswatini /Swaziland": 70,
    "Ethiopia": 71,
    "Falkland Islands /Malvinas": 72,
    "Faroe Islands": 73,
    "Fiji": 74,
    "Finland": 75,
    "France": 76,
    "French Guiana": 77,
    "French Polynesia": 78,
    "French Southern Territories": 79,
    "Gabon": 80,
    "Gambia": 81,
    "Georgia": 82,
    "Germany": 83,
    "Ghana": 84,
    "Gibraltar": 85,
    "Greece": 86,
    "Greenland": 87,
    "Grenada": 88,
    "Guadeloupe": 89,
    "Guam": 90,
    "Guatemala": 91,
    "Guernsey": 92,
    "Guinea": 93,
    "Guinea-Bissau": 94,
    "Guyana": 95,
    "Haiti": 96,
    "Honduras": 97,
    "Hong Kong": 98,
    "Hungary": 99,
    "Iceland": 100,
    "India": 101,
    "Indonesia": 102,
    "Iran": 103,
    "Iraq": 104,
    "Ireland": 105,
    "Isle of Man": 106,
    "Israel": 107,
    "Italy": 108,
    "Jamaica": 109,
    "Japan": 110,
    "Jersey": 111,
    "Jordan": 112,
    "Kazakhstan": 113,
    "Kenya": 114,
    "Kiribati": 115,
    "Korea(North)": 116,
    "Korea(South)": 117,
    "Kosovo": 118,
    "Kuwait": 119,
    "Kyrgyzstan": 120,
    "Laos": 121,
    "Latvia": 122,
    "Lebanon": 123,
    "Lesotho": 124,
    "Liberia": 125,
    "Libya": 126,
    "Liechtenstein": 127,
    "Lithuania": 128,
    "Luxembourg": 129,
    "Macao": 130,
    "Madagascar": 131,
    "Malawi": 132,
    "Malaysia": 133,
    "Maldives": 134,
    "Mali": 135,
    "Malta": 136,
    "Marshall Islands": 137,
    "Martinique": 138,
    "Mauritania": 139,
    "Mauritius": 140,
    "Mayotte": 141,
    "Mexico": 142,
    "Micronesia": 143,
    "Moldova": 144,
    "Monaco": 145,
    "Mongolia": 146,
    "Montenegro": 147,
    "Montserrat": 148,
    "Morocco": 149,
    "Mozambique": 150,
    "Myanmar": 151,
    "Namibia": 152,
    "Nauru / Naoero": 153,
    "Nepal": 154,
    "Netherlands": 155,
    "New Caledonia": 156,
    "New Zealand": 157,
    "Nicaragua": 158,
    "Niger": 159,
    "Nigeria": 160,
    "Niue": 161,
    "Norfolk Island": 162,
    "Northern Mariana Islands": 163,
    "North Macedonia": 164,
    "Norway": 165,
    "Oman": 166,
    "Pakistan": 167,
    "Palau": 168,
    "Palestine": 169,
    "Panama": 170,
    "Papua New Guinea": 171,
    "Paraguay": 172,
    "Peru": 173,
    "Philippines": 174,
    "Pitcairn": 175,
    "Poland": 176,
    "Portugal": 177,
    "Puerto Rico": 178,
    "Qatar": 179,
    "Réunion": 180,
    "Romania": 181,
    "Russia": 182,
    "Rwanda": 183,
    "Saint Barthélemy": 184,
    "Saint Helena, Ascension and Tristan da Cunha": 185,
    "Saint Kitts and Nevis": 186,
    "Saint Lucia": 187,
    "Saint Martin": 188,
    "Saint Pierre & Miquelon": 189,
    "Saint Vincent and the Grenadines": 190,
    "Samoa": 191,
    "San Marino": 192,
    "Sao Tome and Principe": 193,
    "Saudi Arabia": 194,
    "Senegal": 195,
    "Serbia": 196,
    "Seychelles": 197,
    "Sierra Leone": 198,
    "Singapore": 199,
    "Sint Maarten": 200,
    "Slovakia": 201,
    "Slovenia": 202,
    "Solomon Islands": 203,
    "Somalia": 204,
    "South Africa": 205,
    "South Georgia and S. Sandwich Islands": 206,
    "South Sudan": 207,
    "Spain": 208,
    "Sri Lanka": 209,
    "Sudan": 210,
    "Suriname": 211,
    "Svalbard and Jan Mayen": 212,
    "Sweden": 213,
    "Switzerland": 214,
    "Syria": 215,
    "Taiwan": 216,
    "Tajikistan": 217,
    "Tanzania": 218,
    "Thailand": 219,
    "Timor-Leste": 220,
    "Togo": 221,
    "Tokelau": 222,
    "Tonga": 223,
    "Trinidad and Tobago": 224,
    "Tunisia": 225,
    "Turkey": 226,
    "Turkmenistan": 227,
    "Turks and Caicos Islands": 228,
    "Tuvalu": 229,
    "Uganda": 230,
    "Ukraine": 231,
    "United Arab Emirates": 232,
    "United Kingdom": 233,
    "Uruguay": 234,
    "U.S.A.": 235,
    "U.S. Minor Outlying Islands": 236,
    "Uzbekistan": 237,
    "Vanuatu": 238,
    "Vatican": 239,
    "Venezuela": 240,
    "Vietnam": 241,
    "Virgin Islands (UK)": 242,
    "Virgin Islands of the USA": 243,
    "Wallis & Futuna": 244,
    "Western Sahara": 245,
    "Yemen": 246,
    "Zambia": 247,
    "Zimbabwe": 248,
}


# ============================================================
# Postcrossing name matching
# ============================================================

def normalize_country_name(name):
    """
    Normalize country names so small punctuation/case
    differences do not prevent matching.
    """

    name = normalize_text(name)

    name = name.replace("’", "'")
    name = name.replace("–", "-")
    name = name.replace("—", "-")

    return name.casefold()


# Known differences between possible BH Posta names
# and the Postcrossing names.
POSTCROSSING_ALIASES = {
    "bosnia and herzegovina": "Bosnia-Herzegovina",

    "czech republic": "Czechia",

    "cape verde": "Cabo Verde",

    "ivory coast": "Côte d'Ivoire",

    "swaziland": "Eswatini /Swaziland",

    "macau": "Macao",

    "republic of korea": "Korea(South)",
    "south korea": "Korea(South)",
    "korea south": "Korea(South)",

    "democratic people's republic of korea": "Korea(North)",
    "north korea": "Korea(North)",
    "korea north": "Korea(North)",

    "russian federation": "Russia",

    "republic of moldova": "Moldova",

    "turkiye": "Turkey",
    "türkiye": "Turkey",

    "usa": "U.S.A.",
    "u.s.a": "U.S.A.",
    "united states": "U.S.A.",
    "united states of america": "U.S.A.",

    "vatican city": "Vatican",
    "vatican city state": "Vatican",

    "laos pdr": "Laos",
    "lao people's democratic republic": "Laos",

    "islamic republic of iran": "Iran",

    "united republic of tanzania": "Tanzania",

    "plurinational state of bolivia": "Bolivia",

    "bolivarian republic of venezuela": "Venezuela",

    "federated states of micronesia": "Micronesia",

    "brunei darussalam": "Brunei",

    "burma": "Myanmar",

    "state of palestine": "Palestine",

    "republic of north macedonia": "North Macedonia",

    "timor leste": "Timor-Leste",
    "east timor": "Timor-Leste",

    "eswatini": "Eswatini /Swaziland",

    "côte d’ivoire": "Côte d'Ivoire",
}


def get_postcrossing_number(country):
    """
    Return the Postcrossing number for a country.

    Returns None if the country cannot be matched.
    """

    normalized = normalize_country_name(country)

    # First: exact normalized match.
    for postcrossing_name, number in POSTCROSSING_NUMBERS.items():

        if (
            normalize_country_name(postcrossing_name)
            == normalized
        ):
            return number

    # Second: known alias.
    canonical_name = POSTCROSSING_ALIASES.get(
        normalized
    )

    if canonical_name:
        return POSTCROSSING_NUMBERS.get(
            canonical_name
        )

    return None


def format_country(country):
    """
    Add the Postcrossing number to the country name.

    Example:
        Canada
    becomes:
        40|Canada

    Unknown/unmatched countries become:
        ???|Country Name
    """

    number = get_postcrossing_number(country)

    if number is None:
        return f"???|{country}"

    return f"{number}|{country}"


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

        print(
            f"DEBUG: Saved {filename}"
        )

    except Exception as exc:

        print(
            f"DEBUG: Could not save {filename}: {exc}"
        )


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

            locator = page.locator(
                selector
            )

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

            locator = page.locator(
                selector
            )

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

    try:

        page.wait_for_load_state(
            "networkidle",
            timeout=10000,
        )

    except PlaywrightTimeoutError:
        pass

    page.wait_for_timeout(
        1200
    )

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

    page.wait_for_timeout(
        1200
    )

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

    page.wait_for_timeout(
        700
    )

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

    weight.fill(
        WEIGHT
    )

    try:

        weight.press(
            "Tab"
        )

    except Exception:
        pass

    page.wait_for_timeout(
        300
    )

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

    # Allow client-side onchange logic to run.
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

                    # Do not wait for full networkidle.
                    page.wait_for_timeout(
                        450
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
# Result parsing
# ============================================================

def parse_price(text):

    text = normalize_text(
        text
    )

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
            value_text.replace(
                ",",
                ".",
            )
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

                weight.fill(
                    WEIGHT
                )

        except Exception:
            pass

    click_calculate(
        page
    )

    # Read result.
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
            # Check Postcrossing mappings
            # =================================================

            unmapped_countries = []

            for code, country in destinations:

                if get_postcrossing_number(country) is None:

                    unmapped_countries.append(
                        country
                    )

            if unmapped_countries:

                print()
                print(
                    "WARNING: The following BH Posta "
                    "countries do not have a Postcrossing "
                    "number mapping:"
                )

                for country in unmapped_countries:

                    print(
                        f"    ???|{country}"
                    )

                print()

            # =================================================
            # 7. Check countries
            # =================================================

            print()
            print(
                "7. Checking every destination..."
            )

            all_countries = [
                format_country(country)
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

                postcrossing_number = (
                    get_postcrossing_number(
                        country
                    )
                )

                if postcrossing_number is None:

                    display_country = (
                        f"???|{country}"
                    )

                else:

                    display_country = (
                        f"{postcrossing_number}|{country}"
                    )

                print(
                    f"[{number}/{total}] "
                    f"{display_country} ({code})",
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
                            display_country
                        )

                    else:

                        print(
                            f"    -> UNKNOWN "
                            f"({detail})",
                            flush=True,
                        )

                        unknown.append(
                            display_country
                        )

                except Exception as exc:

                    print(
                        f"    -> ERROR: {exc}",
                        flush=True,
                    )

                    errors.append(
                        f"{display_country} | {exc}"
                    )

                    # --------------------------------------------
                    # Do not restart the entire browser for every
                    # individual error.
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
                time.sleep(
                    0.15
                )

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
                f"Unmapped Postcrossing numbers: "
                f"{len(unmapped_countries)}"
            )

            print(
                f"Runtime:       {elapsed:.1f} seconds"
            )

            print(
                "========================================"
            )

            if unmapped_countries:

                print()
                print(
                    "UNMAPPED POSTCROSSING COUNTRIES:"
                )

                for country in unmapped_countries:

                    print(
                        f"    {country}"
                    )

                print()

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
