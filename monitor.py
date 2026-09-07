import re
import sys
import time
import unicodedata
from pathlib import Path

from playwright.sync_api import sync_playwright


# ============================================================
# CONFIG
# ============================================================

URL = "https://bhpwebout.posta.ba/KalkulatorCijena_WEB_app/Bos/"

OUTPUT_FILE = "bh_posta_countries.txt"

DESTINATION_SELECT = "ddlMeDoOdrediste"
AIR_CHECKBOX = "chbMeDoAvionski"
AIR_WEIGHT = "tbxMeDoAvioTezina"
DOPISNICA_BUTTON = "ImageButton8"

SUSPENDED_MESSAGE = "Prijem pošiljaka se trenutno ne vrši za odabranu državu"

WEIGHT = "10"

COUNTRY_WAIT_MS = 350
MAX_RUNTIME_SECONDS = 22 * 60


# ============================================================
# POSTCROSSING NUMBERS
# ============================================================

POSTCROSSING_NUMBERS = {
    1: "Afghanistan",
    2: "Åland Islands",
    3: "Albania",
    4: "Algeria",
    5: "American Samoa",
    6: "Andorra",
    7: "Angola",
    8: "Anguilla",
    9: "Antarctica",
    10: "Antigua and Barbuda",
    11: "Argentina",
    12: "Armenia",
    13: "Aruba",
    14: "Australia",
    15: "Austria",
    16: "Azerbaijan",
    17: "Bahamas",
    18: "Bahrain",
    19: "Bangladesh",
    20: "Barbados",
    21: "Belarus",
    22: "Belgium",
    23: "Belize",
    24: "Benin",
    25: "Bermuda",
    26: "Bhutan",
    27: "Bolivia",
    28: "Bonaire, Sint Eustatius and Saba",
    29: "Bosnia and Herzegovina",
    30: "Botswana",
    31: "Brazil",
    32: "British Indian Ocean Territory",
    33: "British Virgin Islands",
    34: "Brunei",
    35: "Bulgaria",
    36: "Burkina Faso",
    37: "Burundi",
    38: "Cambodia",
    39: "Cameroon",
    40: "Canada",
    41: "Cape Verde",
    42: "Cayman Islands",
    43: "Central African Republic",
    44: "Chad",
    45: "Chile",
    46: "China",
    47: "Christmas Island",
    48: "Cocos (Keeling) Islands",
    49: "Colombia",
    50: "Comoros",
    51: "Congo",
    52: "Cook Islands",
    53: "Costa Rica",
    54: "Croatia",
    55: "Cuba",
    56: "Curaçao",
    57: "Cyprus",
    58: "Czech Republic",
    59: "Denmark",
    60: "Djibouti",
    61: "Dominica",
    62: "Dominican Republic",
    63: "Ecuador",
    64: "Egypt",
    65: "El Salvador",
    66: "Equatorial Guinea",
    67: "Eritrea",
    68: "Estonia",
    69: "Eswatini",
    70: "Ethiopia",
    71: "Falkland Islands",
    72: "Faroe Islands",
    73: "Fiji",
    74: "France",
    75: "Finland",
    76: "French Guiana",
    77: "French Polynesia",
    78: "Gabon",
    79: "Gambia",
    80: "Georgia",
    81: "Germany",
    82: "Ghana",
    83: "Gibraltar",
    84: "Greece",
    85: "Greenland",
    86: "Grenada",
    87: "Guadeloupe",
    88: "Guam",
    89: "Guatemala",
    90: "Guernsey",
    91: "Guinea",
    92: "Guinea-Bissau",
    93: "Guyana",
    94: "Haiti",
    95: "Honduras",
    96: "Hong Kong",
    97: "Hungary",
    98: "Iceland",
    99: "India",
    100: "Indonesia",
    101: "Iran",
    102: "Iraq",
    103: "Ireland",
    104: "Isle of Man",
    105: "Israel",
    106: "Italy",
    107: "Ivory Coast",
    108: "Jamaica",
    109: "Japan",
    110: "Jersey",
    111: "Jordan",
    112: "Kazakhstan",
    113: "Kenya",
    114: "Kiribati",
    115: "Kuwait",
    116: "Laos",
    117: "Latvia",
    118: "Lebanon",
    119: "Lesotho",
    120: "Liberia",
    121: "Libya",
    122: "Liechtenstein",
    123: "Lithuania",
    124: "Luxembourg",
    125: "Macau",
    126: "Madagascar",
    127: "Malawi",
    128: "Malaysia",
    129: "Maldives",
    130: "Mali",
    131: "Malta",
    132: "Marshall Islands",
    133: "Martinique",
    134: "Mauritania",
    135: "Mauritius",
    136: "Mayotte",
    137: "Mexico",
    138: "Micronesia",
    139: "Moldova",
    140: "Monaco",
    141: "Mongolia",
    142: "Montenegro",
    143: "Montserrat",
    144: "Morocco",
    145: "Mozambique",
    146: "Myanmar",
    147: "Namibia",
    148: "Nauru",
    149: "Nepal",
    150: "Netherlands",
    151: "New Caledonia",
    152: "New Zealand",
    153: "Nicaragua",
    154: "Niger",
    155: "Nigeria",
    156: "Niue",
    157: "Norfolk Island",
    158: "North Korea",
    159: "North Macedonia",
    160: "Northern Mariana Islands",
    161: "Norway",
    162: "Oman",
    163: "Pakistan",
    164: "Palau",
    165: "Palestine",
    166: "Panama",
    167: "Papua New Guinea",
    168: "Paraguay",
    169: "Peru",
    170: "Philippines",
    171: "Pitcairn",
    172: "Poland",
    173: "Portugal",
    174: "Puerto Rico",
    175: "Qatar",
    176: "Réunion",
    177: "Romania",
    178: "Russia",
    179: "Rwanda",
    180: "Saint Barthélemy",
    181: "Saint Helena, Ascension and Tristan da Cunha",
    182: "Saint Kitts and Nevis",
    183: "Saint Lucia",
    184: "Saint Pierre and Miquelon",
    185: "Saint Vincent and the Grenadines",
    186: "Samoa",
    187: "San Marino",
    188: "São Tomé and Príncipe",
    189: "Saudi Arabia",
    190: "Senegal",
    191: "Serbia",
    192: "Seychelles",
    193: "Sierra Leone",
    194: "Singapore",
    195: "Sint Maarten",
    196: "Slovakia",
    197: "Slovenia",
    198: "Solomon Islands",
    199: "Somalia",
    200: "South Africa",
    201: "South Korea",
    202: "South Sudan",
    203: "Spain",
    204: "Sri Lanka",
    205: "Sudan",
    206: "Suriname",
    207: "Svalbard and Jan Mayen",
    208: "Sweden",
    209: "Switzerland",
    210: "Syria",
    211: "Taiwan",
    212: "Tajikistan",
    213: "Tanzania",
    214: "Thailand",
    215: "Timor-Leste",
    216: "Togo",
    217: "Tokelau",
    218: "Tonga",
    219: "Trinidad and Tobago",
    220: "Tunisia",
    221: "Türkiye",
    222: "Turkmenistan",
    223: "Turks and Caicos Islands",
    224: "Tuvalu",
    225: "Uganda",
    226: "Ukraine",
    227: "United Arab Emirates",
    228: "United Kingdom",
    229: "United States",
    230: "Uruguay",
    231: "Uzbekistan",
    232: "Vanuatu",
    233: "Vatican City",
    234: "Venezuela",
    235: "Vietnam",
    236: "Wallis and Futuna",
    237: "Western Sahara",
    238: "Yemen",
    239: "Zambia",
    240: "Zimbabwe",
    241: "U.S. Virgin Islands",
    242: "United States Minor Outlying Islands",
    243: "Kosovo",
    244: "Curaçao",
    245: "Bonaire",
    246: "Sint Eustatius",
    247: "Saba",
}


# ============================================================
# BH POŠTA -> POSTCROSSING
# ============================================================

BH_POSTA_TO_POSTCROSSING = {
    # Europe
    "Albanija": 3,
    "Andora": 6,
    "Austrija": 15,
    "Belgija": 22,
    "Bjelorusija": 21,
    "Bosna i Hercegovina": 29,
    "Bugarska": 35,
    "Crna Gora": 143,
    "Češka": 58,
    "Danska": 59,
    "Estonija": 68,
    "Finska": 75,
    "Francuska": 74,
    "Grčka": 84,
    "Hrvatska": 54,
    "Irska": 103,
    "Island": 98,
    "Italija": 106,
    "Kipar": 57,
    "Kosovo": 244,
    "Latvija": 118,
    "Lihtenštajn": 123,
    "Litvanija": 124,
    "Luksemburg": 125,
    "Mađarska": 97,
    "Malta": 132,
    "Moldavija": 140,
    "Monako": 141,
    "Njemačka": 81,
    "Nizozemska": 151,
    "Norveška": 162,
    "Poljska": 173,
    "Portugal": 174,
    "Rumunija": 178,
    "San Marino": 188,
    "Sjeverna Makedonija": 160,
    "Slovačka": 197,
    "Slovenija": 198,
    "Srbija": 192,
    "Španija": 204,
    "Švedska": 209,
    "Švicarska": 210,
    "Turska": 222,
    "Ukrajina": 227,
    "Ujedinjeno Kraljevstvo": 229,
    "Vatikan": 234,

    # Asia
    "Afganistan": 1,
    "Azerbejdžan": 16,
    "Bahrein": 18,
    "Bangladeš": 19,
    "Butan": 26,
    "Brunej": 34,
    "Filipini": 171,
    "Gruzija": 80,
    "Hong Kong": 96,
    "Indija": 99,
    "Indonezija": 100,
    "Iran": 101,
    "Irak": 102,
    "Izrael": 105,
    "Japan": 109,
    "Jemen": 239,
    "Jordan": 111,
    "Južna Koreja": 202,
    "Kambodža": 38,
    "Kazahstan": 112,
    "Kina": 46,
    "Kirgistan": 116,
    "Kuvajt": 115,
    "Laos": 117,
    "Liban": 119,
    "Makao": 126,
    "Malezija": 129,
    "Maldivi": 130,
    "Mongolija": 142,
    "Nepal": 150,
    "Oman": 163,
    "Pakistan": 164,
    "Palestina": 166,
    "Saudijska Arabija": 190,
    "Singapur": 195,
    "Šri Lanka": 205,
    "Tajvan": 212,
    "Tadžikistan": 213,
    "Tajland": 215,
    "Turkmenistan": 223,
    "Ujedinjeni Arapski Emirati": 228,
    "Uzbekistan": 232,
    "Vijetnam": 236,

    # Africa
    "Alžir": 4,
    "Benin": 24,
    "Bocvana": 30,
    "Burkina Faso": 36,
    "Burundi": 37,
    "Egipat": 64,
    "Eritreja": 67,
    "Eswatini": 69,
    "Etiopija": 70,
    "Gana": 82,
    "Gvineja": 91,
    "Gvineja Bisau": 92,
    "Južna Afrika": 201,
    "Kamerun": 39,
    "Kenija": 113,
    "Komori": 50,
    "Kongo": 51,
    "Lesoto": 120,
    "Liberija": 121,
    "Libija": 122,
    "Madagaskar": 127,
    "Malavi": 128,
    "Mali": 131,
    "Maroko": 145,
    "Mauricijus": 136,
    "Mauritanija": 135,
    "Mozambik": 146,
    "Namibija": 148,
    "Niger": 155,
    "Nigerija": 156,
    "Obala Slonovače": 107,
    "Ruanda": 180,
    "Senegal": 191,
    "Sejšeli": 193,
    "Sijera Leone": 194,
    "Somalija": 200,
    "Sudan": 206,
    "Tanzanija": 214,
    "Togo": 217,
    "Tunis": 221,
    "Uganda": 226,
    "Zambija": 240,
    "Zimbabve": 241,

    # Americas
    "Argentina": 11,
    "Bahami": 17,
    "Barbados": 20,
    "Belize": 23,
    "Bolivija": 27,
    "Brazil": 31,
    "Čile": 45,
    "Dominika": 61,
    "Dominikanska Republika": 62,
    "Ekvador": 63,
    "El Salvador": 65,
    "Grenada": 86,
    "Gvatemala": 89,
    "Gvajana": 93,
    "Haiti": 94,
    "Honduras": 95,
    "Jamajka": 108,
    "Kanada": 40,
    "Kolumbija": 49,
    "Kostarika": 53,
    "Kuba": 55,
    "Meksiko": 138,
    "Nikaragva": 154,
    "Panama": 167,
    "Paragvaj": 169,
    "Peru": 170,
    "Sjedinjene Američke Države": 230,
    "Surinam": 207,
    "Trinidad i Tobago": 220,
    "Urugvaj": 231,
    "Venezuela": 235,

    # Oceania
    "Australija": 14,
    "Fidži": 73,
    "Kiribati": 114,
    "Nauru": 149,
    "Novi Zeland": 153,
    "Palau": 165,
    "Papua Nova Gvineja": 168,
    "Samoa": 187,
    "Solomonska Ostrva": 199,
    "Tonga": 219,
    "Tuvalu": 225,
    "Vanuatu": 233,

    # Explicitly needed exception:
    # Åland is NOT independently checked at BH Pošta.
    # It inherits Finland's status.
    "Åland Islands": 2,
}


NORMALIZED_BH_POSTA_TO_POSTCROSSING = {}


# ============================================================
# NORMALIZATION
# ============================================================

def normalize_country_name(name):
    if not name:
        return ""

    text = unicodedata.normalize("NFKD", name)

    text = "".join(
        char
        for char in text
        if not unicodedata.combining(char)
    )

    text = text.upper()

    text = text.replace("Đ", "D")
    text = text.replace("Ð", "D")
    text = text.replace("Ł", "L")

    text = re.sub(r"[^A-Z0-9]+", " ", text)

    return " ".join(text.split())


for _name, _number in BH_POSTA_TO_POSTCROSSING.items():
    NORMALIZED_BH_POSTA_TO_POSTCROSSING[
        normalize_country_name(_name)
    ] = _number


# ============================================================
# SPECIAL COUNTRY HELPERS
# ============================================================

def is_aland(country_name):
    normalized = normalize_country_name(country_name)

    return normalized in {
        "ALAND",
        "ALAND ISLANDS",
    }


def is_finska(country_name):
    normalized = normalize_country_name(country_name)

    return normalized == "FINSKA"


def get_finska_status(status_by_country):
    for country_name, status in status_by_country.items():
        if is_finska(country_name):
            return status

    return None


# ============================================================
# POSTCROSSING LOOKUP
# ============================================================

def get_postcrossing_numbers(country_name):
    if not country_name:
        return []

    normalized = normalize_country_name(country_name)

    # --------------------------------------------------------
    # ÅLAND - explicit and unconditional mapping
    # --------------------------------------------------------
    if normalized in {"ALAND", "ALAND ISLANDS"}:
        return [2]

    # --------------------------------------------------------
    # Exact normalized BH Pošta lookup
    # --------------------------------------------------------
    if normalized in NORMALIZED_BH_POSTA_TO_POSTCROSSING:
        return [
            NORMALIZED_BH_POSTA_TO_POSTCROSSING[normalized]
        ]

    # --------------------------------------------------------
    # Special cases
    # --------------------------------------------------------

    if "HOLANDSKI ANTILI" in normalized:
        return [13, 28, 57, 200]

    if (
        "SVETA HELENA" in normalized
        or "SAINT HELENA" in normalized
        or "ASCENSION" in normalized
        or "TRISTAN" in normalized
    ):
        return [182]

    if "U S VIRGIN" in normalized or "AMERICKI DJEVICANSKI" in normalized:
        return [242]

    if "TAHITI" in normalized:
        return [77]

    if "SAINT EUSTATIUS" in normalized or "SVETI EUSTATIUS" in normalized:
        return [247]

    return []


def format_country(country_name):
    """
    Converts a BH Pošta country name into:

        number|Postcrossing name

    IMPORTANT:
    Åland is explicitly handled here so it can never become
    ???|Åland Islands.
    """

    normalized = normalize_country_name(country_name)

    # --------------------------------------------------------
    # HARD-CODE ÅLAND
    # --------------------------------------------------------
    if normalized in {"ALAND", "ALAND ISLANDS"}:
        return "2|Åland Islands"

    numbers = get_postcrossing_numbers(country_name)

    if not numbers:
        return f"???|{country_name}"

    # Special Holandski Antili handling
    if numbers == [13, 28, 57, 200]:
        names = [
            POSTCROSSING_NUMBERS.get(number, "?")
            for number in numbers
        ]

        return (
            f"{numbers[0]}|{names[0]}; "
            f"{numbers[1]}|{names[1]}; "
            f"{numbers[2]}|{names[2]}; "
            f"{numbers[3]}|{names[3]}"
        )

    result = []

    for number in numbers:
        postcrossing_name = POSTCROSSING_NUMBERS.get(
            number,
            "UNKNOWN"
        )

        result.append(
            f"{number}|{postcrossing_name}"
        )

    return "; ".join(result)


def is_known_country(country_name):
    return bool(get_postcrossing_numbers(country_name))


# ============================================================
# PLAYWRIGHT HELPERS
# ============================================================

def select_dopisnica(page):
    try:
        page.locator(
            f"#{DOPISNICA_BUTTON}"
        ).click(timeout=5000)

        time.sleep(0.5)
        return True

    except Exception:
        return False


def get_destinations(page):
    select = page.locator(
        f"#{DESTINATION_SELECT}"
    )

    options = select.locator("option")

    result = []

    count = options.count()

    for i in range(count):
        option = options.nth(i)

        value = option.get_attribute("value")
        text = option.inner_text().strip()

        if not value:
            continue

        if not text:
            continue

        result.append((value, text))

    return result


def select_air_transport(page):
    checkbox = page.locator(
        f"#{AIR_CHECKBOX}"
    )

    try:
        if not checkbox.is_checked():
            checkbox.check()

    except Exception:
        try:
            checkbox.click()
        except Exception:
            pass


def set_weight(page):
    weight = page.locator(
        f"#{AIR_WEIGHT}"
    )

    try:
        weight.fill(WEIGHT)
    except Exception:
        try:
            weight.click()
            weight.press("Control+A")
            weight.type(WEIGHT)
        except Exception:
            pass


def read_page_text(page):
    try:
        return page.locator("body").inner_text()
    except Exception:
        return ""


# ============================================================
# CALCULATE COUNTRY
# ============================================================

def calculate_country(page, code):
    try:
        select = page.locator(
            f"#{DESTINATION_SELECT}"
        )

        select.select_option(code)

        time.sleep(COUNTRY_WAIT_MS / 1000)

        body_text = read_page_text(page)

        if SUSPENDED_MESSAGE.lower() in body_text.lower():
            return "SUSPENDED"

        # If the calculator has a normal price/result,
        # regard it as available.
        #
        # The original script relied primarily on the absence
        # of the suspension message.
        return "AVAILABLE"

    except Exception as exc:
        print(
            f"    ERROR while checking destination {code}: {exc}"
        )

        return "ERROR"


# ============================================================
# ÅLAND EXCEPTION
# ============================================================

def apply_finska_aland_exception(
    all_countries,
    status_by_country,
    suspended,
    unknown,
    errors,
):
    """
    Åland (#2) is controlled entirely by Finska (#75).

    Finska AVAILABLE  -> Åland AVAILABLE
    Finska SUSPENDED  -> Åland SUSPENDED

    Åland is NEVER independently queried at BH Pošta.
    """

    finska_status = get_finska_status(status_by_country)

    # --------------------------------------------------------
    # Åland is NOT in the BH Pošta dropdown.
    #
    # Insert it directly after Finska in the output list.
    # --------------------------------------------------------

    # Remove Åland first in case it somehow exists already.
    all_countries[:] = [
        country
        for country in all_countries
        if not is_aland(country)
    ]

    new_all_countries = []
    aland_inserted = False

    for country in all_countries:
        new_all_countries.append(country)

        if is_finska(country):
            new_all_countries.append("Åland Islands")
            aland_inserted = True

    # Fallback only if Finska was somehow not present.
    if not aland_inserted:
        new_all_countries.append("Åland Islands")

    all_countries[:] = new_all_countries

    # --------------------------------------------------------
    # If Finska was somehow not found, do not silently claim
    # Åland is available.
    # --------------------------------------------------------
    if finska_status is None:
        print(
            "\nWARNING: Finska (#75) was not found."
        )

        print(
            "Åland (#2) has been added to ALL COUNTRIES "
            "but is marked UNKNOWN."
        )

        if not any(is_aland(country) for country in unknown):
            unknown.append("Åland Islands")

        return

    # --------------------------------------------------------
    # Remove any previous Åland classification.
    # --------------------------------------------------------
    suspended[:] = [
        country
        for country in suspended
        if not is_aland(country)
    ]

    unknown[:] = [
        country
        for country in unknown
        if not is_aland(country)
    ]

    errors[:] = [
        country
        for country in errors
        if not is_aland(country)
    ]

    # --------------------------------------------------------
    # APPLY FINLAND STATUS
    # --------------------------------------------------------

    if finska_status == "AVAILABLE":

        print(
            "\n  FINSKA (#75) AVAILABLE"
        )

        print(
            "  -> ÅLAND ISLANDS (#2) AVAILABLE"
        )

        # Nothing is added to suspended/unknown/errors.
        # Therefore Åland belongs to ALL COUNTRIES only.

    elif finska_status == "SUSPENDED":

        print(
            "\n  FINSKA (#75) SUSPENDED"
        )

        print(
            "  -> ÅLAND ISLANDS (#2) SUSPENDED"
        )

        if not any(is_aland(country) for country in suspended):
            suspended.append("Åland Islands")

    elif finska_status == "UNKNOWN":

        print(
            "\n  FINSKA (#75) UNKNOWN"
        )

        print(
            "  -> ÅLAND ISLANDS (#2) UNKNOWN"
        )

        if not any(is_aland(country) for country in unknown):
            unknown.append("Åland Islands")

    elif finska_status == "ERROR":

        print(
            "\n  FINSKA (#75) ERROR"
        )

        print(
            "  -> ÅLAND ISLANDS (#2) ERROR"
        )

        if not any(is_aland(country) for country in errors):
            errors.append("Åland Islands")


# ============================================================
# OUTPUT
# ============================================================

def write_output_file(
    all_countries,
    suspended,
    unknown,
    errors,
):
    output_path = Path(OUTPUT_FILE)

    # --------------------------------------------------------
    # Make sure Åland is ALWAYS present.
    # --------------------------------------------------------
    if not any(is_aland(country) for country in all_countries):
        all_countries.append("Åland Islands")

    # Remove duplicates while preserving order.
    def unique(items):
        result = []
        seen = set()

        for item in items:
            key = normalize_country_name(item)

            if key not in seen:
                seen.add(key)
                result.append(item)

        return result

    all_countries = unique(all_countries)
    suspended = unique(suspended)
    unknown = unique(unknown)
    errors = unique(errors)

    lines = []

    # ========================================================
    # ALL COUNTRIES
    # ========================================================

    lines.append("ALL COUNTRIES")
    lines.append("=" * 80)

    for country in all_countries:
        lines.append(format_country(country))

    lines.append("")
    lines.append("")

    # ========================================================
    # SUSPENDED
    # ========================================================

    lines.append("SUSPENDED COUNTRIES")
    lines.append("=" * 80)

    if suspended:
        for country in suspended:
            lines.append(format_country(country))
    else:
        lines.append("None")

    lines.append("")
    lines.append("")

    # ========================================================
    # UNKNOWN
    # ========================================================

    lines.append("UNKNOWN COUNTRIES")
    lines.append("=" * 80)

    if unknown:
        for country in unknown:
            lines.append(format_country(country))
    else:
        lines.append("None")

    lines.append("")
    lines.append("")

    # ========================================================
    # ERRORS
    # ========================================================

    lines.append("ERROR COUNTRIES")
    lines.append("=" * 80)

    if errors:
        for country in errors:
            lines.append(format_country(country))
    else:
        lines.append("None")

    lines.append("")
    lines.append("")

    # ========================================================
    # SUMMARY
    # ========================================================

    lines.append("SUMMARY")
    lines.append("=" * 80)

    lines.append(
        f"ALL COUNTRIES: {len(all_countries)}"
    )

    lines.append(
        f"SUSPENDED: {len(suspended)}"
    )

    lines.append(
        f"UNKNOWN: {len(unknown)}"
    )

    lines.append(
        f"ERRORS: {len(errors)}"
    )

    # --------------------------------------------------------
    # Explicit Åland diagnostic
    # --------------------------------------------------------

    aland_in_all = any(
        is_aland(country)
        for country in all_countries
    )

    aland_in_suspended = any(
        is_aland(country)
        for country in suspended
    )

    aland_in_unknown = any(
        is_aland(country)
        for country in unknown
    )

    aland_in_errors = any(
        is_aland(country)
        for country in errors
    )

    lines.append("")
    lines.append(
        f"ÅLAND #2 IN ALL COUNTRIES: "
        f"{'YES' if aland_in_all else 'NO'}"
    )

    lines.append(
        f"ÅLAND #2 SUSPENDED: "
        f"{'YES' if aland_in_suspended else 'NO'}"
    )

    lines.append(
        f"ÅLAND #2 UNKNOWN: "
        f"{'YES' if aland_in_unknown else 'NO'}"
    )

    lines.append(
        f"ÅLAND #2 ERROR: "
        f"{'YES' if aland_in_errors else 'NO'}"
    )

    # --------------------------------------------------------
    # Unmapped countries
    # --------------------------------------------------------

    unmapped = [
        country
        for country in all_countries
        if not is_known_country(country)
    ]

    lines.append("")
    lines.append("UNMAPPED BH POŠTA NAMES")
    lines.append("=" * 80)

    if unmapped:
        for country in unmapped:
            lines.append(country)
    else:
        lines.append("None")

    output_path.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    print(
        f"\nOutput written to: {output_path.resolve()}"
    )


# ============================================================
# MAIN
# ============================================================

def main():
    start_time = time.time()

    all_countries = []
    suspended = []
    unknown = []
    errors = []

    # This dictionary is the authoritative status record.
    status_by_country = {}

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True
        )

        page = browser.new_page()

        try:
            print("Opening BH Pošta calculator...")
            page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            time.sleep(1)

            print("Selecting Dopisnica...")
            select_dopisnica(page)

            time.sleep(0.5)

            print("Reading BH Pošta destinations...")

            destinations = get_destinations(page)

            if not destinations:
                print(
                    "ERROR: No destinations found."
                )

                return

            print(
                f"Found {len(destinations)} destinations."
            )

            # ------------------------------------------------
            # Select air transport and weight.
            # ------------------------------------------------

            print("Selecting air transport...")
            select_air_transport(page)

            print("Setting weight...")
            set_weight(page)

            time.sleep(0.5)

            # Re-read destinations after changing the options.
            destinations_after_options = get_destinations(page)

            if destinations_after_options:
                destinations = destinations_after_options

            # ------------------------------------------------
            # IMPORTANT:
            #
            # Åland is virtual for this script. It does not
            # need to exist in the BH Pošta dropdown.
            # ------------------------------------------------

            all_countries = [
                country
                for _, country in destinations
                if not is_aland(country)
            ]

            print(
                f"Checking {len(destinations)} BH Pošta destinations..."
            )

            print(
                "\nÅland exception:"
            )

            print(
                "  Åland (#2) will inherit Finska (#75)."
            )

            # ------------------------------------------------
            # Print mapping information.
            # ------------------------------------------------

            print(
                "\nDestination mapping:"
            )

            for code, country in destinations:

                if is_aland(country):
                    print(
                        f"  {country} -> 2|Åland Islands "
                        "(controlled by Finska #75)"
                    )
                    continue

                print(
                    f"  {country} -> {format_country(country)}"
                )

            # ------------------------------------------------
            # Check every actual BH Pošta destination.
            # ------------------------------------------------

            for index, (code, country) in enumerate(
                destinations,
                start=1
            ):

                elapsed = time.time() - start_time

                if elapsed > MAX_RUNTIME_SECONDS:
                    print(
                        "\nMaximum runtime reached."
                    )
                    break

                # --------------------------------------------
                # Åland must NEVER be independently checked.
                # --------------------------------------------

                if is_aland(country):
                    print(
                        f"\n[{index}/{len(destinations)}] "
                        f"{country}"
                    )

                    print(
                        "  -> SKIPPED "
                        "(controlled by Finska #75)"
                    )

                    continue

                print(
                    f"\n[{index}/{len(destinations)}] "
                    f"{country}"
                )

                print(
                    f"  Postcrossing: "
                    f"{format_country(country)}"
                )

                status = calculate_country(
                    page,
                    code,
                )

                # --------------------------------------------
                # Store authoritative status.
                # --------------------------------------------

                status_by_country[country] = status

                if status == "AVAILABLE":

                    print(
                        "  -> AVAILABLE"
                    )

                elif status == "SUSPENDED":

                    print(
                        "  -> SUSPENDED"
                    )

                    suspended.append(country)

                elif status == "UNKNOWN":

                    print(
                        "  -> UNKNOWN"
                    )

                    unknown.append(country)

                elif status == "ERROR":

                    print(
                        "  -> ERROR"
                    )

                    errors.append(country)

                # --------------------------------------------
                # Recovery / pacing.
                # --------------------------------------------

                time.sleep(0.1)

            # =================================================
            # APPLY FINLAND -> ÅLAND EXCEPTION
            # =================================================

            print(
                "\n" + "=" * 80
            )

            print(
                "APPLYING FINLAND -> ÅLAND EXCEPTION"
            )

            print(
                "=" * 80
            )

            apply_finska_aland_exception(
                all_countries=all_countries,
                status_by_country=status_by_country,
                suspended=suspended,
                unknown=unknown,
                errors=errors,
            )

            # =================================================
            # FINAL DIAGNOSTIC
            # =================================================

            print(
                "\nFINAL ÅLAND CHECK:"
            )

            print(
                f"  format_country('Åland Islands') = "
                f"{format_country('Åland Islands')}"
            )

            finska_status = get_finska_status(
                status_by_country
            )

            print(
                f"  Finska (#75) status = "
                f"{finska_status}"
            )

            print(
                f"  Åland (#2) is in ALL COUNTRIES = "
                f"{any(is_aland(c) for c in all_countries)}"
            )

            print(
                f"  Åland (#2) is SUSPENDED = "
                f"{any(is_aland(c) for c in suspended)}"
            )

            print(
                f"  Åland (#2) is UNKNOWN = "
                f"{any(is_aland(c) for c in unknown)}"
            )

            # =================================================
            # WRITE OUTPUT
            # =================================================

            write_output_file(
                all_countries=all_countries,
                suspended=suspended,
                unknown=unknown,
                errors=errors,
            )

            # =================================================
            # SUMMARY
            # =================================================

            print(
                "\n" + "=" * 80
            )

            print("DONE")
            print("=" * 80)

            print(
                f"All countries: {len(all_countries)}"
            )

            print(
                f"Suspended: {len(suspended)}"
            )

            print(
                f"Unknown: {len(unknown)}"
            )

            print(
                f"Errors: {len(errors)}"
            )

            print(
                "\nÅland output:"
            )

            print(
                "  2|Åland Islands"
            )

            if finska_status == "AVAILABLE":
                print(
                    "  Status: AVAILABLE "
                    "(inherited from Finska #75)"
                )
            elif finska_status == "SUSPENDED":
                print(
                    "  Status: SUSPENDED "
                    "(inherited from Finska #75)"
                )
            else:
                print(
                    f"  Status: {finska_status}"
                )

        finally:
            browser.close()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    try:
        main()

    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        sys.exit(1)

    except Exception as exc:
        print(
            f"\nFATAL ERROR: {exc}"
        )
        sys.exit(1)
