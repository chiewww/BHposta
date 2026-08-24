import html
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup


URL = (
    "https://bhpwebout.posta.ba/"
    "KalkulatorCijena_WEB_app/Bos/Default.aspx"
)

COUNTRIES_FILE = Path("countries.txt")
AVAILABLE_FILE = Path("available_countries.txt")
SUSPENDED_FILE = Path("suspended_countries.txt")
RESULTS_FILE = Path("monitor_results.txt")

DESTINATION_SELECT = "ddlMeDoOdrediste"
AIR_CHECKBOX = "chbMeDoAvionski"
AIR_WEIGHT = "tbxMeDoAvioTezina"
DOPISNICA_BUTTON = "ImageButton8"
CALCULATE_BUTTON = "btnMeDoIzracunaj"

WEIGHT = "10"

ERROR_TEXT = (
    "Prijem pošiljaka se trenutno ne vrši za odabranu državu"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/151.0.0.0 "
        "Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,image/avif,image/webp,"
        "*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9,ja;q=0.8",
    "Connection": "keep-alive",
}


# ============================================================
# GENERAL HELPERS
# ============================================================


def response_soup(response):
    response.raise_for_status()

    return BeautifulSoup(
        response.text,
        "html.parser",
    )


def get_hidden_fields(soup):
    data = {}

    for element in soup.select(
        "input[type='hidden']"
    ):
        name = element.get("name")

        if name:
            data[name] = element.get(
                "value",
                "",
            )

    return data


def add_form_controls(soup, data):
    """
    Add current ASP.NET form control values.

    This is important because the BH Pošta page is stateful.
    Sending only the control being clicked can cause the server
    to return the initial page instead of the current calculator
    state.
    """

    form = soup.find("form")

    if not form:
        raise RuntimeError(
            "ASP.NET form was not found."
        )

    for element in form.find_all(
        ["input", "select", "textarea"]
    ):
        name = element.get("name")

        if not name:
            continue

        element_type = element.get(
            "type",
            "",
        ).lower()

        if element_type == "hidden":
            continue

        if element_type in (
            "submit",
            "image",
            "button",
            "reset",
            "file",
        ):
            continue

        if element_type in (
            "checkbox",
            "radio",
        ):
            if element.has_attr("checked"):
                data[name] = element.get(
                    "value",
                    "on",
                )

            continue

        if element.name == "select":
            selected = element.find(
                "option",
                selected=True,
            )

            if selected:
                data[name] = selected.get(
                    "value",
                    "",
                )
            else:
                first = element.find("option")

                if first:
                    data[name] = first.get(
                        "value",
                        "",
                    )

        else:
            data[name] = element.get(
                "value",
                "",
            )


def find_form(soup):
    form = soup.find("form")

    if not form:
        raise RuntimeError(
            "ASP.NET form was not found."
        )

    return form


# ============================================================
# ASP.NET AJAX DELTA PARSER
# ============================================================


def parse_ajax_records(text):
    """
    Parse the actual ASP.NET AJAX pipe-delimited response.

    Example:

        1|#||4|6967|updatePanel|UpdatePanel1|<html...>

    The number immediately before a record is the byte/character
    length of the record payload.

    We parse by length instead of trying to use a greedy regex.
    That is important because UpdatePanel HTML itself contains
    many '|' characters.
    """

    records = []

    position = 0
    length = len(text)

    while position < length:
        # Skip stray separators/newlines.
        while position < length and text[position] in "\r\n":
            position += 1

        if position >= length:
            break

        separator = text.find(
            "|",
            position,
        )

        if separator == -1:
            break

        length_text = text[
            position:separator
        ]

        if not length_text.isdigit():
            # Some ASP.NET responses can contain a leading marker.
            position += 1
            continue

        record_length = int(length_text)

        position = separator + 1

        type_separator = text.find(
            "|",
            position,
        )

        if type_separator == -1:
            break

        record_type = text[
            position:type_separator
        ]

        position = type_separator + 1

        id_separator = text.find(
            "|",
            position,
        )

        if id_separator == -1:
            break

        record_id = text[
            position:id_separator
        ]

        position = id_separator + 1

        record_data = text[
            position:position + record_length
        ]

        if len(record_data) != record_length:
            break

        records.append(
            (
                record_type,
                record_id,
                record_data,
            )
        )

        position += record_length

        # Record terminator.
        if position < length and text[position] == "|":
            position += 1

    return records


def parse_delta_response(
    response,
    old_soup,
):
    """
    Apply an ASP.NET AJAX partial response to the previous page.

    The BH Pošta server returns UpdatePanel1 content as an AJAX
    delta rather than a complete HTML document.
    """

    response.raise_for_status()

    text = response.text

    # Complete HTML response.
    lower = text.lower()

    if (
        "<html" in lower
        or "<!doctype" in lower
    ):
        return BeautifulSoup(
            text,
            "html.parser",
        )

    records = parse_ajax_records(text)

    if not records:
        raise RuntimeError(
            "ASP.NET AJAX response contained no parseable records."
        )

    soup = BeautifulSoup(
        str(old_soup),
        "html.parser",
    )

    hidden_count = 0
    panel_count = 0

    for record_type, record_id, record_data in records:

        record_data = html.unescape(
            record_data
        )

        if record_type == "hiddenField":

            hidden_count += 1

            element = soup.find(
                "input",
                attrs={
                    "name": record_id,
                },
            )

            if element:
                element["value"] = record_data

            else:
                form = soup.find("form")

                if form:
                    new_input = soup.new_tag(
                        "input"
                    )

                    new_input["type"] = "hidden"
                    new_input["name"] = record_id
                    new_input["value"] = record_data

                    form.append(new_input)

        elif record_type == "updatePanel":

            panel_count += 1

            panel = soup.find(
                id=record_id
            )

            if panel:
                new_panel = BeautifulSoup(
                    record_data,
                    "html.parser",
                )

                panel.clear()

                for child in list(
                    new_panel.contents
                ):
                    panel.append(child)

            else:
                # UpdatePanel may not be present in the original
                # DOM. Create it so subsequent controls can still
                # be discovered.
                form = soup.find("form")

                if form:
                    new_panel = soup.new_tag(
                        "div",
                        id=record_id,
                    )

                    parsed = BeautifulSoup(
                        record_data,
                        "html.parser",
                    )

                    for child in list(
                        parsed.contents
                    ):
                        new_panel.append(child)

                    form.append(new_panel)

    print(
        f"DEBUG: AJAX records={len(records)}, "
        f"UpdatePanels={panel_count}, "
        f"hiddenFields={hidden_count}",
        flush=True,
    )

    return soup


# ============================================================
# HTTP POST HELPERS
# ============================================================


def async_post(
    session,
    soup,
    data,
):
    headers = {
        **HEADERS,
        "Referer": URL,
        "Origin": "https://bhpwebout.posta.ba",
        "X-Requested-With": "XMLHttpRequest",
        "X-MicrosoftAjax": "Delta=true",
        "Content-Type": (
            "application/x-www-form-urlencoded; "
            "charset=UTF-8"
        ),
    }

    response = session.post(
        URL,
        data=data,
        headers=headers,
        timeout=90,
    )

    response.raise_for_status()

    return parse_delta_response(
        response,
        soup,
    )


def normal_post(
    session,
    soup,
    data,
):
    headers = {
        **HEADERS,
        "Referer": URL,
        "Origin": "https://bhpwebout.posta.ba",
        "Content-Type": (
            "application/x-www-form-urlencoded"
        ),
    }

    response = session.post(
        URL,
        data=data,
        headers=headers,
        timeout=90,
    )

    response.raise_for_status()

    return response_soup(
        response
    )


# ============================================================
# INTERNATIONAL TAB
# ============================================================


def devexpress_tab_international(
    session,
    soup,
):
    """
    This is the request pattern from the version that successfully
    exposed the destination list.

    Do NOT replace this with guessed DevExpress callback arguments.

    Browser request:

        __EVENTTARGET=ASPxTabControl1
        __EVENTARGUMENT=CLICK:1
        ASPxTabControl1={"activeTabIndex":0}
        UpdatePanel1=ASPxTabControl1
        __ASYNCPOST=true
    """

    print(
        "2. Selecting Međunarodni promet...",
        flush=True,
    )

    data = get_hidden_fields(
        soup
    )

    add_form_controls(
        soup,
        data,
    )

    data["__EVENTTARGET"] = (
        "ASPxTabControl1"
    )

    data["__EVENTARGUMENT"] = (
        "CLICK:1"
    )

    data["ASPxTabControl1"] = (
        '{"activeTabIndex":0}'
    )

    data["UpdatePanel1"] = (
        "ASPxTabControl1"
    )

    data["__ASYNCPOST"] = "true"

    print(
        "   Performing DevExpress tab request...",
        flush=True,
    )

    response = session.post(
        URL,
        data=data,
        headers={
            **HEADERS,
            "Referer": URL,
            "Origin": (
                "https://bhpwebout.posta.ba"
            ),
            "X-MicrosoftAjax": "Delta=true",
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": (
                "application/x-www-form-urlencoded; "
                "charset=UTF-8"
            ),
        },
        timeout=90,
    )

    response.raise_for_status()

    print(
        f"   AJAX response: "
        f"{len(response.text):,} bytes",
        flush=True,
    )

    result = parse_delta_response(
        response,
        soup,
    )

    if DESTINATION_SELECT in str(result):
        print(
            "   Destination selector detected.",
            flush=True,
        )

    return result


# ============================================================
# DOPISNICA
# ============================================================


def click_dopisnica(
    session,
    soup,
):
    """
    Click ImageButton8.

    The destination dropdown should already exist after the
    international tab is selected.
    """

    if not soup.find(
        "select",
        id=DESTINATION_SELECT,
    ):
        raise RuntimeError(
            "Destination selector is missing "
            "before Dopisnica."
        )

    print(
        "3. Selecting Dopisnica...",
        flush=True,
    )

    data = get_hidden_fields(
        soup
    )

    add_form_controls(
        soup,
        data,
    )

    data[
        f"{DOPISNICA_BUTTON}.x"
    ] = "1"

    data[
        f"{DOPISNICA_BUTTON}.y"
    ] = "1"

    result = normal_post(
        session,
        soup,
        data,
    )

    print(
        f"   Destination selector after "
        f"Dopisnica: "
        f"{bool(result.find('select', id=DESTINATION_SELECT))}",
        flush=True,
    )

    return result


# ============================================================
# AIR TRANSPORT
# ============================================================


def enable_air_transport(
    session,
    soup,
):
    """
    Enable chbMeDoAvionski.

    Try the normal ASP.NET postback first, matching the successful
    script. If the server returns the control without checked state,
    retry with the checkbox explicitly posted.
    """

    print(
        "4. Selecting Avionski prijenos...",
        flush=True,
    )

    checkbox = soup.find(
        "input",
        id=AIR_CHECKBOX,
    )

    if not checkbox:
        raise RuntimeError(
            f"#{AIR_CHECKBOX} was not found."
        )

    if checkbox.has_attr("checked"):
        print(
            "   Avionski prijenos already enabled.",
            flush=True,
        )

        return soup

    data = get_hidden_fields(
        soup
    )

    add_form_controls(
        soup,
        data,
    )

    data["__EVENTTARGET"] = (
        AIR_CHECKBOX
    )

    data["__EVENTARGUMENT"] = ""

    data[AIR_CHECKBOX] = "on"

    result = normal_post(
        session,
        soup,
        data,
    )

    checkbox = result.find(
        "input",
        id=AIR_CHECKBOX,
    )

    if checkbox and checkbox.has_attr(
        "checked"
    ):
        print(
            "   Avionski prijenos enabled.",
            flush=True,
        )

        return result

    print(
        "   Checkbox did not expose checked "
        "attribute; continuing with explicit "
        "airmail value.",
        flush=True,
    )

    return result


# ============================================================
# DESTINATIONS
# ============================================================


def get_destinations(soup):
    select = soup.find(
        "select",
        id=DESTINATION_SELECT,
    )

    if not select:
        raise RuntimeError(
            f"#{DESTINATION_SELECT} was not found."
        )

    destinations = []

    for option in select.find_all(
        "option"
    ):
        code = option.get(
            "value",
            "",
        ).strip()

        country = option.get_text(
            " ",
            strip=True,
        )

        if code and country:
            destinations.append(
                (
                    code,
                    country,
                )
            )

    return destinations


# ============================================================
# CALCULATOR
# ============================================================


def select_destination(
    session,
    soup,
    country_code,
):
    """
    Select destination.

    We use the same normal ASP.NET postback pattern that was
    present in the successful country-list script.
    """

    data = get_hidden_fields(
        soup
    )

    add_form_controls(
        soup,
        data,
    )

    data[
        DESTINATION_SELECT
    ] = country_code

    data["__EVENTTARGET"] = (
        DESTINATION_SELECT
    )

    data["__EVENTARGUMENT"] = ""

    return normal_post(
        session,
        soup,
        data,
    )


def calculate(
    session,
    soup,
    country_code,
):
    """
    Submit the actual calculation.

    Important: include the complete current form state.
    """

    data = get_hidden_fields(
        soup
    )

    add_form_controls(
        soup,
        data,
    )

    data[
        DESTINATION_SELECT
    ] = country_code

    data[AIR_CHECKBOX] = "on"

    data[AIR_WEIGHT] = WEIGHT

    data["__EVENTTARGET"] = ""

    data["__EVENTARGUMENT"] = ""

    data[
        CALCULATE_BUTTON
    ] = "Izračunaj"

    # Some ASP.NET forms use the button name as the submit
    # control. Keep it in the payload.
    data[
        f"{CALCULATE_BUTTON}.x"
    ] = "1"

    data[
        f"{CALCULATE_BUTTON}.y"
    ] = "1"

    return normal_post(
        session,
        soup,
        data,
    )


# ============================================================
# RESULT PARSING
# ============================================================


def get_full_text(soup):
    return html.unescape(
        soup.get_text(
            " ",
            strip=True,
        )
    )


def get_error(soup):
    element = soup.find(
        id="lblMeObPiPoruka"
    )

    if element:
        text = " ".join(
            element.stripped_strings
        )

        text = html.unescape(
            text
        )

        text = re.sub(
            r"\s+",
            " ",
            text,
        ).strip()

        if ERROR_TEXT.lower() in text.lower():
            return ERROR_TEXT

        if text:
            return text

    full_text = get_full_text(
        soup
    )

    if ERROR_TEXT.lower() in full_text.lower():
        return ERROR_TEXT

    return None


def get_price(soup):
    """
    Look for the calculator's total price.

    Prefer lblRezultat but also search the complete page because
    some responses move the result element inside an UpdatePanel.
    """

    candidates = []

    element = soup.find(
        id="lblRezultat"
    )

    if element:
        candidates.append(
            " ".join(
                element.stripped_strings
            )
        )

    candidates.append(
        get_full_text(soup)
    )

    for text in candidates:

        text = html.unescape(
            text
        )

        text = re.sub(
            r"\s+",
            " ",
            text,
        ).strip()

        match = re.search(
            r"Ukupna\s+cijena\s*"
            r"([0-9]+(?:[,.][0-9]+)?)"
            r"\s*KM",
            text,
            flags=re.IGNORECASE,
        )

        if match:
            return (
                f"{match.group(1)} KM"
            )

        # Fallback: any KM price.
        match = re.search(
            r"\b"
            r"([0-9]+(?:[,.][0-9]+)?)"
            r"\s*KM\b",
            text,
            flags=re.IGNORECASE,
        )

        if match:
            return (
                f"{match.group(1)} KM"
            )

    return None


def price_value(price):
    if not price:
        return None

    match = re.search(
        r"([0-9]+(?:[,.][0-9]+)?)",
        price,
    )

    if not match:
        return None

    try:
        return float(
            match.group(1).replace(
                ",",
                ".",
            )
        )
    except ValueError:
        return None


# ============================================================
# OUTPUT
# ============================================================


def write_countries(
    destinations,
):
    COUNTRIES_FILE.write_text(
        "\n".join(
            country
            for _, country in destinations
        )
        + "\n",
        encoding="utf-8",
    )


def write_available(
    countries,
):
    AVAILABLE_FILE.write_text(
        "\n".join(countries)
        + "\n",
        encoding="utf-8",
    )


def write_suspended(
    countries,
):
    SUSPENDED_FILE.write_text(
        "\n".join(countries)
        + "\n",
        encoding="utf-8",
    )


def write_results(
    destinations,
    results,
):
    lines = []

    lines.append(
        "BH POSTA - DOPISNICA"
    )
    lines.append(
        "========================================"
    )
    lines.append(
        "Avionski prijenos"
    )
    lines.append(
        f"Tezina: {WEIGHT} g"
    )
    lines.append("")

    lines.append(
        "SVE DESTINACIJE"
    )
    lines.append(
        "========================================"
    )

    for code, country in destinations:
        lines.append(
            f"{code} | {country}"
        )

    lines.append("")

    lines.append(
        "DOSTUPNE"
    )
    lines.append(
        "========================================"
    )

    for result in results:
        if result["status"] == "AVAILABLE":
            lines.append(
                f'{result["country"]} | '
                f'{result["price"]}'
            )

    lines.append("")

    lines.append(
        "NEDOSTUPNE"
    )
    lines.append(
        "========================================"
    )

    for result in results:
        if result["status"] in (
            "UNAVAILABLE",
            "ZERO",
        ):
            lines.append(
                f'{result["country"]} | '
                f'{result["detail"]}'
            )

    lines.append("")

    lines.append(
        "GRESKE"
    )
    lines.append(
        "========================================"
    )

    for result in results:
        if result["status"] == "ERROR":
            lines.append(
                f'{result["country"]} | '
                f'{result["detail"]}'
            )

    lines.append("")

    RESULTS_FILE.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


# ============================================================
# MAIN
# ============================================================


def main():

    session = requests.Session()

    session.headers.update(
        HEADERS
    )

    # --------------------------------------------------------
    # 1. Open calculator
    # --------------------------------------------------------

    print(
        "Opening calculator...",
        flush=True,
    )

    response = session.get(
        URL,
        timeout=90,
    )

    response.raise_for_status()

    soup = response_soup(
        response
    )

    print(
        f"Initial page received: "
        f"{len(response.text):,} bytes",
        flush=True,
    )

    # --------------------------------------------------------
    # 2. Međunarodni promet
    # --------------------------------------------------------

    soup = devexpress_tab_international(
        session,
        soup,
    )

    # --------------------------------------------------------
    # 3. Dopisnica
    # --------------------------------------------------------

    soup = click_dopisnica(
        session,
        soup,
    )

    # --------------------------------------------------------
    # 4. Extract destination list
    # --------------------------------------------------------

    destinations = get_destinations(
        soup
    )

    if not destinations:
        raise RuntimeError(
            "No destinations were found."
        )

    print(
        f"Found {len(destinations)} destinations.",
        flush=True,
    )

    # This is the part your previous script proved works.
    write_countries(
        destinations
    )

    print(
        f"Country list written to "
        f"{COUNTRIES_FILE}",
        flush=True,
    )

    # --------------------------------------------------------
    # 5. Enable air transport
    # --------------------------------------------------------

    soup = enable_air_transport(
        session,
        soup,
    )

    # --------------------------------------------------------
    # 6. Check destinations
    # --------------------------------------------------------

    print(
        "Checking every destination...",
        flush=True,
    )

    results = []

    for number, (
        code,
        country,
    ) in enumerate(
        destinations,
        start=1,
    ):

        print(
            f"[{number}/{len(destinations)}] "
            f"{country} ({code})",
            flush=True,
        )

        try:

            # Select destination.
            soup = select_destination(
                session,
                soup,
                code,
            )

            # Force air transport and 10 g
            # in the calculation request.
            soup = calculate(
                session,
                soup,
                code,
            )

            error = get_error(
                soup
            )

            price = get_price(
                soup
            )

            if error:

                print(
                    f"    -> SUSPENDED: "
                    f"{error}",
                    flush=True,
                )

                results.append(
                    {
                        "code": code,
                        "country": country,
                        "status": "UNAVAILABLE",
                        "price": price,
                        "detail": error,
                    }
                )

            elif price is not None:

                value = price_value(
                    price
                )

                if value == 0:

                    print(
                        "    -> ZERO: 0 KM",
                        flush=True,
                    )

                    results.append(
                        {
                            "code": code,
                            "country": country,
                            "status": "ZERO",
                            "price": price,
                            "detail": (
                                "Ukupna cijena 0 KM"
                            ),
                        }
                    )

                else:

                    print(
                        f"    -> AVAILABLE: "
                        f"{price}",
                        flush=True,
                    )

                    results.append(
                        {
                            "code": code,
                            "country": country,
                            "status": "AVAILABLE",
                            "price": price,
                            "detail": price,
                        }
                    )

            else:

                print(
                    "    -> ERROR: "
                    "price not found",
                    flush=True,
                )

                results.append(
                    {
                        "code": code,
                        "country": country,
                        "status": "ERROR",
                        "price": None,
                        "detail": (
                            "Ukupna cijena nije "
                            "pronađena"
                        ),
                    }
                )

        except Exception as exc:

            print(
                f"    -> ERROR: {exc}",
                flush=True,
            )

            results.append(
                {
                    "code": code,
                    "country": country,
                    "status": "ERROR",
                    "price": None,
                    "detail": str(exc),
                }
            )

            # Re-open the calculator state if a particular
            # destination POST breaks the current soup.
            #
            # This prevents one bad country from poisoning every
            # subsequent request.
            try:

                response = session.get(
                    URL,
                    timeout=90,
                )

                response.raise_for_status()

                soup = response_soup(
                    response
                )

                soup = devexpress_tab_international(
                    session,
                    soup,
                )

                soup = click_dopisnica(
                    session,
                    soup,
                )

                soup = enable_air_transport(
                    session,
                    soup,
                )

            except Exception as recovery_exc:

                print(
                    f"    Recovery failed: "
                    f"{recovery_exc}",
                    flush=True,
                )

        time.sleep(0.75)

    # --------------------------------------------------------
    # 7. Generate country files
    # --------------------------------------------------------

    available = [
        result["country"]
        for result in results
        if result["status"] == "AVAILABLE"
    ]

    suspended = [
        result["country"]
        for result in results
        if result["status"] in (
            "UNAVAILABLE",
            "ZERO",
        )
    ]

    write_available(
        available
    )

    write_suspended(
        suspended
    )

    write_results(
        destinations,
        results,
    )

    # --------------------------------------------------------
    # 8. Summary
    # --------------------------------------------------------

    available_count = sum(
        result["status"] == "AVAILABLE"
        for result in results
    )

    suspended_count = sum(
        result["status"] in (
            "UNAVAILABLE",
            "ZERO",
        )
        for result in results
    )

    error_count = sum(
        result["status"] == "ERROR"
        for result in results
    )

    print()
    print(
        "========================================"
    )
    print(
        "Finished."
    )
    print(
        f"Destinations: {len(results)}"
    )
    print(
        f"Available:    {available_count}"
    )
    print(
        f"Suspended:    {suspended_count}"
    )
    print(
        f"Errors:       {error_count}"
    )
    print()
    print(
        f"Countries:    {COUNTRIES_FILE}"
    )
    print(
        f"Available:    {AVAILABLE_FILE}"
    )
    print(
        f"Suspended:    {SUSPENDED_FILE}"
    )
    print(
        f"Results:      {RESULTS_FILE}"
    )
    print(
        "========================================"
    )


if __name__ == "__main__":

    try:
        main()

    except Exception as exc:

        print(
            f"FATAL ERROR: {exc}",
            file=sys.stderr,
        )

        sys.exit(1)
