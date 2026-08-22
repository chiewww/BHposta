#!/usr/bin/env python3

import html as html_module
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

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "bs-BA,bs;q=0.9,en;q=0.8",
}


def normalise_text(text):
    return re.sub(r"\s+", " ", text).strip()


def make_session():
    session = requests.Session()

    session.headers.update(HEADERS)

    return session


def get_hidden_fields(soup):
    fields = {}

    for element in soup.select('input[type="hidden"][name]'):
        name = element.get("name")

        if name:
            fields[name] = element.get("value", "")

    return fields


def find_select(html_text):
    """
    Find ddlMeDoOdrediste in either normal HTML or an ASP.NET AJAX
    partial-rendering response.
    """

    # First try normal BeautifulSoup parsing.
    soup = BeautifulSoup(html_text, "html.parser")

    select = soup.find(
        "select",
        attrs={"name": "ddlMeDoOdrediste"}
    )

    if select is not None:
        return select

    select = soup.find(
        "select",
        id=re.compile(r"ddlMeDoOdrediste", re.I)
    )

    if select is not None:
        return select

    # ASP.NET AJAX sometimes HTML-encodes the UpdatePanel content.
    decoded = html_module.unescape(html_text)

    soup = BeautifulSoup(decoded, "html.parser")

    select = soup.find(
        "select",
        attrs={"name": "ddlMeDoOdrediste"}
    )

    if select is not None:
        return select

    select = soup.find(
        "select",
        id=re.compile(r"ddlMeDoOdrediste", re.I)
    )

    return select


def extract_updatepanel_html(response_text):
    """
    ASP.NET AJAX responses normally look approximately like:

        1|#||4|...|updatePanel|UpdatePanel1|<HTML HERE>|...

    The HTML may itself be HTML-encoded.

    Rather than trying to depend on the exact pipe positions, return
    the complete response plus decoded versions. BeautifulSoup can
    then search all of them.
    """

    candidates = []

    candidates.append(response_text)

    decoded = html_module.unescape(response_text)

    if decoded != response_text:
        candidates.append(decoded)

    # ASP.NET AJAX uses pipe-delimited records.
    parts = response_text.split("|")

    for part in parts:
        if (
            "ddlMeDoOdrediste" in part
            or "UpdatePanel1" in part
            or "<select" in part
        ):
            candidates.append(part)

            decoded_part = html_module.unescape(part)

            if decoded_part != part:
                candidates.append(decoded_part)

    # Return the longest candidate first because it normally contains
    # the most complete HTML.
    candidates.sort(
        key=len,
        reverse=True
    )

    return candidates


def extract_countries(html_text):
    """
    Extract every non-empty <option> from ddlMeDoOdrediste.
    """

    select = find_select(html_text)

    if select is None:
        return []

    countries = []

    for option in select.find_all("option"):
        value = option.get("value", "").strip()

        name = option.get_text(
            " ",
            strip=True
        )

        if not name:
            continue

        # Skip the empty/default selection.
        if not value:
            continue

        countries.append(
            (
                value,
                name
            )
        )

    # Remove duplicates while preserving order.
    result = []
    seen = set()

    for value, name in countries:
        key = (value, name)

        if key not in seen:
            seen.add(key)
            result.append(key)

    return result


def extract_countries_from_response(response_text):
    """
    Search all representations of an ASP.NET AJAX response.
    """

    candidates = extract_updatepanel_html(
        response_text
    )

    for candidate in candidates:
        countries = extract_countries(candidate)

        if countries:
            return countries

    return []


def get_initial_page(session):
    print("Downloading BH Pošta calculator...")

    response = session.get(
        CALCULATOR_URL,
        timeout=60
    )

    response.raise_for_status()

    print(
        f"Initial page: HTTP {response.status_code}, "
        f"{len(response.text):,} bytes"
    )

    return response


def activate_international_tab(session, initial_html):
    """
    Open the Međunarodni promet tab.

    The supplied values from the user's browser inspection are:

        ScriptManager1 = UpdatePanel1|btnMeDoIzracunaj
        ASPxTabControl1 = {"activeTabIndex":1}

    For the tab activation itself we send the ASPxTabControl1
    event to the ASP.NET page and then inspect the UpdatePanel
    response.
    """

    countries = extract_countries(
        initial_html
    )

    if countries:
        print(
            "Destination dropdown already exists "
            "in the initial HTML."
        )

        return initial_html

    soup = BeautifulSoup(
        initial_html,
        "html.parser"
    )

    fields = get_hidden_fields(soup)

    # ASP.NET AJAX tab activation.
    fields.update({
        "ScriptManager1": "UpdatePanel1|ASPxTabControl1",

        "ASPxTabControl1": '{"activeTabIndex":1}',

        "__EVENTTARGET": "ASPxTabControl1",

        "__EVENTARGUMENT": "",

        "__ASYNCPOST": "true",
    })

    print(
        "Opening Međunarodni promet tab..."
    )

    response = session.post(
        CALCULATOR_URL,
        data=fields,
        timeout=60,
        headers={
            "Referer": CALCULATOR_URL,
            "X-Requested-With": "XMLHttpRequest",
            "X-MicrosoftAjax": "Delta=true",
        },
    )

    response.raise_for_status()

    print(
        f"International-tab request: "
        f"HTTP {response.status_code}, "
        f"{len(response.text):,} bytes"
    )

    countries = extract_countries_from_response(
        response.text
    )

    if countries:
        print(
            f"Found {len(countries)} countries "
            "after opening international tab."
        )

        return response.text

    # Some versions use the exact ASPxTabControl state supplied
    # by the user's browser request but don't require the control
    # itself as __EVENTTARGET.
    fields = get_hidden_fields(soup)

    fields.update({
        "ScriptManager1": "UpdatePanel1|btnMeDoIzracunaj",

        "ASPxTabControl1": '{"activeTabIndex":1}',

        "__EVENTTARGET": "",

        "__EVENTARGUMENT": "",

        "__ASYNCPOST": "true",
    })

    print(
        "Trying the calculator's supplied AJAX state..."
    )

    response = session.post(
        CALCULATOR_URL,
        data=fields,
        timeout=60,
        headers={
            "Referer": CALCULATOR_URL,
            "X-Requested-With": "XMLHttpRequest",
            "X-MicrosoftAjax": "Delta=true",
        },
    )

    response.raise_for_status()

    print(
        f"Second tab request: "
        f"HTTP {response.status_code}, "
        f"{len(response.text):,} bytes"
    )

    countries = extract_countries_from_response(
        response.text
    )

    if countries:
        print(
            f"Found {len(countries)} countries."
        )

        return response.text

    return response.text


def submit_country(
    session,
    page_html,
    country_value
):
    """
    Submit the calculator for one country.

    Values supplied by the user's browser inspection:

        ScriptManager1 = UpdatePanel1|btnMeDoIzracunaj
        ASPxTabControl1 = {"activeTabIndex":1}
        ddlMeDoOdrediste = <country>
        chbMeDoAvionski = on
        tbxMeDoAvioTezina = 10
        __EVENTTARGET =
        __EVENTARGUMENT =
        __ASYNCPOST = true
    """

    # The page_html may be either normal HTML or an AJAX response.
    soup = BeautifulSoup(
        html_module.unescape(page_html),
        "html.parser"
    )

    fields = get_hidden_fields(soup)

    fields.update({
        "ScriptManager1":
            "UpdatePanel1|btnMeDoIzracunaj",

        "ASPxTabControl1":
            '{"activeTabIndex":1}',

        "ddlMeDoOdrediste":
            country_value,

        "chbMeDoAvionski":
            "on",

        "tbxMeDoAvioTezina":
            "10",

        "__EVENTTARGET":
            "",

        "__EVENTARGUMENT":
            "",

        "__ASYNCPOST":
            "true",

        "btnMeDoIzracunaj":
            "Izračunaj",
    })

    response = session.post(
        CALCULATOR_URL,
        data=fields,
        timeout=60,
        headers={
            "Referer": CALCULATOR_URL,
            "X-Requested-With": "XMLHttpRequest",
            "X-MicrosoftAjax": "Delta=true",
        },
    )

    response.raise_for_status()

    return response.text


def response_contains_error(response_text):
    """
    Check both the raw AJAX response and decoded HTML.
    """

    candidates = [
        response_text,
        html_module.unescape(response_text),
    ]

    for candidate in candidates:

        if ERROR_MESSAGE in candidate:
            return True

        soup = BeautifulSoup(
            candidate,
            "html.parser"
        )

        text = normalise_text(
            soup.get_text(
                " ",
                strip=True
            )
        )

        if ERROR_MESSAGE in text:
            return True

    return False


def create_output(
    countries,
    unavailable
):
    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    now = datetime.now(
        timezone.utc
    ).astimezone()

    lines = []

    lines.append(
        "BH POŠTA - DOPISNICA"
    )

    lines.append(
        "===================="
    )

    lines.append("")

    lines.append(
        "Source: "
        "https://www.posta.ba/kalkulator-cijena/"
    )

    lines.append(
        "Calculator: "
        + CALCULATOR_URL
    )

    lines.append(
        "Last checked: "
        + now.strftime(
            "%Y-%m-%d %H:%M:%S %Z"
        )
    )

    lines.append("")

    lines.append("SETTINGS")
    lines.append("--------")

    lines.append(
        "Service: Dopisnica"
    )

    lines.append(
        "Traffic: Međunarodni promet"
    )

    lines.append(
        "Air transport: Yes"
    )

    lines.append(
        "Weight: 10 g"
    )

    lines.append("")

    lines.append(
        "TOTAL COUNTRIES IN DROPDOWN: "
        + str(len(countries))
    )

    lines.append("")

    lines.append(
        "ALL COUNTRIES"
    )

    lines.append(
        "-------------"
    )

    for number, (_, name) in enumerate(
        countries,
        start=1
    ):
        lines.append(
            f"{number}. {name}"
        )

    lines.append("")

    lines.append(
        "COUNTRIES WITH ERROR MESSAGE: "
        + str(len(unavailable))
    )

    lines.append("")

    lines.append(
        "COUNTRIES CURRENTLY NOT ACCEPTED"
    )

    lines.append(
        "--------------------------------"
    )

    if unavailable:

        for number, name in enumerate(
            unavailable,
            start=1
        ):
            lines.append(
                f"{number}. {name}"
            )

    else:

        lines.append(
            "None"
        )

    lines.append("")

    OUTPUT_FILE.write_text(
        "\n".join(lines),
        encoding="utf-8"
    )


def save_debug_file(
    response_text,
    filename
):
    """
    Save an AJAX response if debugging becomes necessary.
    """

    debug_dir = Path("debug")

    debug_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    path = debug_dir / filename

    path.write_text(
        response_text,
        encoding="utf-8"
    )

    print(
        f"Debug response saved to {path}"
    )


def main():

    print(
        "=" * 70
    )

    print(
        "BH Pošta Dopisnica monitor"
    )

    print(
        "=" * 70
    )

    session = make_session()

    try:

        initial_response = get_initial_page(
            session
        )

        page_html = initial_response.text

        # First attempt: perhaps the controls are already present.
        countries = extract_countries(
            page_html
        )

        if countries:

            print(
                f"Found {len(countries)} countries "
                "in initial page."
            )

        else:

            page_html = activate_international_tab(
                session,
                page_html
            )

            countries = extract_countries_from_response(
                page_html
            )

        if not countries:

            print()
            print(
                "ERROR: Could not find "
                "ddlMeDoOdrediste."
            )

            print()
            print(
                "Saving the server response for debugging..."
            )

            save_debug_file(
                page_html,
                "international_tab_response.txt"
            )

            print()
            print(
                "The file above can be used to determine "
                "the exact ASP.NET AJAX response structure."
            )

            sys.exit(1)

        print()
        print(
            f"TOTAL COUNTRIES FOUND: "
            f"{len(countries)}"
        )

        print()

        unavailable = []

        for index, (
            value,
            name
        ) in enumerate(
            countries,
            start=1
        ):

            print(
                f"[{index}/{len(countries)}] "
                f"{name} ({value}) ... ",
                end="",
                flush=True
            )

            try:

                response_text = submit_country(
                    session,
                    page_html,
                    value
                )

                if response_contains_error(
                    response_text
                ):

                    unavailable.append(
                        name
                    )

                    print(
                        "NOT ACCEPTED"
                    )

                else:

                    print(
                        "OK"
                    )

            except requests.RequestException as exc:

                print(
                    "REQUEST ERROR"
                )

                print(
                    f"    {exc}"
                )

            except Exception as exc:

                print(
                    "ERROR"
                )

                print(
                    f"    {exc}"
                )

            # Small delay between countries.
            time.sleep(0.5)

        create_output(
            countries,
            unavailable
        )

        print()

        print(
            "=" * 70
        )

        print(
            "Finished"
        )

        print(
            "=" * 70
        )

        print(
            f"Countries found: "
            f"{len(countries)}"
        )

        print(
            f"Countries with error: "
            f"{len(unavailable)}"
        )

        print(
            f"Output file: "
            f"{OUTPUT_FILE}"
        )

        print()

        if unavailable:

            print(
                "Currently not accepted:"
            )

            for country in unavailable:

                print(
                    f"  - {country}"
                )

    except requests.RequestException as exc:

        print()
        print(
            "FATAL HTTP ERROR"
        )

        print(
            exc
        )

        sys.exit(1)

    except Exception as exc:

        print()
        print(
            "FATAL ERROR"
        )

        print(
            exc
        )

        sys.exit(1)


if __name__ == "__main__":
    main()
