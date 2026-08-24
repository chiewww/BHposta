#!/usr/bin/env python3

import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup
import urllib3


URL = "https://www.posta.ba/kalkulator-cijena/"

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
    "Accept-Language": "hr-HR,hr;q=0.9,bs;q=0.8,en;q=0.7",
}

OUTPUT_FILE = Path("countries.txt")

DEBUG_INITIAL = Path("debug_initial.html")
DEBUG_INTERNATIONAL = Path("debug_international.html")
DEBUG_DOPISNICA = Path("debug_dopisnica.html")

# The site's certificate chain is not trusted by the
# GitHub Actions Python environment.
urllib3.disable_warnings(
    urllib3.exceptions.InsecureRequestWarning
)


def save_debug(path, response):
    path.write_text(
        response.text,
        encoding="utf-8",
    )

    print(
        f"Saved debug HTML: {path}"
    )


def get_form(response):
    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    form = soup.find("form")

    if form is None:
        raise RuntimeError(
            "Could not find <form> in returned HTML."
        )

    return soup, form


def collect_hidden_fields(form):
    data = {}

    for element in form.select(
        'input[type="hidden"]'
    ):
        name = element.get("name")

        if name:
            data[name] = element.get(
                "value",
                "",
            )

    return data


def find_control(response, control_id):
    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    return soup.find(
        id=control_id
    )


def inspect_page(response, label):
    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    print()
    print("=" * 70)
    print(f"PAGE INSPECTION: {label}")
    print("=" * 70)

    controls = [
        "ASPxTabControl1",
        "ASPxTabControl1_AT1",
        "ImageButton8",
        "pnlMeDopisnice",
        "ddlMeDoOdrediste",
        "pnlMeObicnoPismo",
        "ddlMeObPiOderdiste",
    ]

    for control_id in controls:
        element = soup.find(
            id=control_id
        )

        if element is None:
            print(
                f"{control_id}: NOT FOUND"
            )
        else:
            print(
                f"{control_id}: FOUND"
            )

            if control_id == "ImageButton8":
                print(
                    f"  src = "
                    f"{element.get('src')}"
                )

    print("=" * 70)


def initial_get(session):
    print(
        "STEP 1: Fetching calculator page..."
    )

    response = session.get(
        URL,
        headers=HEADERS,
        timeout=60,
        verify=False,
    )

    response.raise_for_status()

    print(
        f"HTTP status: {response.status_code}"
    )

    print(
        f"Downloaded: "
        f"{len(response.content):,} bytes"
    )

    save_debug(
        DEBUG_INITIAL,
        response,
    )

    inspect_page(
        response,
        "INITIAL GET",
    )

    return response


def select_international(session, response):
    print()
    print(
        "STEP 2: Selecting "
        "'Međunarodni promet'..."
    )

    soup, form = get_form(response)

    data = collect_hidden_fields(form)

    action = form.get("action")

    if action:
        post_url = requests.compat.urljoin(
            response.url,
            action,
        )
    else:
        post_url = response.url

    #
    # The supplied HTML shows:
    #
    # ASPxTabControl1
    # activeTabIndex: 1
    # autoPostBack: true
    #
    # We first try the ASP.NET WebForms-style
    # postback with the actual tab control.
    #

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

    save_debug(
        DEBUG_INTERNATIONAL,
        response2,
    )

    inspect_page(
        response2,
        "AFTER INTERNATIONAL TAB POST",
    )

    return response2


def click_dopisnica(session, response):
    print()
    print(
        "STEP 3: Clicking "
        "'Dopisnica'..."
    )

    soup, form = get_form(response)

    data = collect_hidden_fields(form)

    action = form.get("action")

    if action:
        post_url = requests.compat.urljoin(
            response.url,
            action,
        )
    else:
        post_url = response.url

    #
    # ImageButton8 is:
    #
    # <input type="image"
    #        name="ImageButton8"
    #        id="ImageButton8"
    #        title="Dopisnica"
    #        ...>
    #
    # ASP.NET ImageButton submits .x and .y.
    #

    data["ImageButton8.x"] = "40"
    data["ImageButton8.y"] = "25"

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

    save_debug(
        DEBUG_DOPISNICA,
        response2,
    )

    inspect_page(
        response2,
        "AFTER DOPISNICA POST",
    )

    return response2


def extract_countries(response):
    print()
    print(
        "STEP 4: Looking for "
        "#ddlMeDoOdrediste..."
    )

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    select = soup.find(
        "select",
        id="ddlMeDoOdrediste",
    )

    if select is None:
        raise RuntimeError(
            "Could not find "
            "#ddlMeDoOdrediste."
        )

    options = select.find_all(
        "option"
    )

    if not options:
        raise RuntimeError(
            "#ddlMeDoOdrediste exists, "
            "but contains no options."
        )

    countries = []

    #
    # IMPORTANT:
    #
    # We deliberately DO NOT sort these.
    # The order is exactly the order supplied
    # by the website.
    #
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

    print()
    print(
        f"Found {len(countries)} "
        f"country options."
    )

    return countries


def write_countries(countries):
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
        f"Wrote {len(lines)} entries to "
        f"{OUTPUT_FILE}"
    )


def main():
    session = requests.Session()

    try:
        response = initial_get(
            session
        )

        response = select_international(
            session,
            response,
        )

        response = click_dopisnica(
            session,
            response,
        )

        countries = extract_countries(
            response
        )

        write_countries(
            countries
        )

        print()
        print(
            "SUCCESS"
        )

        return 0

    except requests.RequestException as exc:
        print()
        print(
            "ERROR: HTTP request failed:"
        )
        print(exc)

        return 1

    except Exception as exc:
        print()
        print(
            "ERROR:"
        )
        print(exc)

        return 1


if __name__ == "__main__":
    sys.exit(main())
