#!/usr/bin/env python3
"""
monitor.py - BH Posta international Dopisnica (postcard) monitor.

Flow:
  1. Open the BH Posta calculator
  2. Click the "Međunarodni promet" tab
  3. Select Dopisnica
  4. For every destination in the "odredišna zemlja" drop-down:
       select "I stopa: do 20g" and click "Izračunaj"
  5. Write bh_posta_output.txt (no timestamps, so only real changes show up)

Safety: if the page or the drop-down cannot be read, or too many checks fail,
the script exits with an error and does NOT overwrite the output file.
"""

import re
import sys
import time
import unicodedata
from pathlib import Path

from playwright.sync_api import sync_playwright

# ============================================================
# CONFIG
# ============================================================

URL = "https://bhpwebout.posta.ba/KalkulatorCijena_WEB_app/Bos/Default.aspx"
OUTPUT_FILE = "bh_posta_output.txt"

TAB_SELECTOR = "#ASPxTabControl1_AT1T"          # "Međunarodni promet"
CALCULATE_SELECTOR = "#btnMeObPiIzracunaj"       # "Izračunaj"

# Tried in order after the tab is opened. First visible match is clicked.
DOPISNICA_SELECTORS = [
    'input[alt*="opisnica" i]',
    'input[title*="opisnica" i]',
    'img[alt*="opisnica" i]',
    'a:has-text("Dopisnica")',
    'text=Dopisnica',
    "#ImageButton8",
]

MIN_DESTINATION_OPTIONS = 100     # a select with this many options = country list
MIN_DESTINATIONS_SANITY = 150     # fewer than this = something is wrong, abort
MAX_ERRORS_ALLOWED = 5
RETRIES_PER_COUNTRY = 3
RESULT_WAIT_SECONDS = 8
MAX_RUNTIME_SECONDS = 25 * 60

SUSPENDED_MESSAGE_NORMALIZED = "PRIJEM POSILJAKA SE TRENUTNO NE VRSI"

IGNORED_DESTINATIONS = [
    "Azori",
    "BOUVET ISLAND",
    "Channel Islands",
    "HEARD ISLAND AND MCDONALD ISLANDS",
    "Italijanske poste",
    "Kanarski Otoci",
    "Madeira",
    "RIA",
]

# Dropdown names that stand for several Postcrossing destinations.
MULTI_ALIASES = {
    "HOLANDSKI ANTILI": [28, 57, 200],
    "NETHERLANDS ANTILLES": [28, 57, 200],
}

# ============================================================
# MASTER LIST:  number | Postcrossing name | local name; alias; alias ...
# The first alias is the local (Bosnian) name used for destinations that are
# missing from the BH Posta drop-down. All names are matched without
# diacritics, case or punctuation.
# ============================================================

MASTER_TABLE = """
1|Afghanistan|Afganistan
2|Åland Islands|Alandska ostrva; Aland
3|Albania|Albanija
4|Algeria|Alžir
5|American Samoa|Američka Samoa
6|Andorra|Andora
7|Angola|Angola
8|Anguilla|Angvila; Anguila
9|Antarctica|Antarktik; Antarktika
10|Antigua & Barbuda|Antigva i Barbuda; Antigua and Barbuda
11|Argentina|Argentina
12|Armenia|Armenija
13|Aruba|Aruba
14|Australia|Australija
15|Austria|Austrija
16|Azerbaijan|Azerbejdžan
17|Bahamas|Bahami
18|Bahrain|Bahrein
19|Bangladesh|Bangladeš
20|Barbados|Barbados
21|Belarus|Bjelorusija
22|Belgium|Belgija
23|Belize|Belize
24|Benin|Benin
25|Bermuda|Bermudi
26|Bhutan|Butan
27|Bolivia|Bolivija
28|Bonaire, Sint Eustatius and Saba|Bonaire; Sint Eustatius; Saint Eustatius; Sveti Eustatius; Saba
29|Bosnia-Herzegovina|Bosna i Hercegovina; Bosnia and Herzegovina
30|Botswana|Bocvana
31|Brazil|Brazil
32|British Indian Ocean Territory|Britanska teritorija Indijskog okeana
33|Brunei|Brunej; Brunei Darussalam
34|Bulgaria|Bugarska
35|Burkina Faso|Burkina Faso
36|Burundi|Burundi
37|Cabo Verde|Zelenortska Ostrva; Cape Verde
38|Cambodia|Kambodža
39|Cameroon|Kamerun
40|Canada|Kanada
41|Cayman Islands|Kajmanska ostrva
42|Central African Republic|Centralnoafrička Republika
43|Chad|Čad
44|Chile|Čile
45|China|Kina
46|Christmas Island|Božićno ostrvo
47|Cocos Islands|Kokosova ostrva; Cocos (Keeling) Islands
48|Colombia|Kolumbija
49|Comoros|Komori
50|Congo|Kongo; Congo (Rep.)
51|Dem. Rep. of Congo|Demokratska Republika Kongo; Congo (Dem. Rep.); Democratic Republic of the Congo
52|Cook Islands|Cookova ostrva
53|Costa Rica|Kostarika
54|Côte d'Ivoire|Obala Slonovače; Cote dIvoir; Cote dIvoire; Ivory Coast
55|Croatia|Hrvatska
56|Cuba|Kuba
57|Curaçao|Curacao
58|Cyprus|Kipar
59|Czechia|Češka; Czech Republic
60|Denmark|Danska
61|Djibouti|Džibuti
62|Dominica|Dominika
63|Dominican Republic|Dominikanska Republika
64|Ecuador|Ekvador
65|Egypt|Egipat
66|El Salvador|El Salvador
67|Equatorial Guinea|Ekvatorijalna Gvineja
68|Eritrea|Eritreja
69|Estonia|Estonija
70|Eswatini / Swaziland|Svazilend; Eswatini; Swaziland
71|Ethiopia|Etiopija
72|Falkland Islands / Malvinas|Falklandska ostrva; Falkland Islands
73|Faroe Islands|Farska ostrva
74|Fiji|Fidži
75|Finland|Finska
76|France|Francuska
77|French Guiana|Francuska Gvajana
78|French Polynesia|Francuska Polinezija; Tahiti
79|French Southern Territories|Francuske južne teritorije
80|Gabon|Gabon
81|Gambia|Gambija
82|Georgia|Gruzija
83|Germany|Njemačka
84|Ghana|Gana
85|Gibraltar|Gibraltar
86|Greece|Grčka
87|Greenland|Grenland
88|Grenada|Grenada
89|Guadeloupe|Gvadalupe
90|Guam|Guam
91|Guatemala|Gvatemala
92|Guernsey|Guernsey
93|Guinea|Gvineja
94|Guinea-Bissau|Gvineja Bisau
95|Guyana|Gvajana
96|Haiti|Haiti
97|Honduras|Honduras
98|Hong Kong|Hong Kong
99|Hungary|Mađarska
100|Iceland|Island
101|India|Indija
102|Indonesia|Indonezija
103|Iran|Iran
104|Iraq|Irak
105|Ireland|Irska
106|Isle of Man|Otok Man
107|Israel|Izrael
108|Italy|Italija
109|Jamaica|Jamajka
110|Japan|Japan
111|Jersey|Jersey
112|Jordan|Jordan
113|Kazakhstan|Kazahstan
114|Kenya|Kenija
115|Kiribati|Kiribati
116|Korea (North)|Sjeverna Koreja; Dem. People's Rep. of Korea; Korea (Dem. People's Rep.)
117|Korea (South)|Južna Koreja; Korea (Rep.)
118|Kosovo|Kosovo
119|Kuwait|Kuvajt
120|Kyrgyzstan|Kirgistan
121|Laos|Laos
122|Latvia|Latvija
123|Lebanon|Liban
124|Lesotho|Lesoto
125|Liberia|Liberija
126|Libya|Libija
127|Liechtenstein|Lihtenštajn
128|Lithuania|Litvanija
129|Luxembourg|Luksemburg
130|Macao|Makao
131|Madagascar|Madagaskar
132|Malawi|Malavi
133|Malaysia|Malezija
134|Maldives|Maldivi
135|Mali|Mali
136|Malta|Malta
137|Marshall Islands|Maršalova ostrva
138|Martinique|Martinik
139|Mauritania|Mauritanija
140|Mauritius|Mauricijus
141|Mayotte|Majot
142|Mexico|Meksiko
143|Micronesia|Mikronezija
144|Moldova|Moldavija
145|Monaco|Monako
146|Mongolia|Mongolija
147|Montenegro|Crna Gora
148|Montserrat|Montserrat
149|Morocco|Maroko
150|Mozambique|Mozambik
151|Myanmar|Mjanmar; Burma
152|Namibia|Namibija
153|Nauru / Naoero|Nauru
154|Nepal|Nepal
155|Netherlands|Nizozemska; Holandija
156|New Caledonia|Nova Kaledonija
157|New Zealand|Novi Zeland
158|Nicaragua|Nikaragva
159|Niger|Niger
160|Nigeria|Nigerija
161|Niue|Niue
162|Norfolk Island|Norfolk
163|Northern Mariana Islands|Sjeverna Marijanska ostrva
164|North Macedonia|Sjeverna Makedonija
165|Norway|Norveška
166|Oman|Oman
167|Pakistan|Pakistan
168|Palau|Palau
169|Palestine|Palestina
170|Panama|Panama
171|Papua New Guinea|Papua Nova Gvineja
172|Paraguay|Paragvaj
173|Peru|Peru
174|Philippines|Filipini
175|Pitcairn|Pitcairn
176|Poland|Poljska
177|Portugal|Portugal
178|Puerto Rico|Portoriko
179|Qatar|Katar
180|Réunion|Reunion
181|Romania|Rumunija
182|Russia|Rusija
183|Rwanda|Ruanda
184|Saint Barthélemy|Sveti Bartolomej
185|Saint Helena, Ascension and Tristan da Cunha|Sveta Helena; Saint Helena; Ascension; Tristan da Cunha
186|Saint Kitts and Nevis|Sveti Kits i Nevis
187|Saint Lucia|Sveta Lucija
188|Saint Martin|Sveti Martin
189|Saint Pierre & Miquelon|Sveti Pierre i Miquelon
190|Saint Vincent and the Grenadines|Sveti Vincent i Grenadini
191|Samoa|Samoa
192|San Marino|San Marino
193|Sao Tome and Principe|Sao Tome i Principe
194|Saudi Arabia|Saudijska Arabija
195|Senegal|Senegal
196|Serbia|Srbija
197|Seychelles|Sejšeli
198|Sierra Leone|Sijera Leone
199|Singapore|Singapur
200|Sint Maarten|Sint Maarten
201|Slovakia|Slovačka
202|Slovenia|Slovenija
203|Solomon Islands|Solomonska Ostrva
204|Somalia|Somalija
205|South Africa|Južnoafrička Republika; Južna Afrika
206|South Georgia and S. Sandwich Islands|Južna Georgija
207|South Sudan|Južni Sudan
208|Spain|Španija
209|Sri Lanka|Šri Lanka
210|Sudan|Sudan
211|Suriname|Surinam
212|Svalbard and Jan Mayen|Svalbard
213|Sweden|Švedska
214|Switzerland|Švicarska
215|Syria|Sirija
216|Taiwan|Tajvan
217|Tajikistan|Tadžikistan
218|Tanzania|Tanzanija
219|Thailand|Tajland
220|Timor-Leste|Istočni Timor; East Timor
221|Togo|Togo
222|Tokelau|Tokelau
223|Tonga|Tonga
224|Trinidad and Tobago|Trinidad i Tobago
225|Tunisia|Tunis
226|Turkey|Turska; Türkiye
227|Turkmenistan|Turkmenistan
228|Turks and Caicos Islands|Turks i Caicos
229|Tuvalu|Tuvalu
230|Uganda|Uganda
231|Ukraine|Ukrajina
232|United Arab Emirates|Ujedinjeni Arapski Emirati
233|United Kingdom|Ujedinjeno Kraljevstvo; Great Britain; Velika Britanija
234|Uruguay|Urugvaj
235|U.S.A.|Sjedinjene Američke Države; SAD; USA; United States
236|U.S. Minor Outlying Islands|Američka vanjska ostrva
237|Uzbekistan|Uzbekistan
238|Vanuatu|Vanuatu
239|Vatican|Vatikan; Holy See; Sveta Stolica
240|Venezuela|Venecuela
241|Vietnam|Vijetnam
242|Virgin Islands (UK)|Britanska Djevičanska Ostrva; British Virgin Islands
243|Virgin Islands of the USA|Američka Djevičanska Ostrva; Virgin Islands, U.S.; Virgin Islands, US; Virgin Islands
244|Wallis & Futuna|Wallis i Futuna
245|Western Sahara|Zapadna Sahara
246|Yemen|Jemen
247|Zambia|Zambija
248|Zimbabwe|Zimbabve
"""

# ============================================================
# HELPERS
# ============================================================


def log(message=""):
    print(message, flush=True)


def normalize(text):
    if not text:
        return ""
    text = text.replace("&", " AND ").replace("'", "").replace("\u2019", "")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.upper().replace("Đ", "D").replace("Ł", "L")
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return " ".join(text.split())


def load_master():
    english = {}
    local = {}
    alias_map = {}
    for line in MASTER_TABLE.strip().splitlines():
        parts = line.split("|")
        number = int(parts[0])
        name = parts[1].strip()
        aliases = [a.strip() for a in parts[2].split(";") if a.strip()]
        english[number] = name
        local[number] = aliases[0] if aliases else name

        names = [name] + aliases
        for part in name.split("/"):
            names.append(part.strip())
        for candidate in names:
            key = normalize(candidate)
            if key and key not in alias_map:
                alias_map[key] = [number]
    return english, local, alias_map


ENGLISH, LOCAL, ALIAS_MAP = load_master()
IGNORED_KEYS = {normalize(x) for x in IGNORED_DESTINATIONS}


def lookup_numbers(dropdown_name):
    key = normalize(dropdown_name)
    if key in MULTI_ALIASES:
        return list(MULTI_ALIASES[key])
    return list(ALIAS_MAP.get(key, []))


def is_placeholder(value, text):
    if not value or not value.strip():
        return True
    t = text.strip()
    if not t or t.startswith("-") or t.startswith("*"):
        return True
    if normalize(t).startswith("ODABERI"):
        return True
    return False


# ============================================================
# PAGE HELPERS
# ============================================================

FIND_SELECTS_JS = """
() => Array.from(document.querySelectorAll('select')).map(s => ({
    id: s.id,
    name: s.name,
    visible: !!(s.offsetParent),
    n: s.options.length,
    opts: Array.from(s.options).map(o => [o.value, o.text])
}))
"""


def wait_idle(page, timeout=10000):
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:
        pass


def body_text(page):
    try:
        return page.locator("body").inner_text(timeout=5000)
    except Exception:
        return ""


def dump_debug(page, label="debug"):
    try:
        Path(f"{label}_page.html").write_text(page.content(), encoding="utf-8")
        page.screenshot(path=f"{label}_screenshot.png", full_page=True)
        log(f"  (saved {label}_page.html and {label}_screenshot.png)")
    except Exception as exc:
        log(f"  (could not save debug files: {exc})")


def select_css(info):
    if info.get("id"):
        return f'select[id="{info["id"]}"]'
    return f'select[name="{info["name"]}"]'


def find_controls(page):
    try:
        info = page.evaluate(FIND_SELECTS_JS)
    except Exception:
        return None

    dest = None
    for s in info:
        if s["visible"] and s["n"] >= MIN_DESTINATION_OPTIONS:
            if dest is None or s["n"] > dest["n"]:
                dest = s
    if dest is None:
        return None

    weight_css = None
    weight_value = None
    for s in info:
        if not s["visible"] or s is dest:
            continue
        for value, text in s["opts"]:
            if re.match(r"\s*I\s*stopa", text, re.I):
                weight_css = select_css(s)
                weight_value = value
                break
        if weight_css:
            break

    return {
        "dest": select_css(dest),
        "weight": weight_css,
        "weight_value": weight_value,
    }


def wait_for_controls(page, seconds):
    deadline = time.time() + seconds
    while time.time() < deadline:
        ctl = find_controls(page)
        if ctl:
            return ctl
        time.sleep(0.5)
    return None


def click_tab(page):
    try:
        page.locator(TAB_SELECTOR).click(timeout=10000)
    except Exception:
        page.locator("text=Međunarodni promet").first.click(timeout=10000)
    time.sleep(0.5)
    wait_idle(page)


def click_dopisnica(page):
    for selector in DOPISNICA_SELECTORS:
        try:
            loc = page.locator(selector).first
            if loc.count() and loc.is_visible():
                loc.click(timeout=5000)
                time.sleep(0.5)
                wait_idle(page)
                log(f"  Dopisnica selected using: {selector}")
                return True
        except Exception:
            continue
    log("  WARNING: Dopisnica button not found; continuing with page default.")
    return False


def setup(page):
    page.goto(URL, wait_until="domcontentloaded", timeout=60000)
    wait_idle(page)
    click_tab(page)
    click_dopisnica(page)

    ctl = wait_for_controls(page, 8)
    if not ctl:
        click_tab(page)
        ctl = wait_for_controls(page, 20)
    if not ctl:
        dump_debug(page, "debug_setup")
        raise RuntimeError("Could not find the destination drop-down.")
    return ctl


def read_destinations(page, ctl):
    options = page.locator(ctl["dest"]).locator("option")
    result = []
    for i in range(options.count()):
        opt = options.nth(i)
        value = opt.get_attribute("value")
        text = opt.inner_text().strip()
        if is_placeholder(value, text):
            continue
        result.append((value, text))
    return result


# ============================================================
# RESULT PARSING
# ============================================================


def parse_result(text):
    """Return (status, price, delivery). Status: AVAILABLE, SUSPENDED, PENDING."""
    if SUSPENDED_MESSAGE_NORMALIZED in normalize(text):
        return "SUSPENDED", None, None

    idx = text.lower().find("ukupna cijena")
    if idx < 0:
        return "PENDING", None, None

    segment = text[idx:]
    price_m = re.search(r"(\d[\d.]*[,.]\d{2})\s*(?:KM|BAM)", segment, re.I)
    time_m = re.search(
        r"(\d+\s*[-\u2013\u2014]\s*\d+|\d+)\s*(?:radn\w*\s+)?dan\w*",
        segment,
        re.I,
    )
    if price_m and time_m:
        price = price_m.group(1) + "KM"
        delivery = re.sub(r"\s*[-\u2013\u2014]\s*", "-", time_m.group(1)).strip()
        return "AVAILABLE", price, delivery
    return "PENDING", None, None


def read_result(page):
    deadline = time.time() + RESULT_WAIT_SECONDS
    while True:
        status, price, delivery = parse_result(body_text(page))
        if status != "PENDING":
            return status, price, delivery
        if time.time() > deadline:
            # Neither a price + delivery time nor a message: treat as suspended.
            return "SUSPENDED", None, None
        time.sleep(0.5)


def check_country(page, ctl, value):
    page.locator(ctl["dest"]).select_option(value=value)
    time.sleep(0.4)
    wait_idle(page)

    if ctl["weight"]:
        weight = page.locator(ctl["weight"])
        if weight.input_value() != ctl["weight_value"]:
            weight.select_option(value=ctl["weight_value"])
            time.sleep(0.4)
            wait_idle(page)

    with page.expect_response(
        lambda r: r.request.method == "POST", timeout=20000
    ):
        page.locator(CALCULATE_SELECTOR).click(timeout=10000)

    wait_idle(page)
    time.sleep(0.3)
    return read_result(page)


# ============================================================
# REPORT
# ============================================================


def build_report(results):
    groups = {}
    first_index = {}
    unmapped = []

    for idx, entry in enumerate(results):
        numbers = lookup_numbers(entry["name"])
        if not numbers:
            unmapped.append(entry)
            continue
        for n in numbers:
            groups.setdefault(n, []).append(entry)
            first_index.setdefault(n, idx)

    available = []
    suspended_a = []
    errors = []

    for n in sorted(groups, key=lambda x: first_index[x]):
        entries = groups[n]

        if n == 185:
            bad = [
                e
                for e in entries
                if re.search(r"ASCENSION|TRISTAN", e["norm"])
                and e["status"] != "AVAILABLE"
            ]
            if bad:
                labels = []
                for e in bad:
                    if "ASCENSION" in e["norm"] and "TRISTAN" not in e["norm"]:
                        labels.append("Ascension")
                    elif "TRISTAN" in e["norm"] and "ASCENSION" not in e["norm"]:
                        labels.append("Tristan da Cunha")
                    else:
                        labels.append(e["name"])
                verb = "is" if len(labels) == 1 else "are"
                suspended_a.append(
                    f"185. {ENGLISH[185]} ({' and '.join(labels)} {verb} suspended)"
                )
                continue

        ok = [e for e in entries if e["status"] == "AVAILABLE"]
        if ok:
            e = ok[0]
            available.append(
                f"{n}. {e['name']} ({ENGLISH[n]}) {e['price']} {e['delivery']} days"
            )
        elif any(e["status"] == "ERROR" for e in entries):
            errors.append(f"{n}. {entries[0]['name']} ({ENGLISH[n]})")
        else:
            suspended_a.append(f"{n}. {entries[0]['name']} ({ENGLISH[n]})")

    missing = [
        f"{n}. {LOCAL[n]} ({ENGLISH[n]})"
        for n in sorted(ENGLISH)
        if n not in groups
    ]

    unmapped_lines = [f"{e['name']}  [{e['status']}]" for e in unmapped]

    def block(title, lines):
        out = [title, "=" * 80]
        out.extend(lines if lines else ["None"])
        out.extend(["", ""])
        return out

    lines = []
    lines += block(
        "AVAILABLE DESTINATIONS (order of BH Posta drop-down)", available
    )
    lines += block(
        "SUSPENDED DESTINATIONS - A) NO PRICE QUOTE (order of BH Posta drop-down)",
        suspended_a,
    )
    lines += block(
        "SUSPENDED DESTINATIONS - B) MISSING FROM BH POSTA DROP-DOWN "
        "(Postcrossing number order)",
        missing,
    )
    lines += block(
        "UNMAPPED BH POSTA NAMES (add an alias in monitor.py)", unmapped_lines
    )
    lines += block("CHECK ERRORS (could not be checked)", errors)
    lines += [
        "SUMMARY",
        "=" * 80,
        f"AVAILABLE: {len(available)}",
        f"SUSPENDED A (no price quote): {len(suspended_a)}",
        f"SUSPENDED B (missing from drop-down): {len(missing)}",
        f"UNMAPPED: {len(unmapped_lines)}",
        f"ERRORS: {len(errors)}",
    ]

    return "\n".join(lines) + "\n", len(available), len(errors)


# ============================================================
# MAIN
# ============================================================


def main():
    start = time.time()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = browser.new_context(
            locale="bs-BA", viewport={"width": 1366, "height": 900}
        )
        page = context.new_page()
        page.set_default_timeout(30000)

        try:
            log("Opening BH Posta calculator...")
            ctl = setup(page)

            raw = read_destinations(page, ctl)
            log(f"Drop-down entries found: {len(raw)}")

            destinations = []
            seen = set()
            for value, text in raw:
                key = normalize(text)
                if key in IGNORED_KEYS:
                    log(f"  ignoring: {text}")
                    continue
                if key in seen:
                    log(f"  duplicate skipped: {text}")
                    continue
                seen.add(key)
                destinations.append((value, text))

            if len(destinations) < MIN_DESTINATIONS_SANITY:
                dump_debug(page, "debug_dropdown")
                raise RuntimeError(
                    f"Only {len(destinations)} destinations found; expected "
                    f"at least {MIN_DESTINATIONS_SANITY}."
                )

            log(f"Checking {len(destinations)} destinations...")

            results = []
            error_count = 0
            debug_saved = False

            for i, (value, name) in enumerate(destinations, start=1):
                if time.time() - start > MAX_RUNTIME_SECONDS:
                    raise RuntimeError("Maximum runtime reached; output not written.")

                outcome = None
                for attempt in range(1, RETRIES_PER_COUNTRY + 1):
                    try:
                        outcome = check_country(page, ctl, value)
                        break
                    except Exception as exc:
                        log(f"    attempt {attempt} failed for {name}: {exc}")
                        if not debug_saved:
                            dump_debug(page, "debug_error")
                            debug_saved = True
                        if attempt < RETRIES_PER_COUNTRY:
                            try:
                                ctl = setup(page)
                            except Exception as exc2:
                                log(f"    re-setup failed: {exc2}")

                if outcome is None:
                    status, price, delivery = "ERROR", None, None
                    error_count += 1
                else:
                    status, price, delivery = outcome

                results.append(
                    {
                        "name": name,
                        "norm": normalize(name),
                        "status": status,
                        "price": price,
                        "delivery": delivery,
                    }
                )

                extra = f" {price} {delivery}" if status == "AVAILABLE" else ""
                log(f"[{i}/{len(destinations)}] {name}: {status}{extra}")

                if error_count > MAX_ERRORS_ALLOWED:
                    raise RuntimeError(
                        f"Too many errors ({error_count}); output not written."
                    )

        finally:
            browser.close()

    report, available_count, _ = build_report(results)

    if available_count == 0:
        raise RuntimeError("No available destinations found; output not written.")

    Path(OUTPUT_FILE).write_text(report, encoding="utf-8")
    log(f"\nOutput written to {Path(OUTPUT_FILE).resolve()}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("\nInterrupted.")
        sys.exit(1)
    except Exception as exc:
        log(f"\nFATAL ERROR: {exc}")
        sys.exit(1)
