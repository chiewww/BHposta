#!/usr/bin/env python3

import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup
import urllib3


URL = "https://www.posta.ba/kalkulator-cijena/"

OUTPUT_FILE = Path("countries.txt")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "bs-BA,bs;q=0.9,en-US;q=0.8,en;q=0.7",
}

# posta.ba currently presents an SSL certificate chain
# that the GitHub Python environment does not trust.
urllib3.disable_warnings(
    urllib3.exceptions.InsecureRequestWarning
)


def get_page(session):
    print("STEP 1: Fetching calculator page...")

    response = session.get(
        URL,
        headers=HEADERS,
        timeout=60,
        verify=False,
    )

    response.raise_for_status()

    print(f"HTTP status: {response.status_code}")
    print(
        f"Downloaded: "
        f"{len(response.content):,} bytes"
    )

    return response


def get_form(soup):
    form = soup.find("form")

    if form is None:
        raise RuntimeError(
            "Could not find the ASP.NET form."
        )

    return form


def collect_form_data(form):
    """
    Collect the current ASP.NET Web Forms fields,
    including ViewState and EventValidation.
    """

    data = {}

    # Hidden ASP.NET fields.
    for element in form.select(
        'input[type="hidden"]'
    ):
        name = element.get("name")

        if name:
            data[name] = element.get(
                "value",
                "",
            )

    # Current values of select controls.
    for select in form.find_all("select"):
        name = select.get("name")

        if not name:
            continue

        selected = select.find(
            "option",
            selected=True,
        )

        if selected is not None:
            data[name] = selected.get(
                "value",
                "",
            )

    # Ordinary inputs.
    for element in form.find_all("input"):
        name = element.get("name")

        if not name:
            continue

        input_type = element.get(
            "type",
            "text",
        ).lower()

        if input_type in (
            "hidden",
            "submit",
            "button",
            "image",
            "reset",
        ):
            continue

        if input_type in (
            "checkbox",
            "radio",
        ):
            if element.has_attr("checked"):
                data[name] = element.get(
                    "value",
                    "on",
                )
        else:
            data[name] = element.get(
                "value",
                "",
            )

    # Textareas.
    for element in form.find_all("textarea"):
        name = element.get("name")

        if name:
            data[name] = element.text or ""

    return data


def get_post_url(response, form):
    action = form.get("action")

    if not action:
        return response.url

    return requests.compat.urljoin(
        response.url,
        action,
    )


def select_international(session, response):
    """
    Explicitly select:

        Međunarodni promet

    The HTML shows an ASPxClientTabControl named
    ASPxTabControl1 with activeTabIndex 1.

    The tab control uses autoPostBack=true.

    We reproduce the tab postback by sending the
    ASP.NET control event for ASPxTabControl1.
    """

    print()
    print(
        "STEP 2: Selecting "
        "'Međunarodni promet'..."
    )

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    form = get_form(soup)

    data = collect_form_data(form)

    post_url = get_post_url(
        response,
        form,
    )

    # ASPxTabControl1 is the actual DevExpress
    # tab control shown in the supplied HTML.
    #
    # Tab index:
    #   0 = Unutrašnji promet
    #   1 = Međunarodni promet
    #
    # DevExpress ASPx controls use their own callback/
    # postback mechanism. We submit the control event
    # and explicitly request tab 1.
    data["__EVENTTARGET"] = "ASPxTabControl1"
    data["__EVENTARGUMENT"] = "1"

    response2 = session.post(
        post_url,
        data=data,
        headers={
            **HEADERS,
            "Referer": response.url,
            "Content-Type": (
                "application/x-www-form-urlencoded"
            ),
        },
        timeout=60,
        verify=False,
    )

    response2.raise_for_status()

    print(
        f"International-tab POST status: "
        f"{response2.status_code}"
    )

    print(
        f"Response size: "
        f"{len(response2.content):,} bytes"
    )

    # Verify what came back.
    soup2 = BeautifulSoup(
        response2.text,
        "html.parser",
    )

    international_text = soup2.find(
        string=lambda text:
            text and "Međunarodni promet" in text
    )

    if international_text is not None:
        print(
            "Confirmed: "
            "'Međunarodni promet' is present."
        )
    else:
        print(
            "WARNING: Could not independently "
            "confirm the International tab."
        )

    return response2


def click_dopisnica(session, response):
    """
    Click ImageButton8, which is the Dopisnica
    button:

        name="ImageButton8"
        id="ImageButton8"
        title="Dopisnica"
    """

    print()
    print(
        "STEP 3: Clicking "
        "'Dopisnica'..."
    )

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    form = get_form(soup)

    data = collect_form_data(form)

    post_url = get_post_url(
        response,
        form,
    )

    # ImageButton controls submit x/y coordinates.
    data["ImageButton8.x"] = "40"
    data["ImageButton8.y"] = "25"

    # This is a normal image-button submit,
    # not an __doPostBack event.
    data["__EVENTTARGET"] = ""
    data["__EVENTARGUMENT"] = ""

    response2 = session.post(
        post_url,
        data=data,
        headers={
            **HEADERS,
            "Referer": response.url,
            "Content-Type": (
                "application/x-www-form-urlencoded"
            ),
        },
        timeout=60,
        verify=False,
    )

    response2.raise_for_status()

    print(
        f"Dopisnica POST status: "
        f"{response2.status_code}"
    )

    print(
        f"Response size: "
        f"{len(response2.content):,} bytes"
    )

    # Confirm Dopisnica is actually active.
    soup2 = BeautifulSoup(
        response2.text,
        "html.parser",
    )

    dopisnica_image = soup2.find(
        "input",
        id="ImageButton8",
    )

    if dopisnica_image is not None:
        src = dopisnica_image.get(
            "src",
            "",
        )

        print(
            f"ImageButton8 image: {src}"
        )

        if "Dopisnica_Aktivna" in src:
            print(
                "Confirmed: "
                "Dopisnica is active."
            )

    return response2


def extract_countries(response):
    """
    Extract countries from the Dopisnica panel.
    """

    print()
    print(
        "STEP 4: Extracting "
        "Dopisnica countries..."
    )

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    panel = soup.find(
        "div",
        id="pnlMeDopisnice",
    )

    if panel is None:
        raise RuntimeError(
            "Could not find #pnlMeDopisnice. "
            "The Dopisnica selection did not "
            "produce the expected panel."
        )

    country_select = panel.find(
        "select",
        id="ddlMeDoOdrediste",
    )

    if country_select is None:
        raise RuntimeError(
            "Could not find "
            "#ddlMeDoOdrediste inside "
            "#pnlMeDopisnice."
        )

    options = country_select.find_all(
        "option"
    )

    if not options:
        raise RuntimeError(
            "The country dropdown contains "
            "no <option> elements."
        )

    countries = []

    # IMPORTANT:
    #
    # DO NOT SORT.
    #
    # This preserves exactly the order returned
    # by BH Pošta.
    for option in options:
        value = option.get(
            "value",
            "",
        )

        name = option.get_text(
            strip=True
        )

        if not name:
            continue

        countries.append(
            (
                value,
                name,
            )
        )

    if not countries:
        raise RuntimeError(
            "No country options were extracted."
        )

    return countries


def write_output(countries):
    print()
    print(
        "STEP 5: Writing countries.txt..."
    )

    lines = []

    for value, name in countries:
        lines.append(
            f'<option value="{value}">{name}</option>'
        )

    OUTPUT_FILE.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    print()
    print(
        f"SUCCESS: {len(countries)} "
        f"country options written."
    )

    print(
        f"Output file: {OUTPUT_FILE}"
    )

    print()
    print("=" * 70)
    print(
        "COUNTRIES — ORIGINAL WEBSITE ORDER"
    )
    print("=" * 70)

    for line in lines:
        print(line)

    print("=" * 70)


def main():
    session = requests.Session()

    try:
        # 1. GET the calculator.
        response = get_page(session)

        # 2. Explicitly select International traffic.
        response = select_international(
            session,
            response,
        )

        # 3. Click Dopisnica.
        response = click_dopisnica(
            session,
            response,
        )

        # 4. Extract countries.
        countries = extract_countries(
            response,
        )

        # 5. Save countries.txt.
        write_output(countries)

        return 0

    except requests.RequestException as exc:
        print()
        print(
            "ERROR: Website request failed:"
        )
        print(exc)
        return 1

    except Exception as exc:
        print()
        print("ERROR:")
        print(exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
