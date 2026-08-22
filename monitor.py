#!/usr/bin/env python3

import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup


CALCULATOR_URL = (
    "https://bhpwebout.posta.ba/"
    "KalkulatorCijena_WEB_app/Bos/Default.aspx"
)

OUTPUT_FILE = Path("output/bhposta_dopisnica.txt")

ERROR_MESSAGE = (
    "Prijem pošiljaka se trenutno ne vrši za odabranu državu"
)

# The values supplied by the ASP.NET page / your browser request.
TAB_STATE = '{"activeTabIndex":1}'

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "bs-BA,bs;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
}


def normalise_text(text):
    """Collapse whitespace so the error message can be found reliably."""
    return re.sub(r"\s+", " ", text).strip()


def get_hidden_fields(soup):
    """
    Get all ASP.NET hidden form fields.

    This includes fields such as:
        __VIEWSTATE
        __VIEWSTATEGENERATOR
        __EVENTVALIDATION
        etc.

    These values can change, so they must be obtained from the page
    every time instead of hard-coding them.
    """
    fields = {}

    for element in soup.select(
        'input[type="hidden"][name]'
    ):
        name = element.get("name")

        if not name:
            continue

        fields[name] = element.get("value", "")

    return fields


def find_destination_select(soup):
    """
    Find the destination-country dropdown.

    The expected ASP.NET control is:
        ddlMeDoOdrediste
    """

    select = soup.find(
        "select",
        attrs={"name": "ddlMeDoOdrediste"}
    )

    if select is None:
        select = soup.find(
            "select",
            id=re.compile(r"ddlMeDoOdrediste", re.I)
        )

    return select


def extract_countries(select):
    """
    Return [(value, visible_name), ...] from the <option> tags.
    """

    countries = []

    for option in select.find_all("option"):
        value = option.get("value", "").strip()
        name = option.get_text(" ", strip=True)

        if not name:
            continue

        # Ignore an empty placeholder such as "Odaberite..."
        if not value:
            continue

        countries.append((value, name))

    # Remove duplicates while preserving the original order.
    result = []
    seen = set()

    for value, name in countries:
        key = (value, name)

        if key not in seen:
            seen.add(key)
            result.append(key)

    return result


def make_session():
    session = requests.Session()
    session.headers.update(HEADERS)

    # These are useful for ASP.NET applications.
    session.headers.update({
        "X-Requested-With": "XMLHttpRequest",
    })

    return session


def get_initial_page(session):
    print("Downloading BH Pošta calculator...")

    response = session.get(
        CALCULATOR_URL,
        timeout=60,
    )

    response.raise_for_status()

    print(
        f"Initial page: HTTP {response.status_code}, "
        f"{len(response.text):,} bytes"
    )

    return response


def extract_countries_from_page(html):
    soup = BeautifulSoup(html, "html.parser")

    select = find_destination_select(soup)

    if select is None:
        return []

    return extract_countries(select)


def activate_international_tab(session, html):
    """
    Some versions of the calculator render the international controls
    immediately. Others may require an ASP.NET AJAX tab request.

    First try the normal page. If the destination dropdown is already
    present, there is nothing more to do.
    """

    countries = extract_countries_from_page(html)

    if countries:
        return html

    print(
        "Destination dropdown was not present in the initial page. "
        "Trying an ASP.NET AJAX request for the international tab..."
    )

    soup = BeautifulSoup(html, "html.parser")
    fields = get_hidden_fields(soup)

    fields.update({
        "__EVENTTARGET": "ASPxTabControl1",
        "__EVENTARGUMENT": "",
        "__ASYNCPOST": "true",
        "ASPxTabControl1": TAB_STATE,
    })

    try:
        response = session.post(
            CALCULATOR_URL,
            data=fields,
            timeout=60,
            headers={
                "Referer": CALCULATOR_URL,
                "X-MicrosoftAjax": "Delta=true",
            },
        )

        response.raise_for_status()

        print(
            f"International-tab request: HTTP {response.status_code}, "
            f"{len(response.text):,} bytes"
        )

        return response.text

    except requests.RequestException as exc:
        print(f"Warning: tab request failed: {exc}")
        return html


def submit_country(session, initial_html, country_value):
    """
    Submit the calculator for one destination country.

    Important values:

        ScriptManager1 = UpdatePanel1|btnMeDoIzracunaj
        ASPxTabControl1 = {"activeTabIndex":1}
        ddlMeDoOdrediste = <country>
        chbMeDoAvionski = on
        tbxMeDoAvioTezina = 10
        __EVENTTARGET =
        __EVENTARGUMENT =
        __ASYNCPOST = true
    """

    soup = BeautifulSoup(initial_html, "html.parser")

    fields = get_hidden_fields(soup)

    # Preserve the form's normal values, then override the fields
    # necessary for the calculator request.
    fields.update({
        "ScriptManager1": "UpdatePanel1|btnMeDoIzracunaj",

        "ASPxTabControl1": TAB_STATE,

        "ddlMeDoOdrediste": country_value,

        "chbMeDoAvionski": "on",

        "tbxMeDoAvioTezina": "10",

        "__EVENTTARGET": "",

        "__EVENTARGUMENT": "",

        "__ASYNCPOST": "true",
    })

    # The calculator button is an ASP.NET button. Depending on the
    # current version of the site, its name may be represented in
    # different ways. Include the known control name.
    fields["btnMeDoIzracunaj"] = "Izračunaj"

    response = session.post(
        CALCULATOR_URL,
        data=fields,
        timeout=60,
        headers={
            "Referer": CALCULATOR_URL,
            "X-MicrosoftAjax": "Delta=true",
        },
    )

    response.raise_for_status()

    return response.text


def response_contains_error(response_text):
    """
    Look for the exact BH Pošta message in the ASP.NET AJAX response.

    We deliberately search the whole response rather than depending
    on a particular result <div>, because ASP.NET UpdatePanel responses
    can change their HTML structure.
    """

    text = normalise_text(
        BeautifulSoup(response_text, "html.parser").get_text(
            " ",
            strip=True
        )
    )

    return ERROR_MESSAGE in text


def create_output(countries, unavailable):
    """
    Create the text file that changedetection.io will monitor.
    """

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    now = datetime.now(timezone.utc).astimezone()

    lines = []

    lines.append("BH POŠTA - DOPISNICA")
    lines.append("====================")
    lines.append("")
    lines.append(
        "Source: https://www.posta.ba/kalkulator-cijena/"
    )
    lines.append(
        "Calculator: https://bhpwebout.posta.ba/"
        "KalkulatorCijena_WEB_app/Bos/Default.aspx"
    )
    lines.append(
        f"Last checked: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}"
    )
    lines.append("")
    lines.append("SETTINGS")
    lines.append("--------")
    lines.append("Service: Dopisnica")
    lines.append("Traffic: Međunarodni promet")
    lines.append("Air transport: Yes")
    lines.append("Weight: 10 g")
    lines.append("")
    lines.append(
        f"TOTAL COUNTRIES IN DROPDOWN: {len(countries)}"
    )
    lines.append("")
    lines.append("ALL COUNTRIES")
    lines.append("-------------")

    for number, (_, name) in enumerate(countries, start=1):
        lines.append(f"{number}. {name}")

    lines.append("")
    lines.append(
        f"COUNTRIES WITH ERROR MESSAGE: {len(unavailable)}"
    )
    lines.append("")
    lines.append("COUNTRIES CURRENTLY NOT ACCEPTED")
    lines.append("--------------------------------")

    if unavailable:
        for number, name in enumerate(unavailable, start=1):
            lines.append(f"{number}. {name}")
    else:
        lines.append("None")

    lines.append("")

    OUTPUT_FILE.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def main():
    print("=" * 70)
    print("BH Pošta Dopisnica monitor")
    print("=" * 70)

    session = make_session()

    try:
        initial_response = get_initial_page(session)

        page_html = initial_response.text

        page_html = activate_international_tab(
            session,
            page_html,
        )

        countries = extract_countries_from_page(page_html)

        if not countries:
            print()
            print("ERROR: Could not find ddlMeDoOdrediste.")
            print()
            print(
                "The BH Pošta calculator HTML structure may have "
                "changed, or the international tab requires a "
                "different ASP.NET event."
            )
            sys.exit(1)

        print()
        print(
            f"Found {len(countries)} destination countries "
            "in ddlMeDoOdrediste."
        )
        print()

        unavailable = []

        for index, (value, name) in enumerate(
            countries,
            start=1,
        ):
            print(
                f"[{index}/{len(countries)}] "
                f"{name} ({value}) ... ",
                end="",
                flush=True,
            )

            try:
                response_text = submit_country(
                    session,
                    page_html,
                    value,
                )

                if response_contains_error(response_text):
                    unavailable.append(name)
                    print("NOT ACCEPTED")
                else:
                    print("OK")

            except requests.RequestException as exc:
                print("REQUEST ERROR")
                print(f"    {exc}")

            except Exception as exc:
                print("ERROR")
                print(f"    {exc}")

            # Be polite to the BH Pošta server.
            time.sleep(0.5)

        create_output(
            countries,
            unavailable,
        )

        print()
        print("=" * 70)
        print("Finished")
        print("=" * 70)
        print(
            f"Countries found: {len(countries)}"
        )
        print(
            f"Countries with error: {len(unavailable)}"
        )
        print(
            f"Output: {OUTPUT_FILE}"
        )
        print()

        if unavailable:
            print("Currently not accepted:")
            for country in unavailable:
                print(f"  - {country}")

    except requests.RequestException as exc:
        print()
        print("FATAL HTTP ERROR")
        print(exc)
        sys.exit(1)

    except Exception as exc:
        print()
        print("FATAL ERROR")
        print(exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
