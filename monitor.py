import re
import time
from pathlib import Path
from html import unescape

import requests
from bs4 import BeautifulSoup


URL = "https://bhpwebout.posta.ba/KalkulatorCijena_WEB_app/Bos/Default.aspx"

AVAILABLE_FILE = Path("available_countries.txt")
SUSPENDED_FILE = Path("suspended_countries.txt")

WEIGHT = "10"

SUSPENDED_MESSAGE = (
    "Prijem pošiljaka se trenutno ne vrši za odabranu državu"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0 Safari/537.36"
    ),
}


def hidden_fields(html):
    """
    Extract all ASP.NET hidden input fields from the current response.
    """
    soup = BeautifulSoup(html, "html.parser")

    data = {}

    for inp in soup.select("input[type=hidden]"):
        name = inp.get("name")
        if name:
            data[name] = inp.get("value", "")

    return data


def country_list(html):
    """
    Extract the country value/text pairs from ddlMeDoOdrediste.
    """
    soup = BeautifulSoup(html, "html.parser")

    select = soup.find("select", id="ddlMeDoOdrediste")

    if not select:
        raise RuntimeError(
            "Could not find ddlMeDoOdrediste in the response."
        )

    countries = []

    for option in select.find_all("option"):
        value = option.get("value")
        name = option.get_text(strip=True)

        if value and name:
            countries.append((value, name))

    return countries


def make_async_headers():
    return {
        **HEADERS,
        "X-Requested-With": "XMLHttpRequest",
    }


def async_post(session, html, event_target, extra_data=None):
    """
    Perform an ASP.NET UpdatePanel-style async postback.

    The current hidden fields are taken from the latest HTML response.
    """
    data = hidden_fields(html)

    data["__EVENTTARGET"] = event_target
    data["__EVENTARGUMENT"] = ""

    # ASP.NET AJAX identifies the async control.
    data["__ASYNCPOST"] = "true"

    if extra_data:
        data.update(extra_data)

    response = session.post(
        URL,
        data=data,
        headers=make_async_headers(),
        timeout=90,
    )

    response.raise_for_status()

    return response.text


def full_post(session, html, form_data):
    """
    Perform the final form submission for Izračunaj.
    """
    data = hidden_fields(html)
    data.update(form_data)

    response = session.post(
        URL,
        data=data,
        headers=HEADERS,
        timeout=90,
    )

    response.raise_for_status()

    return response.text


def response_contains_suspended(html):
    return SUSPENDED_MESSAGE in unescape(html)


def response_contains_price(html):
    """
    Look for the calculator's price/result.

    We deliberately don't hard-code the price because it can change.
    """
    text = BeautifulSoup(
        unescape(html),
        "html.parser"
    ).get_text(" ", strip=True)

    # Typical result wording from the calculator.
    if "Ukupna cijena" in text:
        return True

    # Also accept a KM amount if the wording changes slightly.
    if re.search(r"\b\d+(?:[,.]\d+)?\s*KM\b", text):
        return True

    return False


def activate_dopisnica_and_airmail(session, html):
    """
    Navigate the controls needed for:
      Međunarodni promet
      Dopisnica
      Avionski prijenos
    """

    # The initial page should already expose the international controls.
    # If Dopisnica is not present, we click ImageButton8.
    soup = BeautifulSoup(html, "html.parser")

    if not soup.find("select", id="ddlMeDoOdrediste"):
        print("Country selector not present yet.")

        html = full_post(
            session,
            html,
            {
                "ImageButton8.x": "1",
                "ImageButton8.y": "1",
            },
        )

    # Check whether Avionski prijenos is already checked.
    soup = BeautifulSoup(html, "html.parser")

    aviation = soup.find(
        "input",
        id="chbMeDoAvionski"
    )

    if not aviation:
        raise RuntimeError(
            "Could not find chbMeDoAvionski."
        )

    if not aviation.has_attr("checked"):
        print("Enabling Avionski prijenos...")

        html = async_post(
            session,
            html,
            "chbMeDoAvionski",
            {
                "chbMeDoAvionski": "on",
            },
        )

    return html


def set_country(session, html, country_code):
    """
    Select a destination country.

    The real site has onchange=__doPostBack('ddlMeDoOdrediste',''),
    so we reproduce that event.
    """
    return async_post(
        session,
        html,
        "ddlMeDoOdrediste",
        {
            "ddlMeDoOdrediste": country_code,
        },
    )


def calculate(session, html, country_code):
    """
    Submit the calculator for one country at 10 grams.
    """
    form = {
        "ddlMeDoOdrediste": country_code,

        # The three optional services remain unchecked.
        # Do not send them.

        # Air transport is checked.
        "chbMeDoAvionski": "on",

        "tbxMeDoAvioTezina": WEIGHT,

        "btnMeDoIzracunaj": "Izračunaj",
    }

    return full_post(session, html, form)


def main():
    session = requests.Session()
    session.headers.update(HEADERS)

    print("Opening calculator...")

    response = session.get(
        URL,
        timeout=90,
    )
    response.raise_for_status()

    html = response.text

    # Activate required service.
    html = activate_dopisnica_and_airmail(
        session,
        html,
    )

    # Obtain the country list from the current page.
    countries = country_list(html)

    print(f"Found {len(countries)} destination entries.")

    available = []
    suspended = []

    for number, (code, name) in enumerate(countries, start=1):

        print(
            f"[{number}/{len(countries)}] "
            f"{name} ({code})"
        )

        try:
            # Select country.
            html = set_country(
                session,
                html,
                code,
            )

            # Make sure the weight is present after the country
            # postback. Some Web Forms applications regenerate
            # controls during postback.
            html = calculate(
                session,
                html,
                code,
            )

            if response_contains_suspended(html):
                print("    SUSPENDED")
                suspended.append(name)

            elif response_contains_price(html):
                print("    AVAILABLE")
                available.append(name)

            else:
                print("    UNKNOWN RESULT")
                print(
                    "    The response contained neither "
                    "the suspension message nor a price."
                )

        except Exception as exc:
            print(
                f"    ERROR: {type(exc).__name__}: {exc}"
            )

        # Be polite to the server.
        time.sleep(0.5)

    # Write raw text lists.
    AVAILABLE_FILE.write_text(
        "\n".join(available) + "\n",
        encoding="utf-8",
    )

    SUSPENDED_FILE.write_text(
        "\n".join(suspended) + "\n",
        encoding="utf-8",
    )

    print()
    print("Finished.")
    print(f"Available countries: {AVAILABLE_FILE}")
    print(f"Suspended countries: {SUSPENDED_FILE}")


if __name__ == "__main__":
    main()
