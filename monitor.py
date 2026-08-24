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
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "hr-HR,hr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Connection": "keep-alive",
}


# ============================================================
# General helpers
# ============================================================

def save_debug(filename, content):
    try:
        Path(filename).write_text(
            content,
            encoding="utf-8",
            errors="replace",
        )
    except Exception:
        pass


def soup(html):
    return BeautifulSoup(html, "html.parser")


def get_hidden_fields(html):
    """
    Return every ASP.NET hidden field.

    Important:
    ASP.NET pages can contain duplicate hidden inputs.
    The last value is normally the current value.
    """

    result = {}

    for element in soup(html).select("input[type='hidden']"):
        name = element.get("name")

        if not name:
            continue

        result[name] = element.get("value", "")

    return result


def get_form_fields(html):
    """
    Collect normal form fields as well as hidden fields.

    This is important for ASP.NET/DevExpress because the server
    can expect more than just __VIEWSTATE and __EVENTVALIDATION.
    """

    result = {}

    document = soup(html)

    form = document.find("form")

    if not form:
        return result

    for element in form.find_all(
        ["input", "select", "textarea", "button"]
    ):

        name = element.get("name")

        if not name:
            continue

        tag = element.name
        element_type = (
            element.get("type", "").lower()
            if tag == "input"
            else ""
        )

        # ----------------------------------------------------
        # Input
        # ----------------------------------------------------

        if tag == "input":

            if element_type in {
                "submit",
                "button",
                "reset",
                "file",
            }:
                continue

            if element_type in {
                "checkbox",
                "radio",
            }:
                if element.has_attr("checked"):
                    result[name] = element.get(
                        "value",
                        "on",
                    )
                continue

            result[name] = element.get(
                "value",
                "",
            )

        # ----------------------------------------------------
        # Select
        # ----------------------------------------------------

        elif tag == "select":

            selected = element.find(
                "option",
                selected=True,
            )

            if selected:
                result[name] = selected.get(
                    "value",
                    "",
                )

        # ----------------------------------------------------
        # Textarea
        # ----------------------------------------------------

        elif tag == "textarea":

            result[name] = element.get_text()

    return result


def has_country_selector(html):
    return (
        soup(html).find(
            "select",
            id="ddlMeDoOdrediste",
        )
        is not None
    )


# ============================================================
# ASP.NET AJAX parser
# ============================================================

def parse_ajax_delta(response_text):
    """
    Parse the ASP.NET PageRequestManager delta response.

    Format resembles:

        1|#||4|...|updatePanel|UpdatePanel1|....|hiddenField|...|

    Returns:

        {
            "update_panels": {...},
            "hidden_fields": {...},
        }

    The parser deliberately handles unknown record types instead
    of assuming every record has the same shape.
    """

    result = {
        "update_panels": {},
        "hidden_fields": {},
        "raw": response_text,
    }

    if not response_text:
        return result

    # Not an AJAX delta.
    if not response_text.startswith(("1|", "0|")):
        return result

    parts = response_text.split("|")

    i = 0

    while i < len(parts):

        record_type = parts[i]

        # ----------------------------------------------------
        # updatePanel
        # ----------------------------------------------------

        if record_type == "updatePanel":

            if i + 2 >= len(parts):
                break

            panel_id = parts[i + 1]
            content = parts[i + 2]

            result["update_panels"][panel_id] = content

            i += 3
            continue

        # ----------------------------------------------------
        # hiddenField
        # ----------------------------------------------------

        if record_type == "hiddenField":

            if i + 2 >= len(parts):
                break

            name = parts[i + 1]
            value = parts[i + 2]

            result["hidden_fields"][name] = value

            i += 3
            continue

        # ----------------------------------------------------
        # scriptBlock / scriptStartupBlock
        # ----------------------------------------------------

        if record_type in {
            "scriptBlock",
            "scriptStartupBlock",
        }:

            if i + 2 >= len(parts):
                break

            # These records have different internal layouts.
            # We only need to advance conservatively.
            i += 3
            continue

        # ----------------------------------------------------
        # arrayDeclaration
        # ----------------------------------------------------

        if record_type == "arrayDeclaration":

            i += 3
            continue

        # ----------------------------------------------------
        # expandPanel
        # ----------------------------------------------------

        if record_type == "expandPanel":

            i += 2
            continue

        # ----------------------------------------------------
        # pageRedirect
        # ----------------------------------------------------

        if record_type == "pageRedirect":

            i += 2
            continue

        # ----------------------------------------------------
        # property
        # ----------------------------------------------------

        if record_type == "property":

            i += 3
            continue

        # ----------------------------------------------------
        # unknown record
        # ----------------------------------------------------

        i += 1

    return result


def apply_ajax_delta(original_html, response_text):
    """
    Apply the useful portions of an ASP.NET AJAX response.

    Crucially, if the UpdatePanel does not contain the country
    selector, we do NOT throw away the original document.

    The ASP.NET AJAX response can contain only the changed panel.
    """

    parsed = parse_ajax_delta(response_text)

    html = original_html

    # Update hidden fields in the existing document.
    if parsed["hidden_fields"]:

        document = soup(html)

        for name, value in parsed["hidden_fields"].items():

            element = document.find(
                "input",
                {
                    "type": "hidden",
                    "name": name,
                },
            )

            if element:
                element["value"] = value

            else:
                form = document.find("form")

                if form:
                    new_input = document.new_tag(
                        "input",
                        type="hidden",
                        name=name,
                        value=value,
                    )

                    form.append(new_input)

        html = str(document)

    # Replace/update UpdatePanel content.
    for panel_id, content in parsed[
        "update_panels"
    ].items():

        document = soup(html)

        panel = document.find(
            id=panel_id
        )

        if not panel:
            continue

        replacement = soup(
            content
        )

        new_nodes = list(
            replacement.contents
        )

        panel.clear()

        for node in new_nodes:
            panel.append(node)

        html = str(document)

    return html


# ============================================================
# HTTP post helpers
# ============================================================

def post_async(
    session,
    html,
    event_target,
    extra=None,
):
    """
    ASP.NET AJAX asynchronous postback.
    """

    data = get_form_fields(html)

    data["__EVENTTARGET"] = event_target
    data["__EVENTARGUMENT"] = ""
    data["__ASYNCPOST"] = "true"

    if extra:
        data.update(extra)

    headers = {
        **HEADERS,
        "X-Requested-With": "XMLHttpRequest",
        "X-MicrosoftAjax": "Delta=true",
        "Referer": URL,
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

    return response.text


def post_normal(
    session,
    html,
    extra=None,
):
    """
    Normal ASP.NET form POST.

    Unlike the previous version, this includes the current
    non-hidden form state as well.
    """

    data = get_form_fields(html)

    if extra:
        data.update(extra)

    headers = {
        **HEADERS,
        "Referer": URL,
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

    return response.text


# ============================================================
# Tab discovery
# ============================================================

def inspect_tab_control(html):
    document = soup(html)

    tab = document.find(
        id="ASPxTabControl1"
    )

    if not tab:
        return None

    print(
        "DEBUG: ASPxTabControl1 found."
    )

    print(
        "DEBUG: Tab attributes:",
        dict(tab.attrs),
    )

    scripts = []

    for script in document.find_all("script"):

        text = script.get_text(
            "",
            strip=False,
        )

        if (
            "ASPxTabControl1" in text
            or "ASPxClientTabControl" in text
        ):
            scripts.append(text)

    print(
        f"DEBUG: Found {len(scripts)} "
        "tab-related script block(s)."
    )

    for index, script in enumerate(
        scripts,
        start=1,
    ):

        save_debug(
            f"debug_tab_script_{index}.txt",
            script,
        )

        preview = re.sub(
            r"\s+",
            " ",
            script,
        )

        print(
            "DEBUG SCRIPT:",
            preview[:1500],
        )

    return {
        "tab": tab,
        "scripts": scripts,
    }


def extract_tab_candidates(html):
    """
    Extract useful clues from the generated DevExpress script.

    For the page currently served by BH Pošta the script has
    two tabs, with the second tab being the international tab.

    We still inspect the script rather than hard-coding only one
    callback syntax.
    """

    info = inspect_tab_control(html)

    candidates = []

    if not info:
        return candidates

    for script in info["scripts"]:

        # Number of tab definitions.
        match = re.search(
            r"'tabs'\s*:\s*\[\[(.*?)\]\]",
            script,
            re.S,
        )

        if match:
            body = match.group(1)

            # Usually the second tab is index 1.
            candidates.append("1")

        if (
            "autoPostBack:true"
            in script.replace(" ", "")
            or "autoPostBack':true"
            in script.replace(" ", "")
        ):
            candidates.append("1")

    # Always retain the known second-tab index.
    candidates.extend(
        [
            "1",
            "1|",
            "0|1",
            "C1",
        ]
    )

    # Deduplicate.
    result = []

    for value in candidates:

        if value not in result:
            result.append(value)

    return result


# ============================================================
# International tab activation
# ============================================================

def activate_international(
    session,
    html,
):
    """
    Activate Međunarodni promet.

    The key change from the previous versions is that we no
    longer assume that an AJAX UpdatePanel response itself is
    the complete page.

    We preserve the original ASP.NET form and apply the delta
    only when appropriate.

    Several server-side postback variants are attempted.
    """

    if has_country_selector(html):
        print(
            "Međunarodni promet already active."
        )
        return html

    print(
        "Activating Međunarodni promet..."
    )

    save_debug(
        "debug_original_page.html",
        html,
    )

    # --------------------------------------------------------
    # Candidate 1:
    # Standard ASP.NET __doPostBack
    # --------------------------------------------------------

    candidates = [
        (
            "ASP.NET event target",
            "__doPostBack",
            {
                "__EVENTTARGET":
                    "ASPxTabControl1",
                "__EVENTARGUMENT":
                    "1",
            },
        ),
        (
            "ASP.NET child target",
            "__doPostBack-child",
            {
                "__EVENTTARGET":
                    "ASPxTabControl1$1",
                "__EVENTARGUMENT":
                    "",
            },
        ),
    ]

    for label, event_name, values in candidates:

        print(
            f"Trying {label}..."
        )

        try:

            request_html = post_async(
                session,
                html,
                values["__EVENTTARGET"],
                {
                    "__EVENTARGUMENT":
                        values["__EVENTARGUMENT"],
                },
            )

            print(
                f"DEBUG: {label} response size: "
                f"{len(request_html):,} bytes"
            )

            save_debug(
                "debug_international_"
                + event_name
                + ".txt",
                request_html,
            )

            if has_country_selector(
                request_html
            ):
                print(
                    "SUCCESS: Country selector "
                    "returned directly."
                )

                return request_html

            parsed = parse_ajax_delta(
                request_html
            )

            print(
                "DEBUG: UpdatePanel count:",
                len(
                    parsed["update_panels"]
                ),
            )

            print(
                "DEBUG: Hidden field count:",
                len(
                    parsed["hidden_fields"]
                ),
            )

            combined = apply_ajax_delta(
                html,
                request_html,
            )

            if has_country_selector(
                combined
            ):
                print(
                    "SUCCESS: Country selector "
                    "appeared after applying AJAX delta."
                )

                return combined

        except Exception as exc:

            print(
                f"DEBUG: {label} failed: {exc}"
            )

    # --------------------------------------------------------
    # Candidate 2:
    # DevExpress-generated tab arguments
    # --------------------------------------------------------

    print(
        "Inspecting DevExpress tab control..."
    )

    tab_candidates = extract_tab_candidates(
        html
    )

    for argument in tab_candidates:

        print(
            f"Trying DevExpress tab "
            f"argument={argument!r}..."
        )

        try:

            # DevExpress controls commonly receive their
            # callback state through __CALLBACKID/__CALLBACKPARAM.
            #
            # This is attempted separately from ASP.NET AJAX.
            data = get_form_fields(html)

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
                "X-DevExpress-AjaxRequest":
                    "true",
                "Referer": URL,
                "Content-Type":
                    "application/x-www-form-urlencoded; "
                    "charset=UTF-8",
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
                "DEBUG: DevExpress response "
                f"size: {len(text):,} bytes"
            )

            save_debug(
                "debug_devexpress_tab_"
                + re.sub(
                    r"[^A-Za-z0-9_-]",
                    "_",
                    argument,
                )
                + ".txt",
                text,
            )

            if has_country_selector(
                text
            ):
                return text

        except Exception as exc:

            print(
                "DEBUG: DevExpress attempt failed:",
                exc,
            )

    # --------------------------------------------------------
    # Candidate 3:
    # Normal form POST with all current fields.
    #
    # We try the tab as a submitted control as well.
    # --------------------------------------------------------

    print(
        "Trying normal ASP.NET form post..."
    )

    normal_variants = [
        {
            "ASPxTabControl1":
                "Međunarodni promet",
        },
        {
            "ASPxTabControl1$1":
                "Međunarodni promet",
        },
        {
            "__EVENTTARGET":
                "ASPxTabControl1",
            "__EVENTARGUMENT":
                "1",
        },
    ]

    for index, extra in enumerate(
        normal_variants,
        start=1,
    ):

        try:

            result = post_normal(
                session,
                html,
                extra,
            )

            print(
                f"DEBUG: Normal POST "
                f"variant {index} size: "
                f"{len(result):,} bytes"
            )

            save_debug(
                f"debug_international_normal_"
                f"{index}.html",
                result,
            )

            if has_country_selector(
                result
            ):
                print(
                    "SUCCESS: International tab "
                    "activated by normal POST."
                )

                return result

        except Exception as exc:

            print(
                f"DEBUG: Normal POST "
                f"variant {index} failed: "
                f"{exc}"
            )

    # --------------------------------------------------------
    # Last possibility:
    #
    # The public page exposes the international controls in
    # the rendered DOM, but the initial HTTP response can omit
    # them because DevExpress dynamically creates the tab.
    #
    # In that situation we stop rather than pretending that a
    # successful response was obtained.
    # --------------------------------------------------------

    print(
        "DEBUG: International activation "
        "did not produce ddlMeDoOdrediste."
    )

    print(
        "DEBUG: Original page size:",
        len(html),
    )

    raise RuntimeError(
        "Could not activate Međunarodni promet. "
        "The server did not return "
        "ddlMeDoOdrediste after the available "
        "ASP.NET/DevExpress postback methods."
    )


# ============================================================
# Country parsing
# ============================================================

def parse_countries(html):

    document = soup(html)

    select = document.find(
        "select",
        id="ddlMeDoOdrediste",
    )

    if not select:
        return []

    result = []

    for option in select.find_all(
        "option"
    ):

        value = option.get("value")
        name = option.get_text(
            strip=True
        )

        if value and name:
            result.append(
                (value, name)
            )

    return result


# ============================================================
# Dopisnica
# ============================================================

def activate_dopisnica(
    session,
    html,
):

    if not has_country_selector(
        html
    ):
        raise RuntimeError(
            "Country selector is missing "
            "before Dopisnica."
        )

    print(
        "Activating Dopisnica..."
    )

    if "Dopisnica_Aktivna.png" in html:
        print(
            "Dopisnica already active."
        )
        return html

    # --------------------------------------------------------
    # Try normal ImageButton POST first.
    # --------------------------------------------------------

    try:

        result = post_normal(
            session,
            html,
            {
                "ImageButton8.x": "1",
                "ImageButton8.y": "1",
            },
        )

        if "Dopisnica_Aktivna.png" in result:
            print(
                "Dopisnica activated."
            )
            return result

        # Some ASP.NET pages preserve the selected state
        # through the response even if the image itself isn't
        # repeated.
        return result

    except Exception as exc:

        print(
            "Dopisnica POST failed:",
            exc,
        )

        raise


# ============================================================
# Airmail
# ============================================================

def activate_airmail(
    session,
    html,
):

    document = soup(html)

    checkbox = document.find(
        "input",
        id="chbMeDoAvionski",
    )

    if not checkbox:
        raise RuntimeError(
            "Could not find chbMeDoAvionski."
        )

    checked = (
        checkbox.has_attr("checked")
        or checkbox.get(
            "value"
        ) == "true"
    )

    if checked:
        print(
            "Avionski prijenos already enabled."
        )
        return html

    print(
        "Enabling Avionski prijenos..."
    )

    result = post_async(
        session,
        html,
        "chbMeDoAvionski",
        {
            "chbMeDoAvionski": "on",
        },
    )

    if "chbMeDoAvionski" not in result:
        raise RuntimeError(
            "Airmail postback returned an "
            "unexpected page."
        )

    return result


# ============================================================
# Country selection
# ============================================================

def select_country(
    session,
    html,
    code,
):

    data = {
        "ddlMeDoOdrediste": code,
    }

    return post_async(
        session,
        html,
        "ddlMeDoOdrediste",
        data,
    )


# ============================================================
# Calculation
# ============================================================

def calculate(
    session,
    html,
    code,
):

    data = {
        "ddlMeDoOdrediste": code,
        "chbMeDoAvionski": "on",
        "tbxMeDoAvioTezina": WEIGHT,
        "btnMeDoIzracunaj": "Izračunaj",
    }

    return post_normal(
        session,
        html,
        data,
    )


# ============================================================
# Result detection
# ============================================================

def is_suspended(html):

    return (
        SUSPENDED_MESSAGE
        in unescape(html)
    )


def is_available(html):

    text = soup(
        unescape(html)
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
# Main
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

    save_debug(
        "debug_original_page.html",
        html,
    )

    # --------------------------------------------------------
    # 1. Međunarodni promet
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
    # 3. Avionski prijenos
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
    # 5. Test every destination
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

            # Select destination.
            html = select_country(
                session,
                html,
                code,
            )

            # Calculate 10 g.
            html = calculate(
                session,
                html,
                code,
            )

            if is_suspended(
                html
            ):

                print(
                    "    -> SUSPENDED",
                    flush=True,
                )

                suspended.append(
                    name
                )

            elif is_available(
                html
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

                save_debug(
                    "debug_unknown_"
                    + re.sub(
                        r"[^A-Za-z0-9_-]",
                        "_",
                        code,
                    )
                    + ".html",
                    html,
                )

        except Exception as exc:

            print(
                f"    -> ERROR: {exc}",
                flush=True,
            )

        time.sleep(0.5)

    # --------------------------------------------------------
    # 6. Write results
    # --------------------------------------------------------

    AVAILABLE_FILE.write_text(
        "\n".join(available)
        + ("\n" if available else ""),
        encoding="utf-8",
    )

    SUSPENDED_FILE.write_text(
        "\n".join(suspended)
        + ("\n" if suspended else ""),
        encoding="utf-8",
    )

    print()
    print(
        "Finished."
    )
    print()

    print(
        f"Available countries written to: "
        f"{AVAILABLE_FILE}"
    )

    print(
        f"Suspended countries written to: "
        f"{SUSPENDED_FILE}"
    )

    print()
    print(
        f"Available: {len(available)}"
    )

    print(
        f"Suspended: {len(suspended)}"
    )


if __name__ == "__main__":
    main()
