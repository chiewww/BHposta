import re
import sys
import time
import unicodedata
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

COUNTRY_WAIT_MS = 350
MAX_RUNTIME_SECONDS = 22 * 60


# ============================================================
# POSTCROSSING LIST
#
# Authoritative list supplied by the user.
# Number -> Postcrossing name
# ============================================================

POSTCROSSING_NUMBERS = {
    1: "Afganistan",
    2: "Åland Islands",
    3: "Albanija",
    4: "Alžir",
    5: "AMERICAN SAMOA",
    6: "ANDORRA",
    7: "Angola",
    8: "ANGUILLA",
    9: "Antarctica",
    10: "Antiga i Barbuda",
    11: "Argentina",
    12: "Armenija",
    13: "Aruba",
    14: "Australija",
    15: "Austrija",
    16: "Azerbejdžan",
    17: "Bahami",
    18: "Bahrein",
    19: "Bangladeš",
    20: "Barbados",
    21: "Bjelorusija",
    22: "Belgija",
    23: "Belize",
    24: "Benin",
    25: "Bermuda",
    26: "Butan",
    27: "Bolivija",
    28: "BONAIRE",
    29: "Bosna i Hercegovina",
    30: "Bocvana",
    31: "Brazil",
    32: "BRITISH INDIAN OCEAN TERRITORY",
    33: "Brunei Daruselam",
    34: "Bugarska",
    35: "Burkina Faso",
    36: "Burundi",
    37: "Cap-Vert (Zeleni-Rt)",
    38: "Kambodža",
    39: "Kamerun",
    40: "Kanada",
    41: "Kajmanski otoci",
    42: "Centralnoafricka Republika",
    43: "Cad",
    44: "Cile",
    45: "Kina",
    46: "Christmas Island",
    47: "COCOS (KEELING) ISLANDS",
    48: "Kolumbija",
    49: "Komori",
    50: "Kongo (Rep.)",
    51: "Kongo (Dem.Rep.)",
    52: "COOK ISLANDS",
    53: "Costa Rica",
    54: "Obala Slonovace",
    55: "Hrvatska",
    56: "Cuba",
    57: "Curaçao",
    58: "Kipar",
    59: "Češka Republika",
    60: "Danska",
    61: "Džibuti",
    62: "Dominika",
    63: "Dominikanska Republika",
    64: "Ekvador",
    65: "Egipat",
    66: "Salvador",
    67: "Ekvatorijalna Gvineja",
    68: "Eritreja",
    69: "Estonija",
    70: "ESVATINI (SVAZILEND)",
    71: "Etiopija",
    72: "FALKLAND ISLANDS (MALVINAS)",
    73: "Farski otoci",
    74: "Fidži",
    75: "Finska",
    76: "Francuska",
    77: "French Guiana",
    78: "Polinezija",
    79: "French Southern Territories",
    80: "Gabon",
    81: "Gambija",
    82: "Gruzija",
    83: "Njemacka",
    84: "Gana",
    85: "Gibraltar",
    86: "Grcka",
    87: "Grenland",
    88: "Grenada",
    89: "Gvadelupe",
    90: "Guam",
    91: "Gvatemala",
    92: "Guernsey",
    93: "Gvineja",
    94: "Gvineja Bisao",
    95: "Gvajana",
    96: "Haiti",
    97: "Honduras",
    98: "Hong Kong, Kina",
    99: "Hungary",
    100: "Island",
    101: "Indija",
    102: "Indonezija",
    103: "Iran",
    104: "Irak",
    105: "Irska",
    106: "Otok Man",
    107: "Izrael",
    108: "Italija",
    109: "Jamajka",
    110: "Japan",
    111: "Jersey",
    112: "Jordan",
    113: "Kazahstan",
    114: "Kenija",
    115: "Kiribati",
    116: "Koreja (Dem.Rep.)",
    117: "Koreja (Rep.)",
    118: "Kosovo",
    119: "Kuvajt",
    120: "Kirgistan",
    121: "Laos",
    122: "Latvija",
    123: "Liban",
    124: "Lesoto",
    125: "Liberija",
    126: "Libija",
    127: "Lihtenštajn",
    128: "Litvanija",
    129: "Luksemburg",
    130: "Macao",
    131: "Madagaskar",
    132: "Malavi",
    133: "Malezija",
    134: "Maldivi",
    135: "Mali",
    136: "Malta",
    137: "Marshall Islands",
    138: "Martinique",
    139: "Mauritanija",
    140: "Mauricijus",
    141: "Mayotte",
    142: "Meksiko",
    143: "MICRONESIA, FEDERATED STATES OF",
    144: "Moldavija",
    145: "Monako",
    146: "Mongolia",
    147: "Crna Gora",
    148: "Montserrat",
    149: "Maroko",
    150: "Mozambik",
    151: "Mianmar",
    152: "Namibija",
    153: "Nauru",
    154: "Nepal",
    155: "Holandija",
    156: "Nova Kaledonija",
    157: "Novi Zeland",
    158: "Nikaragva",
    159: "Niger",
    160: "Nigerija",
    161: "Niue",
    162: "NORFOLK ISLAND",
    163: "NORTHERN MARIANA ISLANDS",
    164: "Republika Sjeverna Makedonija",
    165: "Norveška",
    166: "Oman",
    167: "Pakistan",
    168: "Palau",
    169: "Palestine",
    170: "Panama",
    171: "Papua Nova Gvineja",
    172: "Paragvaj",
    173: "Peru",
    174: "Filipini",
    175: "PITCAIRN",
    176: "Poljska",
    177: "Portugal",
    178: "Puerto Rico",
    179: "Katar",
    180: "REUNION",
    181: "Rumunija",
    182: "Ruska Federacija",
    183: "Ruanda",
    184: "Sveti Barthelemy",
    185: "ASCENSION",
    186: "Sveti Kits i Nevis",
    187: "Sveta Lucija",
    188: "S. Martin",
    189: "SAINT PIERRE AND MIQUELON",
    190: "Sveti Vincent i Grenadine",
    191: "Samoa",
    192: "San Marino",
    193: "Sveti Tome i Principe",
    194: "Saudijska Arabija",
    195: "Senegal",
    196: "Srbija",
    197: "Sejšeli",
    198: "Siera Leone",
    199: "Singapur",
    200: "Sint Maarten",
    201: "Slovacka",
    202: "Slovenija",
    203: "Solomonski otoci",
    204: "Somalija",
    205: "Južnoafricka Republika",
    206: "Južna Džodžija i Sandwich otoci",
    207: "Južni Sudan",
    208: "Španija",
    209: "Šri Lanka",
    210: "Sudan",
    211: "Suriname",
    212: "SVALBARD AND JAN MAYEN",
    213: "Švedska",
    214: "Švicarska",
    215: "Sirija",
    216: "Tajvan - Kina",
    217: "Tadžikistan",
    218: "Tanzanija",
    219: "Tajland",
    220: "Timor",
    221: "Togo",
    222: "Tokelau",
    223: "Tonga",
    224: "Trinidad i Tobago",
    225: "Tunis",
    226: "Turska",
    227: "Turkmenistan",
    228: "TURKS AND CAICOS ISLANDS",
    229: "Tuvalu",
    230: "Uganda",
    231: "Ukrajina",
    232: "Ujedinjeni Arapski Emirati",
    233: "Velika Britanija",
    234: "Urugvaj",
    235: "SAD Sjedinjene Americke Države",
    236: "UNITED STATES MINOR OUTLYING ISLANDS",
    237: "Uzbekistan",
    238: "Vanuatu",
    239: "Vatikan",
    240: "Venecuela",
    241: "Vijetnam",
    242: "VIRGIN ISLANDS, BRITISH",
    243: "Amer.Djevičanska Ostrva",
    244: "Walis i Futuna",
    245: "WESTERN SAHARA",
    246: "Jemen",
    247: "Zambija",
    248: "Zimbabve",
}


# ============================================================
# BH POSTA -> POSTCROSSING
#
# These are the ACTUAL BH Posta names from the user's output.
#
# None = no separate Postcrossing destination in the supplied
# 1-248 list.
#
# list[int] = one BH Posta destination corresponds to several
# Postcrossing destinations.
# ============================================================

BH_POSTA_TO_POSTCROSSING = {
    "Afganistan": 1,
    "Albanija": 3,
    "Alžir": 4,
    "Amer.Djevičanska Ostrva": 243,
    "AMERICAN SAMOA": 5,
    "ANDORRA": 6,
    "Angola": 7,
    "ANGUILLA": 8,
    "Antiga i Barbuda": 10,
    "Argentina": 11,
    "Armenija": 12,
    "Aruba": 13,

    "ASCENSION": 185,
    "Ascension": 185,

    "Australija": 14,
    "Austrija": 15,
    "Azerbejdžan": 16,

    "Azori": None,

    "Bahami": 17,
    "Bahrein": 18,
    "Bangladeš": 19,
    "Barbados": 20,
    "Belgija": 22,
    "Belize": 23,
    "Benin": 24,
    "BERMUDA": 25,
    "Bjelorusija": 21,
    "Bocvana": 30,
    "Bolivija": 27,
    "BONAIRE": 28,
    "Bosna i Hercegovina": 29,

    "BOUVET ISLAND": None,

    "Brazil": 31,
    "BRITISH INDIAN OCEAN TERRITORY": 32,
    "Brunei Daruselam": 33,
    "Bugarska": 34,
    "Burkina Faso": 35,
    "Burundi": 36,
    "Butan": 26,
    "Cad": 43,
    "Cap-Vert (Zeleni-Rt)": 37,
    "Centralnoafricka Republika": 42,

    "Channel Islands": None,

    "CHRISTMAS ISLAND": 46,
    "Cile": 44,
    "COCOS (KEELING) ISLANDS": 47,
    "COOK ISLANDS": 52,
    "Crna Gora": 147,
    "Češka Republika": 59,
    "Danska": 60,
    "Dominika": 62,
    "Dominikanska Republika": 63,
    "Džibuti": 61,
    "Egipat": 65,
    "Ekvador": 64,
    "Ekvatorijalna Gvineja": 67,
    "Eritreja": 68,
    "Estonija": 69,
    "ESVATINI (SVAZILEND)": 70,
    "Etiopija": 71,
    "FALKLAND ISLANDS (MALVINAS)": 72,
    "Farski otoci": 73,
    "Fidži": 74,
    "Filipini": 174,
    "Finska": 75,
    "Francuska": 76,
    "FRENCH GUIANA": 77,
    "FRENCH SOUTHERN TERRITORIES": 79,
    "Gabon": 80,
    "Gambija": 81,
    "Gana": 84,
    "Gibraltar": 85,
    "Grcka": 86,
    "Grenada": 88,
    "Grenland": 87,
    "Gruzija": 82,
    "GUAM": 90,
    "Guernsey": 92,
    "Gvadelupe": 89,
    "Gvajana": 95,
    "Gvatemala": 91,
    "Gvineja": 93,
    "Gvineja Bisao": 94,
    "Haiti": 96,

    "HEARD ISLAND AND MCDONALD ISLANDS": None,

    "Holandija": 155,

    # Four Postcrossing destinations.
    "Holandski Antili": [
        13,   # Aruba
        28,   # BONAIRE
        57,   # Curaçao
        200,  # Sint Maarten
    ],

    "Honduras": 97,
    "Hong Kong, Kina": 98,
    "Hrvatska": 55,
    "Indija": 101,
    "Indonezija": 102,
    "Irak": 104,
    "Iran": 103,
    "Irska": 105,
    "Island": 100,

    "Italija": 108,

    "Italijanske poste": None,

    "Izrael": 107,
    "Jamajka": 109,
    "Japan": 110,
    "Jemen": 246,
    "Jersey": 111,
    "Jordan": 112,
    "Južna Džodžija i Sandwich otoci": 206,
    "Južni Sudan": 207,
    "Južnoafricka Republika": 205,
    "Kajmanski otoci": 41,
    "Kambodža": 38,
    "Kamerun": 39,
    "Kanada": 40,

    "Kanarski otoci": None,

    "Katar": 179,
    "Kazahstan": 113,
    "Kenija": 114,
    "Kina": 45,
    "Kipar": 58,
    "Kirgistan": 120,
    "Kiribati": 115,
    "Kolumbija": 48,
    "Komori": 49,
    "Kongo (Dem.Rep.)": 51,
    "Kongo (Rep.)": 50,
    "Koreja (Dem.Rep.)": 116,
    "Koreja (Rep.)": 117,
    "Kosovo": 118,
    "Kostarika": 53,
    "Kuba": 56,
    "Kurakao": 57,
    "Kuvajt": 119,
    "Laos": 121,
    "Latvija": 122,
    "Lesoto": 124,
    "Liban": 123,
    "Liberija": 125,
    "Libija": 126,
    "Lihtenštajn": 127,
    "Litvanija": 128,
    "Luksemburg": 129,
    "Madagaskar": 131,

    "Madeira": None,

    "Mađarska": 99,
    "Makao, Kina": 130,
    "Malavi": 132,
    "Maldivi": 134,
    "Malezija": 133,
    "Mali": 135,
    "Malta": 136,
    "Maroko": 149,
    "MARSHALL ISLANDS": 137,
    "MARTINIQUE": 138,
    "Mauricijus": 140,
    "Mauritanija": 139,
    "MAYOTTE": 141,
    "Meksiko": 142,
    "Mianmar": 151,
    "MICRONESIA, FEDERATED STATES OF": 143,
    "Moldavija": 144,
    "Monako": 145,
    "Mongolija": 146,
    "MONTSERRAT": 148,
    "Mozambik": 150,
    "Namibija": 152,
    "Nauru": 153,
    "Nepal": 154,
    "Niger": 159,
    "Nigerija": 160,
    "Nikaragva": 158,
    "NIUE": 161,
    "NORFOLK ISLAND": 162,
    "NORTHERN MARIANA ISLANDS": 163,
    "Norveška": 165,
    "Nova Kaledonija": 156,
    "Novi Zeland": 157,
    "Njemacka": 83,
    "Obala Slonovace": 54,
    "Oman": 166,
    "Otok Man": 106,
    "Pakistan": 167,
    "PALAU": 168,
    "Palestina": 169,
    "Panama": 170,
    "Papua Nova Gvineja": 171,
    "Paragvaj": 172,
    "Peru": 173,
    "PITCAIRN": 175,

    "Polinezija": 78,
    "TAHITI": 78,

    "Poljska": 176,
    "Portoriko": 178,
    "Portugal": 177,
    "Republika Sjeverna Makedonija": 164,
    "REUNION": 180,

    "RIA": None,

    "Ruanda": 183,
    "Rumunija": 181,
    "Ruska Federacija": 182,
    "S. Martin": 188,
    "SAD Sjedinjene Americke Države": 235,
    "SAINT PIERRE AND MIQUELON": 189,
    "Salvador": 66,
    "Samoa": 191,
    "San Marino": 192,
    "Saudijska Arabija": 194,
    "Sejšeli": 197,
    "Senegal": 195,
    "Siera Leone": 198,
    "Singapur": 199,
    "Sirija": 215,
    "Slovacka": 201,
    "Slovenija": 202,
    "Solomonski otoci": 203,
    "Somalija": 204,
    "Srbija": 196,
    "Sudan": 210,
    "Surinam": 211,
    "SVALBARD AND JAN MAYEN": 212,

    "Sveta Helena": 185,
    "Sveta Lucija": 187,
    "Sveti Vincent i Grenadine": 190,
    "Sveti Barthelemy": 184,

    # Explicit exception:
    # SVETI EUSTATIUS -> BONAIRE #28
    "SVETI EUSTATIUS": 28,

    "Sveti Kits i Nevis": 186,
    "Sveti Tome i Principe": 193,

    "Španija": 208,
    "Šri Lanka": 209,
    "Švedska": 213,
    "Švicarska": 214,
    "Tadžikistan": 217,

    "TAHITI": 78,

    "Tajland": 219,
    "Tajvan - Kina": 216,
    "Tanzanija": 218,
    "Timor": 220,
    "Togo": 221,
    "TOKELAU": 222,
    "Tonga": 223,
    "Trinidad i Tobago": 224,

    "TRISTAN DA CUNHA": 185,
    "Tristan Da Cunha": 185,

    "Tunis": 225,
    "Turkmenistan": 227,
    "TURKS AND CAICOS ISLANDS": 228,
    "Turska": 226,
    "Tuvalu": 229,
    "Uganda": 230,
    "Ujedinjeni Arapski Emirati": 232,
    "Ukrajina": 231,
    "UNITED STATES MINOR OUTLYING ISLANDS": 236,
    "Urugvaj": 234,
    "Uzbekistan": 237,
    "Vanuatu": 238,
    "Vatikan": 239,
    "Velika Britanija": 233,
    "Venecuela": 240,
    "Vijetnam": 241,
    "VIRGIN ISLANDS, BRITISH": 242,

    # Explicit exception:
    # U.S. Virgin Islands -> Amer.Djevičanska Ostrva #243
    "VIRGIN ISLANDS, U.S.": 243,

    "Walis i Futuna": 244,
    "WALLIS AND FUTUNA": 244,
    "WESTERN SAHARA": 245,
    "Zambija": 247,
    "Zimbabve": 248,
}


# ============================================================
# NORMALIZATION
# ============================================================

def normalize_text(text):
    if text is None:
        return ""

    text = str(text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def normalize_country_name(text):
    """
    Normalize a country name for reliable comparison.

    Examples:

        Curaçao -> CURACAO
        Češka Republika -> CESKA REPUBLIKA
        Španija -> SPANIJA
    """

    text = normalize_text(text).upper()

    text = unicodedata.normalize("NFD", text)

    text = "".join(
        char
        for char in text
        if unicodedata.category(char) != "Mn"
    )

    # Handle letters that are not decomposed by NFD.
    text = text.replace("Đ", "D")
    text = text.replace("Ð", "D")

    # Normalize punctuation.
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


# ============================================================
# BUILD NORMALIZED LOOKUP
# ============================================================

NORMALIZED_BH_POSTA_TO_POSTCROSSING = {}

for country_name, number in BH_POSTA_TO_POSTCROSSING.items():
    normalized = normalize_country_name(country_name)
    NORMALIZED_BH_POSTA_TO_POSTCROSSING[normalized] = number


# ============================================================
# POSTCROSSING LOOKUP
# ============================================================

def get_postcrossing_numbers(country_name):
    """
    Return a list of Postcrossing number(s).

    Examples:

        Canada
            -> [40]

        Holandski Antili
            -> [13, 28, 57, 200]

        Unknown
            -> []
    """

    country_name = normalize_text(country_name)

    # Exact lookup.
    if country_name in BH_POSTA_TO_POSTCROSSING:
        value = BH_POSTA_TO_POSTCROSSING[country_name]

        if value is None:
            return []

        if isinstance(value, list):
            return value

        return [value]

    normalized = normalize_country_name(country_name)

    # Normalized lookup.
    if normalized in NORMALIZED_BH_POSTA_TO_POSTCROSSING:
        value = NORMALIZED_BH_POSTA_TO_POSTCROSSING[normalized]

        if value is None:
            return []

        if isinstance(value, list):
            return value

        return [value]

    # --------------------------------------------------------
    # Explicit exceptions
    # --------------------------------------------------------

    # Holandski Antili -> four destinations.
    if normalized == "HOLANDSKI ANTILI":
        return [13, 28, 57, 200]

    # Sveta Helena / Ascension / Tristan da Cunha -> #185.
    if (
        "SVETA HELENA" in normalized
        or "SAINT HELENA" in normalized
        or "ASCENSION" in normalized
        or "TRISTAN DA CUNHA" in normalized
    ):
        return [185]

    # U.S. Virgin Islands -> #243.
    if (
        "VIRGIN ISLANDS U S" in normalized
        or "US VIRGIN ISLANDS" in normalized
        or "UNITED STATES VIRGIN ISLANDS" in normalized
    ):
        return [243]

    # Tahiti -> French Polynesia #78.
    if "TAHITI" in normalized:
        return [78]

    # Saint Eustatius -> Bonaire #28.
    if (
        "SVETI EUSTATIUS" in normalized
        or "SAINT EUSTATIUS" in normalized
    ):
        return [28]

    return []


# ============================================================
# OUTPUT FORMATTING
# ============================================================

def format_country(country_name):
    """
    Convert one BH Posta destination into output line(s).

    Normal:
        Canada
        -> 40|Kanada

    Special:
        Holandski Antili
        -> 13|Aruba
           28|BONAIRE
           57|Curaçao
           200|Sint Maarten

    Unknown:
        Some Name
        -> ???|Some Name
    """

    country_name = normalize_text(country_name)

    numbers = get_postcrossing_numbers(country_name)

    if not numbers:
        return [f"???|{country_name}"]

    normalized = normalize_country_name(country_name)

    # --------------------------------------------------------
    # Holandski Antili is one BH Posta entry representing
    # four Postcrossing destinations.
    # --------------------------------------------------------

    if normalized == "HOLANDSKI ANTILI":
        return [
            "13|Aruba",
            "28|BONAIRE",
            "57|Curaçao",
            "200|Sint Maarten",
        ]

    # --------------------------------------------------------
    # All other destinations use the original BH Posta name
    # in the output.
    # --------------------------------------------------------

    return [
        f"{number}|{country_name}"
        for number in numbers
    ]


def is_known_country(country_name):
    return bool(get_postcrossing_numbers(country_name))


# ============================================================
# OUTPUT FILE
# ============================================================

def write_output_file(
    path,
    all_countries,
    suspended,
    unknown,
    errors,
):
    lines = []

    lines.append("========================================")
    lines.append("BH POSTA INTERNATIONAL DOPISNICA")
    lines.append("========================================")
    lines.append("")

    # --------------------------------------------------------
    # ALL COUNTRIES
    # --------------------------------------------------------

    lines.append("ALL COUNTRIES")
    lines.append("========================================")

    for country in all_countries:
        lines.extend(format_country(country))

    # --------------------------------------------------------
    # SUSPENDED
    # --------------------------------------------------------

    lines.append("")
    lines.append("SUSPENDED COUNTRIES")
    lines.append("========================================")

    if suspended:
        for country in suspended:
            lines.extend(format_country(country))
    else:
        lines.append("(none)")

    # --------------------------------------------------------
    # UNKNOWN
    # --------------------------------------------------------

    lines.append("")
    lines.append("UNKNOWN COUNTRIES")
    lines.append("========================================")

    if unknown:
        for country in unknown:
            lines.extend(format_country(country))
    else:
        lines.append("(none)")

    # --------------------------------------------------------
    # ERRORS
    # --------------------------------------------------------

    lines.append("")
    lines.append("ERROR COUNTRIES")
    lines.append("========================================")

    if errors:
        for country in errors:
            lines.extend(format_country(country))
    else:
        lines.append("(none)")

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    lines.append("")
    lines.append("SUMMARY")
    lines.append("========================================")
    lines.append(
        f"BH Posta countries: {len(all_countries)}"
    )
    lines.append(
        f"Suspended: {len(suspended)}"
    )
    lines.append(
        f"Unknown: {len(unknown)}"
    )
    lines.append(
        f"Errors: {len(errors)}"
    )

    unmapped = [
        country
        for country in all_countries
        if not is_known_country(country)
    ]

    lines.append(
        f"Countries without Postcrossing mapping: "
        f"{len(unmapped)}"
    )

    if unmapped:
        lines.append("")
        lines.append("UNMAPPED COUNTRY NAMES")
        lines.append("========================================")

        for country in unmapped:
            lines.append(f"???|{country}")

    path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


# ============================================================
# DEBUG HELPERS
# ============================================================

def save_debug(page, filename):
    try:
        Path(filename).write_text(
            page.content(),
            encoding="utf-8",
        )

        print(f"Saved debug file: {filename}")

    except Exception as exc:
        print(
            f"Could not save debug file "
            f"{filename}: {exc}"
        )


def selector_exists(page, selector):
    try:
        return page.locator(selector).count() > 0
    except Exception:
        return False


def runtime_exceeded(start_time):
    return (
        time.monotonic() - start_time
    ) >= MAX_RUNTIME_SECONDS


def get_visible_text(page):
    try:
        return normalize_text(
            page.locator("body").inner_text(
                timeout=3000
            )
        )
    except Exception:
        return ""


def get_result_text(page):
    selectors = [
        "#lblMeDoRezultat",
        "#lblMeDoCijena",
        "#lblMeDoUkupnaCijena",
        "[id*='Rezultat']",
        "[id*='Cijena']",
        "[id*='Price']",
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
    text = get_visible_text(page)

    if SUSPENDED_MESSAGE in text:
        return SUSPENDED_MESSAGE

    return ""


# ============================================================
# INTERNATIONAL TAB
# ============================================================

def select_international_tab(page):
    print("Selecting international traffic tab...")

    tab_control = page.locator(
        "#ASPxTabControl1"
    )

    if tab_control.count() > 0:
        names = [
            "Međunarodni promet",
            "Međunarodni",
            "Medjunarodni promet",
            "Medjunarodni",
        ]

        for name in names:
            try:
                locator = tab_control.get_by_text(
                    name,
                    exact=True,
                )

                if locator.count() > 0:
                    locator.first.click()

                    page.wait_for_timeout(1200)

                    try:
                        page.wait_for_load_state(
                            "networkidle",
                            timeout=10000,
                        )
                    except Exception:
                        pass

                    save_debug(
                        page,
                        "debug_after_international.html",
                    )

                    return

            except Exception:
                pass

    fallback_selectors = [
        "#ASPxTabControl1 .dxtc-tab",
        "#ASPxTabControl1 .dxtc-tabLink",
        "#ASPxTabControl1 td[id*='T1']",
        "#ASPxTabControl1 [id*='T1']",
    ]

    for selector in fallback_selectors:
        try:
            locator = page.locator(selector)

            if locator.count() > 0:
                locator.first.click()

                page.wait_for_timeout(1200)

                try:
                    page.wait_for_load_state(
                        "networkidle",
                        timeout=10000,
                    )
                except Exception:
                    pass

                save_debug(
                    page,
                    "debug_after_international.html",
                )

                return

        except Exception:
            pass

    raise RuntimeError(
        "Could not select the international traffic tab."
    )


# ============================================================
# DOPISNICA
# ============================================================

def select_dopisnica(page):
    print("Selecting Dopisnica...")

    active = page.locator(
        "img[src*='Dopisnica_Aktivna.png']"
    )

    if active.count() > 0:
        print("Dopisnica already active.")
        return

    selectors = [
        "#ImageButton8",
        "input#ImageButton8",
        "input[name='ImageButton8']",
        "input[id$='ImageButton8']",
        "img[src*='Dopisnica']",
    ]

    for selector in selectors:
        try:
            locator = page.locator(selector)

            if locator.count() > 0:
                locator.first.click()

                page.wait_for_timeout(1200)

                try:
                    page.wait_for_load_state(
                        "networkidle",
                        timeout=10000,
                    )
                except Exception:
                    pass

                return

        except Exception:
            pass

    # JavaScript fallback.
    try:
        clicked = page.evaluate(
            """
            () => {
                const el =
                    document.getElementById('ImageButton8');

                if (el) {
                    el.click();
                    return true;
                }

                return false;
            }
            """
        )

        if clicked:
            page.wait_for_timeout(1200)
            return

    except Exception:
        pass

    raise RuntimeError(
        "Could not select Dopisnica."
    )


# ============================================================
# AIR TRANSPORT
# ============================================================

def select_air_transport(page):
    print("Selecting air transport...")

    selector = f"#{AIR_CHECKBOX}"

    try:
        checkbox = page.locator(selector)

        if checkbox.count() == 0:
            raise RuntimeError(
                f"Air transport checkbox not found: "
                f"{selector}"
            )

        if not checkbox.is_checked():
            checkbox.check()

        page.wait_for_timeout(500)

    except Exception as exc:
        raise RuntimeError(
            f"Could not select air transport: {exc}"
        )


# ============================================================
# WEIGHT
# ============================================================

def set_weight(page):
    print(f"Setting weight to {WEIGHT}...")

    selector = f"#{AIR_WEIGHT}"

    try:
        field = page.locator(selector)

        if field.count() == 0:
            raise RuntimeError(
                f"Weight field not found: {selector}"
            )

        field.fill(WEIGHT)

        page.wait_for_timeout(250)

    except Exception as exc:
        raise RuntimeError(
            f"Could not set weight: {exc}"
        )


# ============================================================
# DESTINATIONS
# ============================================================

def get_destinations(page):
    selector = f"select#{DESTINATION_SELECT}"

    locator = page.locator(selector)

    if locator.count() == 0:
        raise RuntimeError(
            f"Destination selector not found: {selector}"
        )

    options = locator.locator("option")

    destinations = []

    for i in range(options.count()):
        option = options.nth(i)

        try:
            value = option.get_attribute("value")
            name = normalize_text(
                option.inner_text()
            )

            if value is None:
                continue

            if not name:
                continue

            destinations.append(
                (value, name)
            )

        except Exception:
            continue

    return destinations


def select_country(page, code):
    selector = f"select#{DESTINATION_SELECT}"

    page.locator(selector).select_option(
        value=code
    )

    page.wait_for_timeout(
        COUNTRY_WAIT_MS
    )


# ============================================================
# CALCULATE
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
            locator = page.locator(selector)

            if locator.count() > 0:
                locator.first.click()

                page.wait_for_timeout(450)

                return

        except Exception:
            pass

    raise RuntimeError(
        "Could not find the calculate button."
    )


def parse_price(text):
    if not text:
        return None

    # Prefer "Ukupna cijena ... KM".
    match = re.search(
        r"Ukupna\s+cijena.*?"
        r"([0-9]+(?:[.,][0-9]+)?)\s*KM",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    if match:
        value = match.group(1).replace(
            ",",
            ".",
        )

        return float(value)

    # Fallback: any number followed by KM.
    matches = re.findall(
        r"([0-9]+(?:[.,][0-9]+)?)\s*KM",
        text,
        flags=re.IGNORECASE,
    )

    if matches:
        value = matches[-1].replace(
            ",",
            ".",
        )

        return float(value)

    return None


def calculate_country(page, code):
    select_country(
        page,
        code,
    )

    # The destination change can rebuild the weight field.
    if selector_exists(
        page,
        f"#{AIR_WEIGHT}",
    ):
        set_weight(page)

    click_calculate(page)

    result_text = get_result_text(page)
    error_text = get_error_text(page)

    if SUSPENDED_MESSAGE in result_text:
        return (
            "SUSPENDED",
            result_text,
        )

    if error_text:
        return (
            "SUSPENDED",
            error_text,
        )

    price = parse_price(result_text)

    if price is None:
        return (
            "UNKNOWN",
            result_text,
        )

    if price <= 0:
        return (
            "UNKNOWN",
            result_text,
        )

    return (
        "AVAILABLE",
        result_text,
    )


# ============================================================
# MAIN
# ============================================================

def main():
    start_time = time.monotonic()

    all_countries = []
    suspended = []
    unknown = []
    errors = []

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
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/151.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            viewport={
                "width": 1440,
                "height": 1000,
            },
        )

        page = context.new_page()

        try:
            # ------------------------------------------------
            # Open BH Posta.
            # ------------------------------------------------

            print("Opening BH Posta...")

            page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            page.wait_for_timeout(1500)

            save_debug(
                page,
                "debug_original.html",
            )

            # ------------------------------------------------
            # Select international traffic.
            # ------------------------------------------------

            select_international_tab(page)

            # ------------------------------------------------
            # Select Dopisnica.
            # ------------------------------------------------

            select_dopisnica(page)

            # ------------------------------------------------
            # Read destinations.
            # ------------------------------------------------

            destinations = get_destinations(page)

            if not destinations:
                raise RuntimeError(
                    "No destination countries found."
                )

            # ------------------------------------------------
            # Select air transport and weight.
            # ------------------------------------------------

            select_air_transport(page)

            set_weight(page)

            # ------------------------------------------------
            # Re-read destinations because the page can
            # dynamically rebuild the select element.
            # ------------------------------------------------

            destinations = get_destinations(page)

            all_countries = [
                country
                for _, country in destinations
            ]

            print(
                f"Found {len(destinations)} "
                f"BH Posta destinations."
            )

            # ------------------------------------------------
            # Display mapping information.
            # ------------------------------------------------

            print("")
            print(
                "Checking Postcrossing mappings..."
            )

            for _, country in destinations:
                numbers = get_postcrossing_numbers(
                    country
                )

                if not numbers:
                    print(
                        f"WARNING: No Postcrossing "
                        f"mapping: {country}"
                    )
                else:
                    mapped = ", ".join(
                        str(number)
                        for number in numbers
                    )

                    print(
                        f"  {country} -> {mapped}"
                    )

            # ------------------------------------------------
            # Check each BH Posta destination.
            # ------------------------------------------------

            print("")
            print(
                "Checking countries..."
            )

            for index, (code, country) in enumerate(
                destinations,
                start=1,
            ):
                if runtime_exceeded(start_time):
                    print(
                        "Maximum runtime reached. "
                        "Stopping country checks."
                    )
                    break

                print(
                    f"[{index}/{len(destinations)}] "
                    f"{country}"
                )

                try:
                    status, result = calculate_country(
                        page,
                        code,
                    )

                    if status == "SUSPENDED":
                        suspended.append(country)

                        print(
                            "  -> SUSPENDED"
                        )

                    elif status == "UNKNOWN":
                        unknown.append(country)

                        print(
                            "  -> UNKNOWN"
                        )

                        print(
                            f"     Result: "
                            f"{result[:300]}"
                        )

                    elif status == "AVAILABLE":
                        print(
                            "  -> AVAILABLE"
                        )

                    else:
                        unknown.append(country)

                        print(
                            f"  -> UNKNOWN STATUS: "
                            f"{status}"
                        )

                except Exception as exc:
                    errors.append(country)

                    print(
                        f"  -> ERROR: {exc}"
                    )

                    # ----------------------------------------
                    # Attempt recovery.
                    # ----------------------------------------

                    try:
                        print(
                            "  Attempting page recovery..."
                        )

                        page.reload(
                            wait_until="domcontentloaded",
                            timeout=30000,
                        )

                        page.wait_for_timeout(1000)

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
                            "  Recovery successful."
                        )

                    except Exception as recovery_exc:
                        print(
                            "  Recovery failed: "
                            f"{recovery_exc}"
                        )

                time.sleep(0.15)

            # ------------------------------------------------
            # Write results.
            # ------------------------------------------------

            write_output_file(
                OUTPUT_FILE,
                all_countries,
                suspended,
                unknown,
                errors,
            )

            # ------------------------------------------------
            # Final summary.
            # ------------------------------------------------

            print("")
            print(
                "========================================"
            )
            print(
                "MONITOR COMPLETE"
            )
            print(
                "========================================"
            )

            print(
                f"BH Posta countries: "
                f"{len(all_countries)}"
            )

            print(
                f"Suspended: "
                f"{len(suspended)}"
            )

            print(
                f"Unknown: "
                f"{len(unknown)}"
            )

            print(
                f"Errors: "
                f"{len(errors)}"
            )

            unmapped = [
                country
                for country in all_countries
                if not is_known_country(country)
            ]

            print(
                f"Without Postcrossing mapping: "
                f"{len(unmapped)}"
            )

            if unmapped:
                print("")
                print(
                    "Unmapped countries:"
                )

                for country in unmapped:
                    print(
                        f"  ???|{country}"
                    )

            print("")
            print(
                f"Output file: "
                f"{OUTPUT_FILE}"
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
        print("Interrupted.")
        sys.exit(130)

    except Exception as exc:
        print(
            f"FATAL ERROR: {exc}"
        )
        sys.exit(1)
