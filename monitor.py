import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from pathlib import Path


# ============================================================
# CONFIGURATION
# ============================================================

CALCULATOR_URL = (
    "https://bhpwebout.posta.ba/"
    "KalkulatorCijena_WEB_app/Bos/Default.aspx"
)

OUTPUT_DIR = Path("debug")
OUTPUT_DIR.mkdir(exist_ok=True)


# ============================================================
# HTTP SESSION
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
    "Accept-Language": "bs-BA,bs;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
})


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def save_html(filename, html):
    path = OUTPUT_DIR / filename
    path.write_text(html, encoding="utf-8")
    print(f"Saved: {path}")


def print_section(title):
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def get_hidden_fields(html):
    """
    Extract all ASP.NET hidden form fields from the current page.
    """
    soup = BeautifulSoup(html, "html.parser")

    data = {}

    for element in soup.select("input[type='hidden']"):
        name = element.get("name")

        if not name:
            continue

        data[name] = element.get("value", "")

    return data


def find_forms(html):
    soup = BeautifulSoup(html, "html.parser")
    return soup.find_all("form")


def describe_element(element):
    if not element:
        return "NOT FOUND"

    attrs = []

    for attr in ["id", "name", "type", "value", "title", "src", "href"]:
        value = element.get(attr)

        if value is not None:
            attrs.append(f'{attr}="{value}"')

    return "<" + element.name + " " + " ".join(attrs) + ">"


# ============================================================
# STEP 1 — GET THE ACTUAL CALCULATOR IFRAME
# ============================================================

print_section("STEP 1: FETCHING ACTUAL CALCULATOR IFRAME")

print(f"GET: {CALCULATOR_URL}")

response = session.get(
    CALCULATOR_URL,
    timeout=30,
    allow_redirects=True
)

print(f"HTTP status: {response.status_code}")
print(f"Final URL:   {response.url}")
print(f"Content-Type: {response.headers.get('Content-Type')}")
print(f"Bytes:       {len(response.content)}")

response.raise_for_status()

html = response.text

save_html("calculator_initial.html", html)


# ============================================================
# STEP 2 — BASIC PAGE INSPECTION
# ============================================================

print_section("STEP 2: INSPECTING ACTUAL CALCULATOR PAGE")

soup = BeautifulSoup(html, "html.parser")

print(f"Page title: {soup.title.get_text(strip=True) if soup.title else 'NONE'}")

print()
print("Important ASP.NET fields:")

for field in [
    "__VIEWSTATE",
    "__VIEWSTATEGENERATOR",
    "__EVENTVALIDATION",
    "__EVENTTARGET",
    "__EVENTARGUMENT",
]:
    element = soup.find("input", {"name": field})

    if element:
        value = element.get("value", "")

        print(
            f"  {field}: FOUND "
            f"(length={len(value)})"
        )
    else:
        print(f"  {field}: NOT FOUND")


# ============================================================
# STEP 3 — FIND ALL FORMS
# ============================================================

print_section("STEP 3: ASP.NET FORMS")

forms = find_forms(html)

print(f"Found {len(forms)} form(s).")

for index, form in enumerate(forms, start=1):

    print()
    print(f"FORM #{index}")

    print(f"  id:     {form.get('id')}")
    print(f"  name:   {form.get('name')}")
    print(f"  method: {form.get('method')}")
    print(f"  action: {form.get('action')}")

    inputs = form.find_all(["input", "select", "button"])

    print(f"  controls: {len(inputs)}")


# ============================================================
# STEP 4 — SEARCH FOR THE IMPORTANT CONTROLS
# ============================================================

print_section("STEP 4: SEARCHING FOR CALCULATOR CONTROLS")

search_terms = [
    "Međunarodni promet",
    "Medjunarodni promet",
    "Dopisnica",
    "ImageButton8",
    "ASPxTabControl1",
    "pnlMeDopisnice",
    "ddlMeDoOdrediste",
    "ddlMeObPiOderdiste",
]

for term in search_terms:

    print()
    print(f"SEARCH: {term}")

    # Search text
    text_matches = soup.find_all(
        string=lambda s: s and term.lower() in s.lower()
    )

    if text_matches:
        print(f"  Text matches: {len(text_matches)}")

        for match in text_matches[:5]:
            parent = match.parent
            print(
                "   ",
                parent.name,
                parent.attrs
            )
    else:
        print("  Text matches: NONE")

    # Search attributes / exact IDs / names
    attr_matches = []

    for element in soup.find_all(True):

        for attr_name, attr_value in element.attrs.items():

            if isinstance(attr_value, list):
                attr_value = " ".join(attr_value)

            if term.lower() in str(attr_value).lower():
                attr_matches.append(element)
                break

    if attr_matches:
        print(f"  Attribute matches: {len(attr_matches)}")

        for element in attr_matches[:10]:
            print(
                "   ",
                describe_element(element)
            )
    else:
        print("  Attribute matches: NONE")


# ============================================================
# STEP 5 — LIST INPUT CONTROLS
# ============================================================

print_section("STEP 5: ALL INPUT CONTROLS")

inputs = soup.find_all("input")

print(f"Found {len(inputs)} input elements.")

for index, element in enumerate(inputs, start=1):

    input_type = element.get("type", "")
    name = element.get("name", "")
    element_id = element.get("id", "")
    value = element.get("value", "")
    title = element.get("title", "")

    print(
        f"{index:4d}: "
        f"type={input_type!r} "
        f"name={name!r} "
        f"id={element_id!r} "
        f"value={value[:80]!r} "
        f"title={title!r}"
    )


# ============================================================
# STEP 6 — LIST SELECT ELEMENTS
# ============================================================

print_section("STEP 6: ALL SELECT ELEMENTS")

selects = soup.find_all("select")

print(f"Found {len(selects)} select element(s).")

for index, select in enumerate(selects, start=1):

    print()
    print(
        f"SELECT #{index}: "
        f"id={select.get('id')!r}, "
        f"name={select.get('name')!r}"
    )

    options = select.find_all("option")

    print(f"  options: {len(options)}")

    for option in options[:10]:

        print(
            f"    value={option.get('value')!r} "
            f"text={option.get_text(' ', strip=True)!r}"
        )

    if len(options) > 10:
        print("    ...")


# ============================================================
# STEP 7 — FIND DOPISNICA IMAGE BUTTON
# ============================================================

print_section("STEP 7: SEARCHING FOR DOPISNICA IMAGE BUTTON")

image_inputs = soup.find_all(
    "input",
    {"type": "image"}
)

print(f"Found {len(image_inputs)} image input(s).")

for index, element in enumerate(image_inputs, start=1):

    print()
    print(f"IMAGE BUTTON #{index}")

    print(
        f"  name:  {element.get('name')}"
    )

    print(
        f"  id:    {element.get('id')}"
    )

    print(
        f"  title: {element.get('title')}"
    )

    print(
        f"  src:   {element.get('src')}"
    )

    if (
        "dopisnica" in str(element.get("title", "")).lower()
        or
        "dopisnica" in str(element.get("src", "")).lower()
    ):
        print("  >>> THIS LOOKS LIKE DOPISNICA <<<")


# ============================================================
# STEP 8 — FIND INTERNATIONAL TAB
# ============================================================

print_section("STEP 8: SEARCHING FOR 'MEĐUNARODNI PROMET'")

# Search every element whose visible text contains the phrase.

international_elements = []

for element in soup.find_all(True):

    text = element.get_text(" ", strip=True)

    if "međunarodni promet" in text.lower():
        international_elements.append(element)


print(
    f"Elements containing 'Međunarodni promet': "
    f"{len(international_elements)}"
)

for element in international_elements[:20]:

    print()
    print(
        f"ELEMENT: <{element.name}>"
    )

    print(
        f"  id:    {element.get('id')}"
    )

    print(
        f"  name:  {element.get('name')}"
    )

    print(
        f"  class: {element.get('class')}"
    )

    print(
        f"  text:  "
        f"{element.get_text(' ', strip=True)[:300]!r}"
    )

    # Show nearby HTML, useful for identifying the tab control.
    print(
        f"  HTML:  "
        f"{str(element)[:1000]}"
    )


# ============================================================
# STEP 9 — COOKIES
# ============================================================

print_section("STEP 9: SESSION COOKIES")

if session.cookies:

    for cookie in session.cookies:
        print(
            f"{cookie.name} = {cookie.value} "
            f"(domain={cookie.domain}, path={cookie.path})"
        )

else:
    print("No cookies received.")


# ============================================================
# STEP 10 — SUMMARY
# ============================================================

print_section("SUMMARY")

print(f"Calculator URL: {CALCULATOR_URL}")
print(f"Final URL:      {response.url}")
print(f"Status:         {response.status_code}")
print(f"Response size:  {len(response.content):,} bytes")
print(f"Forms:          {len(forms)}")
print(f"Inputs:         {len(inputs)}")
print(f"Selects:        {len(selects)}")
print(f"Image buttons:  {len(image_inputs)}")

print()
print("The complete initial calculator HTML is saved here:")

print(
    OUTPUT_DIR / "calculator_initial.html"
)

print()
print("NEXT STEP:")
print(
    "Use the output above to identify the actual ASP.NET control "
    "for 'Međunarodni promet'."
)
