import re
import time
from pathlib import Path
from html import unescape

import requests
from bs4 import BeautifulSoup


URL = (
    "https://bhpwebout.posta.ba/"
    "KalkulatorCijena_WEB_app/Bos/Default.aspx"
)

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
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,image/avif,image/webp,"
        "*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# ============================================================
# GENERAL HELPERS
# ============================================================

def save_debug(name, content):
    Path(name).write_text(
        content,
        encoding="utf-8",
    )

    print(
        f"DEBUG: Saved {name}"
    )


def get_hidden_fields(html):
    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    result = {}

    for element in soup.select(
        "input[type='hidden']"
    ):
        name = element.get("name")

        if name:
            result[name] = element.get(
                "value",
                "",
            )

    return result


def parse_countries(html):
    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    select = soup.find(
        "select",
        id="ddlMeDoOdrediste",
    )

    if not select:
        return []

    countries = []

    for option in select.find_all(
        "option"
    ):
        value = option.get("value")
        name = option.get_text(
            " ",
            strip=True,
        )

        if value and name:
            countries.append(
                (
                    value,
                    name,
                )
            )

    return countries


# ============================================================
# DEVEXPRESS / PAGE INSPECTION
# ============================================================

def inspect_tab_control(html):
    """
    Inspect the actual ASPxTabControl1 markup and scripts.

    We do not assume that __EVENTARGUMENT='1' is sufficient.
    """

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    print(
        "DEBUG: Inspecting DevExpress tab control..."
    )

    elements = soup.find_all(
        id=re.compile(
            r"ASPxTabControl1",
            re.I,
        )
    )

    print(
        f"DEBUG: Found {len(elements)} "
        "elements related to ASPxTabControl1."
    )

    for element in elements:

        print(
            "DEBUG TAB:",
            element.name,
            "id=",
            element.get("id"),
            "name=",
            element.get("name"),
            "class=",
            element.get("class"),
        )

        # Print useful attributes.
        for key, value in element.attrs.items():

            if key.lower() in {
                "id",
                "name",
                "class",
                "onclick",
                "onchange",
                "clientinstance",
                "data",
            }:
                print(
                    f"DEBUG TAB ATTR {key}: {value}"
                )

    # --------------------------------------------------------
    # Search scripts for ASPxTabControl1.
    # --------------------------------------------------------

    matches = []

    for script in soup.find_all("script"):

        text = script.string

        if not text:
            text = script.get_text()

        if not text:
            continue

        if (
            "ASPxTabControl1" in text
            or "ASPxClientTabControl" in text
            or "SetActiveTab" in text
            or "SetActiveTabIndex" in text
        ):

            matches.append(text)

    print(
        f"DEBUG: Found {len(matches)} "
        "script blocks related to tab control."
    )

    for index, text in enumerate(
        matches,
        start=1,
    ):

        filename = (
            f"debug_tab_script_{index}.txt"
        )

        save_debug(
            filename,
            text,
        )

        # Print only useful lines.
        for line in text.splitlines():

            if (
                "ASPxTabControl1" in line
                or "SetActiveTab" in line
                or "TabClick" in line
                or "tab" in line.lower()
                and (
                    "ASPx" in line
                    or "callback" in line.lower()
                    or "postback" in line.lower()
                )
            ):

                print(
                    "DEBUG SCRIPT:",
                    line[:500],
                )


# ============================================================
# AJAX RESPONSE PARSER
# ============================================================

def parse_ajax_delta(text):
    """
    Parse ASP.NET PageRequestManager response records.

    We specifically collect updatePanel and hiddenField
    records.
    """

    result = {
        "panels": {},
        "hidden_fields": {},
    }

    if not text:
        return result

    position = 0
    total = len(text)

    while position < total:

        first_pipe = text.find(
            "|",
            position,
        )

        if first_pipe == -1:
            break

        length_text = text[
            position:first_pipe
        ]

        if not length_text.isdigit():

            position += 1
            continue

        record_length = int(
            length_text
        )

        record_type_start = (
            first_pipe + 1
        )

        second_pipe = text.find(
            "|",
            record_type_start,
        )

        if second_pipe == -1:
            break

        record_type = text[
            record_type_start:second_pipe
        ]

        content_start = (
            second_pipe + 1
        )

        content_end = (
            content_start + record_length
        )

        if content_end > total:
            break

        content = text[
            content_start:content_end
        ]

        if record_type == "updatePanel":

            separator = content.find(
                "|"
            )

            if separator >= 0:

                panel_id = content[
                    :separator
                ]

                panel_content = content[
                    separator + 1:
                ]

                result[
                    "panels"
                ][panel_id] = panel_content

        elif record_type == "hiddenField":

            separator = content.find(
                "|"
            )

            if separator >= 0:

                name = content[
                    :separator
                ]

                value = content[
                    separator + 1:
                ]

                result[
                    "hidden_fields"
                ][name] = value

        position = content_end

    return result


def merge_ajax_response(
    original_html,
    ajax_text,
):
    """
    Merge an ASP.NET AJAX response into the
    original full page.

    Never replace the full document with an AJAX
    response.
    """

    parsed = parse_ajax_delta(
        ajax_text
    )

    print(
        "DEBUG: ASP.NET AJAX parser found "
        f"{sum(len(x) for x in parsed['panels'].values()):,} "
        "bytes of UpdatePanel content."
    )

    print(
        "DEBUG: Returned hidden fields: "
        f"{len(parsed['hidden_fields'])}"
    )

    if not parsed["panels"]:

        return original_html

    soup = BeautifulSoup(
        original_html,
        "html.parser",
    )

    for panel_id, panel_html in (
        parsed["panels"].items()
    ):

        panel = soup.find(
            id=panel_id
        )

        if not panel:

            print(
                f"DEBUG: Panel {panel_id} "
                "does not exist in original page."
            )

            continue

        replacement = BeautifulSoup(
            panel_html,
            "html.parser",
        )

        panel.clear()

        for child in list(
            replacement.contents
        ):
            panel.append(child)

    # Update hidden fields.
    for name, value in (
        parsed["hidden_fields"].items()
    ):

        element = soup.find(
            "input",
            attrs={
                "name": name,
            },
        )

        if not element:

            element = soup.find(
                "input",
                id=name,
            )

        if element:

            element["value"] = value

    return str(soup)


# ============================================================
# POST HELPERS
# ============================================================

def post_async(
    session,
    html,
    event_target,
    event_argument="",
    extra=None,
):
    data = get_hidden_fields(
        html
    )

    data["__EVENTTARGET"] = (
        event_target
    )

    data["__EVENTARGUMENT"] = (
        event_argument
    )

    data["__ASYNCPOST"] = "true"

    if extra:
        data.update(extra)

    headers = {
        **HEADERS,
        "X-Requested-With": "XMLHttpRequest",
        "X-MicrosoftAjax": "Delta=true",
        "Referer": URL,
        "Accept": "*/*",
    }

    response = session.post(
        URL,
        data=data,
        headers=headers,
        timeout=90,
    )

    response.raise_for_status()

    return response


def post_normal(
    session,
    html,
    extra,
):
    data = get_hidden_fields(
        html
    )

    data.update(extra)

    headers = {
        **HEADERS,
        "Referer": URL,
    }

    response = session.post(
        URL,
        data=data,
        headers=headers,
        timeout=90,
    )

    response.raise_for_status()

    return response


# ============================================================
# FIND DEVEXPRESS CLIENT CONFIGURATION
# ============================================================

def find_tab_configuration(html):
    """
    Search page JavaScript for the actual DevExpress
    initialization/configuration of ASPxTabControl1.

    Returns useful strings for diagnostics.
    """

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    results = []

    for script in soup.find_all(
        "script"
    ):

        text = script.get_text()

        if not text:
            continue

        if (
            "ASPxTabControl1" in text
            or "SetActiveTabIndex" in text
            or "SetActiveTab(" in text
        ):

            results.append(text)

    return results


# ============================================================
# INTERNATIONAL TAB
# ============================================================

def activate_international(
    session,
    html,
):
    print(
        "Activating Međunarodni promet..."
    )

    if "ddlMeDoOdrediste" in html:

        print(
            "International selector already present."
        )

        return html

    # --------------------------------------------------------
    # Save original page.
    # --------------------------------------------------------

    save_debug(
        "debug_original_page.html",
        html,
    )

    inspect_tab_control(
        html
    )

    scripts = find_tab_configuration(
        html
    )

    print(
        f"DEBUG: Relevant DevExpress scripts: "
        f"{len(scripts)}"
    )

    # --------------------------------------------------------
    # Extract possible tab indices/keys from the scripts.
    # --------------------------------------------------------

    candidates = []

    for script in scripts:

        # Common SetActiveTabIndex(1)
        for match in re.finditer(
            r"SetActiveTabIndex\s*\(\s*(\d+)\s*\)",
            script,
            re.I,
        ):

            candidates.append(
                ("index", match.group(1))
            )

        # Common SetActiveTab(...)
        for match in re.finditer(
            r"SetActiveTab\s*\(\s*([^)]+)\)",
            script,
            re.I,
        ):

            candidates.append(
                ("tab", match.group(1).strip())
            )

    # Always retain the known international index.
    candidates.append(
        ("index", "1")
    )

    # Deduplicate.
    seen = set()
    unique_candidates = []

    for candidate in candidates:

        if candidate in seen:
            continue

        seen.add(candidate)
        unique_candidates.append(
            candidate
        )

    print(
        "DEBUG: Tab candidates:",
        unique_candidates,
    )

    # --------------------------------------------------------
    # Strategy 1:
    #
    # ASP.NET AJAX postback with ASPxTabControl1.
    # --------------------------------------------------------

    for candidate_type, candidate in (
        unique_candidates
    ):

        print(
            f"Trying ASPxTabControl1 "
            f"{candidate_type}={candidate}..."
        )

        try:

            response = post_async(
                session,
                html,
                "ASPxTabControl1",
                candidate,
            )

            response_text = (
                response.text
            )

            print(
                "DEBUG: Response size: "
                f"{len(response_text):,} bytes"
            )

            filename_candidate = re.sub(
                r"[^A-Za-z0-9_.-]",
                "_",
                candidate,
            )

            save_debug(
                (
                    "debug_international_"
                    f"ASPxTabControl1_"
                    f"{candidate_type}_"
                    f"{filename_candidate}.txt"
                ),
                response_text,
            )

            # Direct response.
            if (
                "ddlMeDoOdrediste"
                in response_text
            ):

                print(
                    "DEBUG: Country selector "
                    "returned directly."
                )

                return response_text

            # AJAX merge.
            if "|updatePanel|" in (
                response_text
            ):

                merged = merge_ajax_response(
                    html,
                    response_text,
                )

                if (
                    "ddlMeDoOdrediste"
                    in merged
                ):

                    print(
                        "International tab activated "
                        "through AJAX merge."
                    )

                    return merged

        except Exception as exc:

            print(
                "DEBUG: Candidate failed:",
                exc,
            )

    # --------------------------------------------------------
    # Strategy 2:
    #
    # Try common DevExpress callback argument forms.
    #
    # These are deliberately attempted only after the actual
    # page configuration has been inspected.
    # --------------------------------------------------------

    callback_arguments = [
        "1",
        "1|",
        "0|1",
        "C1",
        "1|0",
    ]

    for argument in callback_arguments:

        print(
            "Trying DevExpress callback "
            f"parameter='{argument}'..."
        )

        try:

            data = get_hidden_fields(
                html
            )

            data["__CALLBACKID"] = (
                "ASPxTabControl1"
            )

            data["__CALLBACKPARAM"] = (
                argument
            )

            headers = {
                **HEADERS,
                "X-Requested-With":
                    "XMLHttpRequest",
                "Referer": URL,
                "Content-Type":
                    "application/x-www-form-urlencoded",
            }

            response = session.post(
                URL,
                data=data,
                headers=headers,
                timeout=90,
            )

            response.raise_for_status()

            text = response.text

            print(
                "DEBUG: DevExpress callback "
                f"response size: {len(text):,}"
            )

            filename = (
                "debug_devexpress_callback_"
                + re.sub(
                    r"[^A-Za-z0-9_.-]",
                    "_",
                    argument,
                )
                + ".txt"
            )

            save_debug(
                filename,
                text,
            )

            if (
                "ddlMeDoOdrediste"
                in text
            ):

                return text

        except Exception as exc:

            print(
                "DEBUG: Callback failed:",
                exc,
            )

    # --------------------------------------------------------
    # Strategy 3:
    #
    # Normal POST preserving the complete original form.
    # --------------------------------------------------------

    print(
        "Trying normal form POST fallback..."
    )

    try:

        response = post_normal(
            session,
            html,
            {
                "__EVENTTARGET":
                    "ASPxTabControl1",
                "__EVENTARGUMENT":
                    "1",
            },
        )

        text = response.text

        print(
            "DEBUG: Normal POST response size: "
            f"{len(text):,} bytes"
        )

        save_debug(
            "debug_international_normal_post.html",
            text,
        )

        if (
            "ddlMeDoOdrediste"
            in text
        ):

            return text

    except Exception as exc:

        print(
            "DEBUG: Normal POST failed:",
            exc,
        )

    # --------------------------------------------------------
    # Final diagnostics.
    # --------------------------------------------------------

    print(
        "DEBUG: ddlMeDoOdrediste still not present."
    )

    print(
        "DEBUG: Original page size: "
        f"{len(html):,} bytes"
    )

    print(
        "DEBUG: Relevant DevExpress script "
        f"count: {len(scripts)}"
    )

    raise RuntimeError(
        "Could not activate Međunarodni promet. "
        "The server did not return "
        "ddlMeDoOdrediste for the discovered "
        "tab-postback/callback methods."
    )


# ============================================================
# DOPISNICA
# ============================================================

def activate_dopisnica(
    session,
    html,
):
    if "ddlMeDoOdrediste" not in html:

        raise RuntimeError(
            "Country selector is missing before "
            "Dopisnica."
        )

    print(
        "Selecting Dopisnica..."
    )

    if "Dopisnica_Aktivna.png" in html:

        print(
            "Dopisnica already selected."
        )

        return html

    response = post_normal(
        session,
        html,
        {
            "ImageButton8.x": "1",
            "ImageButton8.y": "1",
        },
    )

    response.raise_for_status()

    result = response.text

    if "Dopisnica_Aktivna.png" in result:

        print(
            "Dopisnica selected."
        )

    else:

        print(
            "WARNING: Dopisnica_Aktivna.png "
            "not found after selection."
        )

    return result


# ============================================================
# AIRMAIL
# ============================================================

def activate_airmail(
    session,
    html,
):
    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    checkbox = soup.find(
        "input",
        id="chbMeDoAvionski",
    )

    if not checkbox:

        raise RuntimeError(
            "Could not find chbMeDoAvionski."
        )

    if checkbox.has_attr(
        "checked"
    ):

        print(
            "Avionski prijenos already enabled."
        )

        return html

    print(
        "Enabling Avionski prijenos..."
    )

    # Keep original full document.
    original_html = html

    response = post_async(
        session,
        html,
        "chbMeDoAvionski",
        "",
        {
            "chbMeDoAvionski": "on",
        },
    )

    response_text = response.text

    # --------------------------------------------------------
    # AJAX response.
    # --------------------------------------------------------

    if "|updatePanel|" in response_text:

        html = merge_ajax_response(
            original_html,
            response_text,
        )

    else:

        html = response_text

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    checkbox = soup.find(
        "input",
        id="chbMeDoAvionski",
    )

    if not checkbox:

        raise RuntimeError(
            "chbMeDoAvionski disappeared "
            "after the postback."
        )

    if checkbox.has_attr(
        "checked"
    ):

        print(
            "Avionski prijenos enabled."
        )

    else:

        print(
            "WARNING: Avionski prijenos "
            "was returned without an explicit "
            "checked attribute."
        )

    return html


# ============================================================
# COUNTRY SELECTION
# ============================================================

def select_country(
    session,
    html,
    code,
):
    """
    Select destination.

    The destination dropdown itself normally causes an
    ASP.NET AJAX postback.
    """

    original_html = html

    response = post_async(
        session,
        html,
        "ddlMeDoOdrediste",
        "",
        {
            "ddlMeDoOdrediste": code,
        },
    )

    response_text = response.text

    if "|updatePanel|" in response_text:

        return merge_ajax_response(
            original_html,
            response_text,
        )

    return response_text


# ============================================================
# CALCULATE
# ============================================================

def calculate(
    session,
    html,
    code,
):
    response = post_normal(
        session,
        html,
        {
            "ddlMeDoOdrediste": code,
            "chbMeDoAvionski": "on",
            "tbxMeDoAvioTezina": WEIGHT,
            "btnMeDoIzracunaj":
                "Izračunaj",
        },
    )

    response.raise_for_status()

    return response.text


# ============================================================
# RESULT DETECTION
# ============================================================

def is_suspended(html):
    return (
        SUSPENDED_MESSAGE
        in unescape(html)
    )


def is_available(html):
    text = BeautifulSoup(
        unescape(html),
        "html.parser",
    ).get_text(
        " ",
        strip=True,
    )

    if "Ukupna cijena" in text:
        return True

    if re.search(
        r"\b\d+(?:[,.]\d+)?\s*KM\b",
        text,
    ):
        return True

    return False


# ============================================================
# MAIN
# ============================================================

def main():

    session = requests.Session()

    session.headers.update(
        HEADERS
    )

    print(
        "Opening calculator..."
    )

    response = session.get(
        URL,
        timeout=90,
    )

    response.raise_for_status()

    html = response.text

    print(
        f"Initial page received: "
        f"{len(html):,} bytes"
    )

    # --------------------------------------------------------
    # 1. International traffic
    # --------------------------------------------------------

    html = activate_international(
        session,
        html,
    )

    # --------------------------------------------------------
    # 2. Dopisnica
    # --------------------------------------------------------

    html = activate_dopisnica(
        session,
        html,
    )

    # --------------------------------------------------------
    # 3. Airmail
    # --------------------------------------------------------

    html = activate_airmail(
        session,
        html,
    )

    # --------------------------------------------------------
    # 4. Countries
    # --------------------------------------------------------

    countries = parse_countries(
        html
    )

    if not countries:

        save_debug(
            "debug_no_countries.html",
            html,
        )

        raise RuntimeError(
            "No countries found in "
            "ddlMeDoOdrediste."
        )

    print(
        f"Found {len(countries)} "
        "destination entries."
    )

    available = []
    suspended = []

    # --------------------------------------------------------
    # 5. Test every country
    # --------------------------------------------------------

    for index, (code, name) in enumerate(
        countries,
        start=1,
    ):

        print(
            f"[{index}/{len(countries)}] "
            f"{name} ({code})",
            flush=True,
        )

        try:

            selected_html = select_country(
                session,
                html,
                code,
            )

            result_html = calculate(
                session,
                selected_html,
                code,
            )

            if is_suspended(
                result_html
            ):

                print(
                    "    -> SUSPENDED",
                    flush=True,
                )

                suspended.append(
                    name
                )

            elif is_available(
                result_html
            ):

                print(
                    "    -> AVAILABLE",
                    flush=True,
                )

                available.append(
                    name
                )

            else:

                print(
                    "    -> UNKNOWN",
                    flush=True,
                )

        except Exception as exc:

            print(
                f"    -> ERROR: {exc}",
                flush=True,
            )

        time.sleep(0.5)

    # --------------------------------------------------------
    # 6. Write output
    # --------------------------------------------------------

    AVAILABLE_FILE.write_text(
        "\n".join(available) + "\n",
        encoding="utf-8",
    )

    SUSPENDED_FILE.write_text(
        "\n".join(suspended) + "\n",
        encoding="utf-8",
    )

    print()
    print(
        "Finished."
    )
    print()

    print(
        f"Available: {len(available)}"
    )

    print(
        f"Suspended: {len(suspended)}"
    )

    print()

    print(
        "Available countries written to: "
        f"{AVAILABLE_FILE}"
    )

    print(
        "Suspended countries written to: "
        f"{SUSPENDED_FILE}"
    )


if __name__ == "__main__":
    main()
