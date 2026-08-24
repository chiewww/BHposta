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

AVAILABLE_FILE = Path("available_countries.txt")
SUSPENDED_FILE = Path("suspended_countries.txt")
UNKNOWN_FILE = Path("unknown_countries.txt")
ERROR_FILE = Path("error_countries.txt")
OUTPUT_FILE = Path("output.txt")

DESTINATION_SELECT = "ddlMeDoOdrediste"
AIR_CHECKBOX = "chbMeDoAvionski"
AIR_WEIGHT = "tbxMeDoAvioTezina"
DOPISNICA_BUTTON = "ImageButton8"

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
    "Accept-Language": "en-US,en;q=0.9",
}


# ============================================================
# General helpers
# ============================================================

def response_soup(response):
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def get_hidden_fields(soup):
    data = {}

    for element in soup.select("input[type='hidden']"):
        name = element.get("name")

        if name:
            data[name] = element.get("value", "")

    return data


def add_form_controls(soup, data):
    """
    Add the current ASP.NET form controls.
    """

    form = soup.find("form")

    if not form:
        raise RuntimeError("ASP.NET form was not found.")

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

    return data


# ============================================================
# ASP.NET AJAX parser
# ============================================================

def parse_ajax_records(text):
    """
    Parse the ASP.NET AJAX pipe-delimited response.

    The BH Posta server returns records such as:

        updatePanel
        hiddenField
        scriptBlock
        scriptStartupBlock

    This parser intentionally preserves the HTML returned by
    UpdatePanel records.
    """

    records = []

    position = 0
    text_length = len(text)

    while position < text_length:

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
            position += 1
            continue

        record_length = int(
            length_text
        )

        record_start = separator + 1

        if record_start >= text_length:
            break

        type_separator = text.find(
            "|",
            record_start,
        )

        if type_separator == -1:
            break

        record_type = text[
            record_start:type_separator
        ]

        content_start = (
            type_separator + 1
        )

        if record_type in (
            "updatePanel",
            "hiddenField",
            "scriptBlock",
            "scriptStartupBlock",
        ):
            content_end = (
                content_start
                + record_length
            )

            if content_end <= text_length:

                content = text[
                    content_start:content_end
                ]

                records.append(
                    (
                        record_type,
                        content,
                    )
                )

                position = (
                    content_end + 1
                )

                continue

        position = content_start

    return records


def parse_delta_response(
    response,
    old_soup,
    debug_name=None,
):
    """
    Process an ASP.NET AJAX response.

    The original document is retained and UpdatePanel contents
    are merged into it.
    """

    response.raise_for_status()

    text = response.text

    if debug_name:
        Path(debug_name).write_text(
            text,
            encoding="utf-8",
        )

    lower = text.lower()

    # Complete HTML response.
    if (
        "<html" in lower
        or "<!doctype" in lower
    ):
        return BeautifulSoup(
            text,
            "html.parser",
        )

    soup = BeautifulSoup(
        str(old_soup),
        "html.parser",
    )

    records = parse_ajax_records(
        text
    )

    update_panel_count = sum(
        1
        for record_type, _ in records
        if record_type == "updatePanel"
    )

    hidden_field_count = sum(
        1
        for record_type, _ in records
        if record_type == "hiddenField"
    )

    print(
        "DEBUG: AJAX records="
        f"{len(records)}, "
        f"UpdatePanels={update_panel_count}, "
        f"hiddenFields={hidden_field_count}"
    )

    # --------------------------------------------------------
    # Hidden fields
    # --------------------------------------------------------

    for record_type, content in records:

        if record_type != "hiddenField":
            continue

        parts = content.split(
            "|",
            1,
        )

        if len(parts) != 2:
            continue

        name, value = parts

        value = html.unescape(
            value
        )

        element = soup.find(
            "input",
            attrs={
                "name": name,
            },
        )

        if element:
            element["value"] = value

        else:
            form = soup.find("form")

            if form:
                new_input = soup.new_tag(
                    "input",
                    type="hidden",
                    name=name,
                    value=value,
                )

                form.append(
                    new_input
                )

    # --------------------------------------------------------
    # UpdatePanel contents
    # --------------------------------------------------------

    for record_type, content in records:

        if record_type != "updatePanel":
            continue

        parts = content.split(
            "|",
            1,
        )

        if len(parts) != 2:
            continue

        panel_id, panel_html = parts

        panel = soup.find(
            id=panel_id
        )

        if not panel:
            continue

        new_panel = BeautifulSoup(
            panel_html,
            "html.parser",
        )

        panel.clear()

        for child in list(
            new_panel.contents
        ):
            panel.append(child)

    return soup


# ============================================================
# Normal ASP.NET POST
# ============================================================

def normal_post(
    session,
    soup,
    data,
    debug_name=None,
):
    response = session.post(
        URL,
        data=data,
        timeout=90,
        headers={
            **HEADERS,
            "Referer": URL,
            "Origin": (
                "https://bhpwebout.posta.ba"
            ),
            "Content-Type": (
                "application/x-www-form-urlencoded"
            ),
        },
    )

    response.raise_for_status()

    if debug_name:
        Path(debug_name).write_text(
            response.text,
            encoding="utf-8",
        )

    return response_soup(
        response
    )


# ============================================================
# Međunarodni promet
# ============================================================

def devexpress_tab_international(
    session,
    soup,
):
    """
    Select Međunarodni promet.

    Important:
    Do NOT require ddlMeDoOdrediste after this request.

    The successful sequence is:

        initial page
             ↓
        Međunarodni promet
             ↓
        Dopisnica
             ↓
        destination selector
    """

    print(
        "   Performing DevExpress tab request..."
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

    response = session.post(
        URL,
        data=data,
        timeout=90,
        headers={
            **HEADERS,
            "Referer": URL,
            "Origin": (
                "https://bhpwebout.posta.ba"
            ),
            "X-MicrosoftAjax": "Delta=true",
            "X-Requested-With": (
                "XMLHttpRequest"
            ),
            "Content-Type": (
                "application/x-www-form-urlencoded; "
                "charset=UTF-8"
            ),
        },
    )

    response.raise_for_status()

    print(
        "   AJAX response: "
        f"{len(response.text):,} bytes"
    )

    soup = parse_delta_response(
        response,
        soup,
        "debug_international_response.txt",
    )

    if not soup.find("form"):
        raise RuntimeError(
            "ASP.NET form disappeared after "
            "Međunarodni promet request."
        )

    print(
        "   Međunarodni promet request processed."
    )

    return soup


# ============================================================
# Dopisnica
# ============================================================

def click_dopisnica(
    session,
    soup,
):
    """
    Click ImageButton8 = Dopisnica.

    IMPORTANT:

    There must NOT be a requirement for
    ddlMeDoOdrediste before this request.
    """

    print(
        "   Clicking Dopisnica..."
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

    response = session.post(
        URL,
        data=data,
        timeout=90,
        headers={
            **HEADERS,
            "Referer": URL,
            "Origin": (
                "https://bhpwebout.posta.ba"
            ),
            "Content-Type": (
                "application/x-www-form-urlencoded"
            ),
        },
    )

    response.raise_for_status()

    print(
        "   Dopisnica response: "
        f"{len(response.text):,} bytes"
    )

    Path(
        "debug_dopisnica_response.html"
    ).write_text(
        response.text,
        encoding="utf-8",
    )

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    select = soup.find(
        "select",
        id=DESTINATION_SELECT,
    )

    if not select:

        # Save the page for diagnosis.
        Path(
            "debug_after_dopisnica.html"
        ).write_text(
            str(soup),
            encoding="utf-8",
        )

        raise RuntimeError(
            "Dopisnica POST completed, but "
            f"#{DESTINATION_SELECT} was not returned."
        )

    print(
        "   Destination selector found."
    )

    return soup


# ============================================================
# Avionski prijenos
# ============================================================

def click_air_transport(
    session,
    soup,
):
    print(
        "   Selecting Avionski prijenos..."
    )

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

    soup = normal_post(
        session,
        soup,
        data,
        "debug_air_transport.html",
    )

    return soup


# ============================================================
# Weight
# ============================================================

def set_weight(
    session,
    soup,
    weight,
):
    print(
        f"   Setting weight to {weight} g..."
    )

    data = get_hidden_fields(
        soup
    )

    add_form_controls(
        soup,
        data,
    )

    data[AIR_CHECKBOX] = "on"

    data[AIR_WEIGHT] = str(
        weight
    )

    data["__EVENTTARGET"] = ""

    data["__EVENTARGUMENT"] = ""

    soup = normal_post(
        session,
        soup,
        data,
        "debug_weight.html",
    )

    return soup


# ============================================================
# Destination list
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
# Destination selection
# ============================================================

def select_destination(
    session,
    soup,
    country_code,
):
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


# ============================================================
# Result parsing
# ============================================================

def get_price(soup):

    element = soup.find(
        id="lblRezultat"
    )

    if not element:
        return None

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

    match = re.search(
        r"Ukupna\s+cijena\s+"
        r"([0-9]+(?:[,.][0-9]+)?)"
        r"\s*KM",
        text,
        flags=re.IGNORECASE,
    )

    if not match:
        return None

    return (
        f"{match.group(1)} KM"
    )


def get_error(soup):

    element = soup.find(
        id="lblMeObPiPoruka"
    )

    if not element:
        return None

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

    return text or None


def is_zero_price(price):

    if not price:
        return False

    normalized = price.replace(
        ",",
        ".",
    )

    match = re.search(
        r"([0-9]+(?:\.[0-9]+)?)"
        r"\s*KM",
        normalized,
    )

    if not match:
        return False

    return (
        float(match.group(1))
        == 0
    )


# ============================================================
# Output
# ============================================================

def write_country_files(
    results
):
    available = []
    suspended = []
    unknown = []
    errors = []

    for result in results:

        country = result["country"]

        status = result["status"]

        if status == "AVAILABLE":
            available.append(
                country
            )

        elif status in (
            "UNAVAILABLE",
            "ZERO",
        ):
            suspended.append(
                country
            )

        elif status == "UNKNOWN":
            unknown.append(
                country
            )

        elif status == "ERROR":
            errors.append(
                country
            )

    AVAILABLE_FILE.write_text(
        "\n".join(available)
        + (
            "\n"
            if available
            else ""
        ),
        encoding="utf-8",
    )

    SUSPENDED_FILE.write_text(
        "\n".join(suspended)
        + (
            "\n"
            if suspended
            else ""
        ),
        encoding="utf-8",
    )

    UNKNOWN_FILE.write_text(
        "\n".join(unknown)
        + (
            "\n"
            if unknown
            else ""
        ),
        encoding="utf-8",
    )

    ERROR_FILE.write_text(
        "\n".join(errors)
        + (
            "\n"
            if errors
            else ""
        ),
        encoding="utf-8",
    )


def write_output(
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
        "Prijenos: Avionski prijenos"
    )

    lines.append(
        "Tezina: 10 g"
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
        "CIJENE"
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
        "NEDOSTUPNE ILI CIJENA 0 KM"
    )

    lines.append(
        "========================================"
    )

    unavailable = [
        result
        for result in results
        if result["status"] in (
            "UNAVAILABLE",
            "ZERO",
        )
    ]

    if unavailable:

        for result in unavailable:

            lines.append(
                f'{result["country"]} | '
                f'{result["detail"]}'
            )

    else:
        lines.append("Nema")

    lines.append("")

    lines.append(
        "NEODREĐENO"
    )

    lines.append(
        "========================================"
    )

    unknown = [
        result
        for result in results
        if result["status"] == "UNKNOWN"
    ]

    if unknown:

        for result in unknown:

            lines.append(
                f'{result["country"]} | '
                f'{result["detail"]}'
            )

    else:
        lines.append("Nema")

    lines.append("")

    lines.append(
        "GREŠKE PRI PROVJERI"
    )

    lines.append(
        "========================================"
    )

    errors = [
        result
        for result in results
        if result["status"] == "ERROR"
    ]

    if errors:

        for result in errors:

            lines.append(
                f'{result["country"]} | '
                f'{result["detail"]}'
            )

    else:
        lines.append("Nema")

    lines.append("")

    OUTPUT_FILE.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


# ============================================================
# Main
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
        "Opening calculator..."
    )

    response = session.get(
        URL,
        timeout=90,
    )

    response.raise_for_status()

    print(
        "Initial page received: "
        f"{len(response.text):,} bytes"
    )

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    Path(
        "debug_original_page.html"
    ).write_text(
        response.text,
        encoding="utf-8",
    )

    # --------------------------------------------------------
    # 2. Međunarodni promet
    # --------------------------------------------------------

    print(
        "2. Selecting Međunarodni promet..."
    )

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
    # 4. Read countries
    # --------------------------------------------------------

    destinations = get_destinations(
        soup
    )

    print(
        "   Found "
        f"{len(destinations)} "
        "destinations."
    )

    if not destinations:
        raise RuntimeError(
            "Destination selector exists "
            "but contains no countries."
        )

    # --------------------------------------------------------
    # 5. Avionski prijenos
    # --------------------------------------------------------

    soup = click_air_transport(
        session,
        soup,
    )

    # --------------------------------------------------------
    # 6. Set 10 g
    # --------------------------------------------------------

    soup = set_weight(
        session,
        soup,
        WEIGHT,
    )

    # The destination list may survive the POST,
    # but if it does not, retain the list already obtained.

    try:

        destinations_after_weight = (
            get_destinations(soup)
        )

        if destinations_after_weight:
            destinations = (
                destinations_after_weight
            )

    except RuntimeError:

        print(
            "   WARNING: destination selector "
            "not present after weight POST."
        )

        print(
            "   Keeping destination list "
            "from Dopisnica response."
        )

    print(
        "   Destination list contains "
        f"{len(destinations)} countries."
    )

    # --------------------------------------------------------
    # 7. Check every destination
    # --------------------------------------------------------

    print(
        "3. Checking every destination..."
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
            f"   [{number}/{len(destinations)}] "
            f"{country}",
            flush=True,
        )

        try:

            soup = select_destination(
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
                    "      -> UNAVAILABLE",
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

            elif is_zero_price(
                price
            ):

                print(
                    "      -> ZERO",
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

            elif price:

                print(
                    "      -> AVAILABLE "
                    f"({price})",
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
                    "      -> UNKNOWN",
                    flush=True,
                )

                results.append(
                    {
                        "code": code,
                        "country": country,
                        "status": "UNKNOWN",
                        "price": None,
                        "detail": (
                            "Ukupna cijena nije "
                            "pronađena"
                        ),
                    }
                )

        except Exception as exc:

            print(
                f"      -> ERROR: {exc}",
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

        time.sleep(0.5)

    # --------------------------------------------------------
    # 8. Write output
    # --------------------------------------------------------

    print(
        "4. Writing result files..."
    )

    write_country_files(
        results
    )

    write_output(
        destinations,
        results,
    )

    # --------------------------------------------------------
    # 9. Summary
    # --------------------------------------------------------

    available = sum(
        result["status"]
        == "AVAILABLE"
        for result in results
    )

    unavailable = sum(
        result["status"]
        in (
            "UNAVAILABLE",
            "ZERO",
        )
        for result in results
    )

    unknown = sum(
        result["status"]
        == "UNKNOWN"
        for result in results
    )

    errors = sum(
        result["status"]
        == "ERROR"
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
        f"Available:    {available}"
    )

    print(
        f"Unavailable:  {unavailable}"
    )

    print(
        f"Unknown:      {unknown}"
    )

    print(
        f"Errors:       {errors}"
    )

    print(
        f"Output:       {OUTPUT_FILE}"
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
