import os
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# ============================================================
# CONFIG
# ============================================================

CALCULATOR_URL = (
    "https://bhpwebout.posta.ba/"
    "KalkulatorCijena_WEB_app/Bos/Default.aspx"
)

DEBUG_DIR = "debug"
os.makedirs(DEBUG_DIR, exist_ok=True)

OUTPUT_FILE = os.path.join(
    DEBUG_DIR,
    "step10_international.html"
)

# ============================================================
# SESSION
# ============================================================

session = requests.Session()

session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "bs-BA,bs;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.posta.ba/kalkulator-cijena/",
})

# ============================================================
# STEP 1: LOAD CALCULATOR
# ============================================================

print("=" * 70)
print("STEP 1: LOADING CALCULATOR")
print("=" * 70)

response = session.get(
    CALCULATOR_URL,
    timeout=30,
    allow_redirects=True
)

print("Status:", response.status_code)
print("Final URL:", response.url)
print("Response size:", len(response.content))

html = response.text

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write(html)

print("Saved:", OUTPUT_FILE)

soup = BeautifulSoup(html, "html.parser")

# ============================================================
# STEP 2: SESSION COOKIES
# ============================================================

print("\n" + "=" * 70)
print("STEP 2: SESSION COOKIES")
print("=" * 70)

for cookie in session.cookies:
    print(
        cookie.name,
        "=",
        cookie.value,
        "(domain=",
        cookie.domain,
        ", path=",
        cookie.path,
        ")"
    )

# ============================================================
# STEP 3: FORM
# ============================================================

print("\n" + "=" * 70)
print("STEP 3: ASP.NET FORM")
print("=" * 70)

forms = soup.find_all("form")

print("Forms found:", len(forms))

for i, form in enumerate(forms, 1):
    print("\nFORM", i)
    print("id:", form.get("id"))
    print("name:", form.get("name"))
    print("method:", form.get("method"))
    print("action:", form.get("action"))

form = soup.find("form", id="form1")

if not form:
    print("ERROR: form#form1 not found")
    raise SystemExit(1)

form_action = urljoin(response.url, form.get("action", ""))

print("\nSelected form:")
print("id:", form.get("id"))
print("action:", form_action)
print("method:", form.get("method"))

# ============================================================
# STEP 4: HIDDEN ASP.NET FIELDS
# ============================================================

print("\n" + "=" * 70)
print("STEP 4: ASP.NET HIDDEN FIELDS")
print("=" * 70)

hidden_names = [
    "__VIEWSTATE",
    "__VIEWSTATEGENERATOR",
    "__EVENTVALIDATION",
    "__EVENTTARGET",
    "__EVENTARGUMENT",
    "__LASTFOCUS",
]

for name in hidden_names:
    element = form.find("input", {"name": name})

    if element:
        value = element.get("value", "")

        print(
            f"{name}: "
            f"FOUND "
            f"(length={len(value)})"
        )

        if name in ["__EVENTTARGET", "__EVENTARGUMENT"]:
            print("  value:", repr(value))
    else:
        print(name + ": NOT FOUND")

# ============================================================
# STEP 5: ALL INPUTS
# ============================================================

print("\n" + "=" * 70)
print("STEP 5: ALL INPUT CONTROLS")
print("=" * 70)

inputs = form.find_all("input")

print("Input count:", len(inputs))

for i, inp in enumerate(inputs, 1):

    print(
        f"{i:3}: "
        f"type={inp.get('type')!r} "
        f"id={inp.get('id')!r} "
        f"name={inp.get('name')!r} "
        f"value={inp.get('value')!r} "
        f"title={inp.get('title')!r}"
    )

# ============================================================
# STEP 6: SELECTS
# ============================================================

print("\n" + "=" * 70)
print("STEP 6: SELECT ELEMENTS")
print("=" * 70)

selects = form.find_all("select")

print("Select count:", len(selects))

for i, select in enumerate(selects, 1):

    print(
        f"\nSELECT #{i}"
    )

    print("id:", select.get("id"))
    print("name:", select.get("name"))
    print("class:", select.get("class"))

    options = select.find_all("option")

    print("options:", len(options))

    for option in options:
        print(
            "   value=",
            repr(option.get("value")),
            "text=",
            repr(option.get_text(" ", strip=True))
        )

# ============================================================
# STEP 7: DEVEXPRESS TAB
# ============================================================

print("\n" + "=" * 70)
print("STEP 7: DEVEXPRESS TAB CONTROL")
print("=" * 70)

tab = soup.find(id="ASPxTabControl1")

if not tab:
    print("ASPxTabControl1: NOT FOUND")
else:

    print("ASPxTabControl1: FOUND")

    print("\nAttributes:")
    for key, value in tab.attrs.items():
        print(" ", key, "=", value)

    print("\nHTML:")
    print(tab.prettify())

# ============================================================
# STEP 8: INTERNATIONAL TAB
# ============================================================

print("\n" + "=" * 70)
print("STEP 8: INTERNATIONAL TAB")
print("=" * 70)

international_nodes = []

for element in soup.find_all(
    string=lambda s: s and "Međunarodni promet" in s
):
    parent = element.parent
    international_nodes.append(parent)

print(
    "Elements containing 'Međunarodni promet':",
    len(international_nodes)
)

for i, element in enumerate(international_nodes, 1):

    print("\n--- INTERNATIONAL NODE", i, "---")

    print("TAG:", element.name)
    print("ID:", element.get("id"))
    print("CLASS:", element.get("class"))
    print("TEXT:", element.get_text(" ", strip=True))

    if element.name in ["a", "span", "li"]:
        print("\nHTML:")
        print(str(element))

        print("\nPARENT:")
        if element.parent:
            print(str(element.parent))

# ============================================================
# STEP 9: SEARCH RAW HTML FOR INTERNATIONAL CONTROL NAMES
# ============================================================

print("\n" + "=" * 70)
print("STEP 9: SEARCHING RAW HTML")
print("=" * 70)

search_terms = [
    "Međunarodni",
    "Medjunarodni",
    "Dopisnica",
    "Dopisnice",
    "ddlMe",
    "pnlMe",
    "ImageButton8",
    "MeDo",
    "MeOb",
    "Odrediste",
    "Oderdiste",
    "ASPxTabControl1",
    "ActiveTabIndex",
    "ActiveTab",
    "TabIndex",
    "SetActiveTab",
    "SetActiveTabIndex",
    "PerformCallback",
    "Callback",
    "__doPostBack",
]

for term in search_terms:

    count = html.lower().count(term.lower())

    print(
        f"{term:30} -> {count}"
    )

# ============================================================
# STEP 10: EXTRACT LINES AROUND INTERNATIONAL TERMS
# ============================================================

print("\n" + "=" * 70)
print("STEP 10: RAW HTML CONTEXT")
print("=" * 70)

lines = html.splitlines()

interesting_terms = [
    "Međunarodni",
    "ddlMe",
    "pnlMe",
    "ImageButton8",
    "ASPxTabControl1",
    "ActiveTabIndex",
    "SetActiveTab",
    "PerformCallback",
    "__doPostBack",
]

seen = set()

for index, line in enumerate(lines):

    for term in interesting_terms:

        if term.lower() in line.lower():

            start = max(0, index - 3)
            end = min(len(lines), index + 4)

            key = (start, end)

            if key in seen:
                continue

            seen.add(key)

            print(
                "\n--- context around line",
                index + 1,
                "---"
            )

            for n in range(start, end):
                print(
                    f"{n + 1:6}: {lines[n]}"
                )

            break

# ============================================================
# STEP 11: SEARCH JAVASCRIPT
# ============================================================

print("\n" + "=" * 70)
print("STEP 11: JAVASCRIPT ANALYSIS")
print("=" * 70)

scripts = soup.find_all("script")

print("Script elements:", len(scripts))

js_keywords = [
    "ASPxTabControl1",
    "ActiveTabIndex",
    "SetActiveTab",
    "SetActiveTabIndex",
    "GetTab",
    "GetActiveTab",
    "PerformCallback",
    "Callback",
    "__doPostBack",
    "ImageButton4",
    "Međunarodni",
    "Medjunarodni",
]

for i, script in enumerate(scripts, 1):

    src = script.get("src")

    if src:
        print(
            f"\nSCRIPT #{i}: external"
        )
        print("src:", urljoin(response.url, src))

    else:

        text = script.get_text()

        if any(
            keyword.lower() in text.lower()
            for keyword in js_keywords
        ):

            print(
                f"\nSCRIPT #{i}: relevant inline JavaScript"
            )

            print(
                text[:10000]
            )

# ============================================================
# STEP 12: EXTERNAL JAVASCRIPT FILES
# ============================================================

print("\n" + "=" * 70)
print("STEP 12: JAVASCRIPT FILE REFERENCES")
print("=" * 70)

for script in scripts:

    src = script.get("src")

    if src:

        absolute = urljoin(response.url, src)

        print(absolute)

# ============================================================
# STEP 13: SEARCH FOR ASP.NET POSTBACK FUNCTIONS
# ============================================================

print("\n" + "=" * 70)
print("STEP 13: POSTBACK FUNCTIONS")
print("=" * 70)

postback_patterns = [
    r"__doPostBack\s*\(",
    r"WebForm_DoPostBackWithOptions\s*\(",
    r"ASPxClientUtils",
    r"ASPxClientTabControl",
    r"SetActiveTab",
    r"PerformCallback",
]

for pattern in postback_patterns:

    matches = list(
        re.finditer(
            pattern,
            html,
            re.IGNORECASE
        )
    )

    print(
        f"\nPATTERN: {pattern}"
    )

    print(
        "Matches:",
        len(matches)
    )

    for match in matches[:20]:

        start = max(
            0,
            match.start() - 500
        )

        end = min(
            len(html),
            match.end() + 1000
        )

        print(
            html[start:end]
        )

# ============================================================
# STEP 14: SEARCH ALL ELEMENT IDs
# ============================================================

print("\n" + "=" * 70)
print("STEP 14: ALL IDS RELATED TO ME / INTERNATIONAL")
print("=" * 70)

for element in soup.find_all(True):

    element_id = element.get("id")

    if not element_id:
        continue

    id_lower = element_id.lower()

    if any(
        keyword in id_lower
        for keyword in [
            "me",
            "med",
            "international",
            "odred",
            "oder",
            "pnl",
            "ddl",
            "imagebutton",
        ]
    ):

        print(
            element.name,
            "id=",
            element_id,
            "name=",
            element.get("name"),
            "type=",
            element.get("type"),
            "title=",
            element.get("title")
        )

# ============================================================
# STEP 15: FORM HTML
# ============================================================

print("\n" + "=" * 70)
print("STEP 15: COMPLETE FORM HTML")
print("=" * 70)

form_file = os.path.join(
    DEBUG_DIR,
    "step10_form.html"
)

with open(
    form_file,
    "w",
    encoding="utf-8"
) as f:
    f.write(form.prettify())

print(
    "Complete form saved to:",
    form_file
)

# ============================================================
# STEP 16: SUMMARY
# ============================================================

print("\n" + "=" * 70)
print("STEP 16: SUMMARY")
print("=" * 70)

print(
    "Calculator URL:",
    response.url
)

print(
    "Form:",
    form.get("id")
)

print(
    "Form action:",
    form_action
)

print(
    "Inputs:",
    len(inputs)
)

print(
    "Selects:",
    len(selects)
)

print(
    "Scripts:",
    len(scripts)
)

print(
    "ASPxTabControl1:",
    "FOUND" if tab else "NOT FOUND"
)

print(
    "International text:",
    "FOUND"
    if "Međunarodni promet" in html
    else "NOT FOUND"
)

print()
print("Saved files:")
print(" ", OUTPUT_FILE)
print(" ", form_file)

print("\n" + "=" * 70)
print("NEXT OBJECTIVE")
print("=" * 70)

print(
    """
Determine exactly how the original calculator switches from
'Unutrašnji promet' to 'Međunarodni promet'.

Do NOT guess the control names.

Look specifically for:

1. ASP.NET __EVENTTARGET values
2. DevExpress callback JavaScript
3. ASPxTabControl1 client-side initialization
4. Hidden fields containing the active tab
5. Any JavaScript associated with the second tab
6. Server-side postback/callback parameters
7. Controls that appear only after activating the
   Međunarodni promet tab
"""
)
