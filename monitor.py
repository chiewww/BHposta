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


# ============================================================
# Basic helpers
# ============================================================

def save_debug(filename, content):
    try:
        Path(filename).write_text(
            content,
            encoding="utf-8",
            errors="ignore",
        )
        print(f"DEBUG: Saved {filename}")
    except Exception as exc:
        print(f"DEBUG: Could not save {filename}: {exc}")


def get_hidden_fields(html):
    soup = BeautifulSoup(html, "html.parser")

    data = {}

    for element in soup.select("input[type='hidden']"):
        name = element.get("name")

        if name:
            data[name] = element.get("value", "")

    return data


def parse_countries(html):
    soup = BeautifulSoup(html, "html.parser")

    select = soup.find(
        "select",
        id="ddlMeDoOdrediste",
    )

    if not select:
        return []

    result = []

    for option in select.find_all("option"):
        value = option.get("value")
        name = option.get_text(strip=True)

        if value and name:
            result.append((value, name))

    return result


def has_country_selector(html):
    return "ddlMeDoOdrediste" in html


def get_text(html):
    return BeautifulSoup(
        unescape(html),
        "html.parser",
    ).get_text(
        " ",
        strip=True,
    )


# ============================================================
# ASP.NET AJAX parser
# ============================================================

def parse_aspnet_ajax_response(response_text):
    """
    Parse an ASP.NET AJAX PageRequestManager delta response.

    Example:

        1|#||4|6967|updatePanel|UpdatePanel1|<html>...
        6|hiddenField|__VIEWSTATE|...
        ...

    Returns:

        {
            "panels": {...},
            "hidden": {...},
            "raw": response_text,
        }
    """

    result = {
        "panels": {},
        "hidden": {},
        "raw": response_text,
    }

    if not response_text:
        return result

    if "|updatePanel|" not in response_text and "|hiddenField|" not in response_text:
        return result

    pos = 0
    length = len(response_text)

    while pos < length:

        # Find next record type.
        match = re.search(
            r"(?:(?<=^)|(?<=\|))(\d+)\|([^|]*)\|",
            response_text[pos:],
        )

        if not match:
            break

        start = pos + match.start()
        record_start = pos + match.end()

        try:
            record_length = int(match.group(1))
        except ValueError:
            pos = record_start
            continue

        record_type = match.group(2)

        value_start = record_start
        value_end = value_start + record_length

        if value_end > length:
            break

        value = response_text[value_start:value_end]

        if record_type == "updatePanel":

            # updatePanel records have:
            #
            # updatePanel|panelID|content
            #
            # but depending on the parser state, panel ID may
            # appear in the record value.

            if "|" in value:
                panel_id, content = value.split(
                    "|",
                    1,
                )
                result["panels"][panel_id] = content

        elif record_type == "hiddenField":

            if "|" in value:
                name, field_value = value.split(
                    "|",
                    1,
                )
                result["hidden"][name] = field_value

        pos = value_end

    return result


def apply_ajax_response(old_html, response_text):
    """
    Apply ASP.NET AJAX changes to our local HTML representation.

    Hidden fields returned by the server are merged into the old
    document.

    UpdatePanel content is replaced where possible.

    If the returned panel does not contain the requested control,
    the old document is retained for that part.
    """

    parsed = parse_aspnet_ajax_response(
        response_text
    )

    print(
        "DEBUG: ASP.NET AJAX parser found "
        f"{sum(len(x) for x in parsed['panels'].values()):,} "
        "bytes of UpdatePanel content."
    )

    if parsed["hidden"]:
        print(
            f"DEBUG: Returned hidden fields: "
            f"{len(parsed['hidden'])}"
        )

    # --------------------------------------------------------
    # No useful AJAX response
    # --------------------------------------------------------

    if not parsed["panels"] and not parsed["hidden"]:

        print(
            "DEBUG: AJAX response contained no usable "
            "UpdatePanel/hidden-field records."
        )

        return old_html

    soup = BeautifulSoup(
        old_html,
        "html.parser",
    )

    # --------------------------------------------------------
    # Replace/update hidden fields
    # --------------------------------------------------------

    for name, value in parsed["hidden"].items():

        element = soup.find(
            "input",
            {
                "type": "hidden",
                "name": name,
            },
        )

        if element:
            element["value"] = value

        else:
            new_element = soup.new_tag(
                "input",
                type="hidden",
            )

            new_element["name"] = name
            new_element["value"] = value

            form = soup.find("form")

            if form:
                form.append(new_element)

    # --------------------------------------------------------
    # Update panels
    # --------------------------------------------------------

    for panel_id, content in parsed["panels"].items():

        panel = soup.find(
            id=panel_id,
        )

        if not panel:
            continue

        replacement = BeautifulSoup(
            content,
            "html.parser",
        )

        panel.clear()

        for child in replacement.contents:
            panel.append(child)

    return str(soup)


# ============================================================
# ASP.NET POST helpers
# ============================================================

def post_async(
    session,
    html,
    event_target,
    extra=None,
    event_argument="",
):
    """
    ASP.NET UpdatePanel asynchronous postback.
    """

    data = get_hidden_fields(html)

    data["__EVENTTARGET"] = event_target
    data["__EVENTARGUMENT"] = event_argument
    data["__ASYNCPOST"] = "true"

    if extra:
        data.update(extra)

    headers = {
        **HEADERS,
        "X-Requested-With": "XMLHttpRequest",
        "X-MicrosoftAjax": "Delta=true",
        "Content-Type": (
            "application/x-www-form-urlencoded; "
            "charset=UTF-8"
        ),
        "Referer": URL,
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
    extra,
):
    """
    Normal ASP.NET form POST.
    """

    data = get_hidden_fields(html)

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

    return response.text


# ============================================================
# DevExpress inspection
# ============================================================

def inspect_devexpress_tabs(html):
    """
    Print useful information about the DevExpress tab control.

    This is intentionally diagnostic because the server response
    shows that the tab is not behaving like a normal ASP.NET
    Button.
    """

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    print()
    print("DEBUG: Inspecting DevExpress tab control...")

    candidates = []

    for element in soup.find_all(
        lambda tag: (
            tag.name in ("div", "table", "span", "input")
            and (
                "ASPxTabControl1" in str(tag.get("id", ""))
                or "ASPxTabControl1" in str(tag.get("name", ""))
                or "ASPxTabControl1" in str(tag.get("class", ""))
            )
        )
    ):
        candidates.append(element)

    print(
        f"DEBUG: Found {len(candidates)} elements related "
        "to ASPxTabControl1."
    )

    for element in candidates[:20]:

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

    # Look for ASPx hidden state fields.
    for element in soup.find_all("input"):

        name = element.get("name", "")
        element_id = element.get("id", "")

        if (
            "ASPxTab" in name
            or "ASPxTab" in element_id
            or "DX" in name
            or "DX" in element_id
        ):
            print(
                "DEBUG DEVEXPRESS INPUT:",
                name or element_id,
                "=",
                element.get("value", ""),
            )

    print()


# ============================================================
# International tab activation
# ============================================================

def activate_international(
    session,
    html,
):
    """
    Activate Međunarodni promet.

    Important:
    The previous implementation assumed that the UpdatePanel
    response itself must contain ddlMeDoOdrediste.

    That assumption is false for this page.

    The server is returning UpdatePanel1, but the international
    controls are apparently not represented by that panel in
    the callback response.

    We therefore try several ways of activating the tab and
    preserve useful diagnostic information instead of blindly
    replacing the whole document with the AJAX response.
    """

    print(
        "Activating Međunarodni promet..."
    )

    if has_country_selector(html):

        print(
            "International destination selector is already "
            "present."
        )

        return html

    inspect_devexpress_tabs(html)

    original_html = html

    # --------------------------------------------------------
    # Attempt 1:
    # ASP.NET async postback using ASPxTabControl1
    # --------------------------------------------------------

    attempts = [
        (
            "ASPxTabControl1 argument=1",
            "ASPxTabControl1",
            "1",
        ),
        (
            "ASPxTabControl1 argument=1|",
            "ASPxTabControl1",
            "1|",
        ),
        (
            "ASPxTabControl1 argument=0|1",
            "ASPxTabControl1",
            "0|1",
        ),
    ]

    for description, target, argument in attempts:

        print(
            f"Trying {description}..."
        )

        try:

            response_text = post_async(
                session,
                html,
                target,
                event_argument=argument,
            )

            print(
                f"DEBUG: {description} response size: "
                f"{len(response_text):,} bytes"
            )

            save_debug(
                "debug_international_"
                + re.sub(
                    r"[^a-zA-Z0-9]+",
                    "_",
                    description,
                )
                + ".txt",
                response_text,
            )

            # ------------------------------------------------
            # The crucial change:
            #
            # Do NOT replace the entire page with the AJAX
            # response.
            # ------------------------------------------------

            candidate = apply_ajax_response(
                html,
                response_text,
            )

            if has_country_selector(candidate):

                print(
                    "International destination selector "
                    "appeared after AJAX response."
                )

                return candidate

            # Keep the candidate only if it contains more
            # useful page state than the original.
            html = candidate

        except Exception as exc:

            print(
                f"WARNING: {description} failed: {exc}"
            )

    # --------------------------------------------------------
    # Attempt 2:
    # Browser-style ASP.NET postback fields
    # --------------------------------------------------------

    print(
        "Trying ASP.NET tab fallback..."
    )

    tab_fields = [
        {
            "__EVENTTARGET": "ASPxTabControl1",
            "__EVENTARGUMENT": "1",
        },
        {
            "__EVENTTARGET": "ASPxTabControl1",
            "__EVENTARGUMENT": "1|",
        },
        {
            "__EVENTTARGET": "ASPxTabControl1",
            "__EVENTARGUMENT": "0|1",
        },
    ]

    for extra in tab_fields:

        try:

            data = get_hidden_fields(
                original_html
            )

            data.update(extra)

            headers = {
                **HEADERS,
                "X-Requested-With": "XMLHttpRequest",
                "X-MicrosoftAjax": "Delta=true",
                "Referer": URL,
            }

            response = session.post(
                URL,
                data=data,
                headers=headers,
                timeout=90,
            )

            response.raise_for_status()

            response_text = response.text

            print(
                "DEBUG: ASP.NET tab fallback response "
                f"size: {len(response_text):,} bytes"
            )

            candidate = apply_ajax_response(
                original_html,
                response_text,
            )

            if has_country_selector(candidate):

                print(
                    "International selector found after "
                    "ASP.NET fallback."
                )

                return candidate

        except Exception as exc:

            print(
                f"WARNING: ASP.NET fallback failed: {exc}"
            )

    # --------------------------------------------------------
    # Attempt 3:
    # Normal POST with tab state
    # --------------------------------------------------------

    print(
        "Trying normal form POST fallback..."
    )

    try:

        data = get_hidden_fields(
            original_html
        )

        data["__EVENTTARGET"] = (
            "ASPxTabControl1"
        )
        data["__EVENTARGUMENT"] = "1"

        response = session.post(
            URL,
            data=data,
            headers={
                **HEADERS,
                "Referer": URL,
            },
            timeout=90,
        )

        response.raise_for_status()

        candidate = response.text

        print(
            "DEBUG: Normal POST response size: "
            f"{len(candidate):,} bytes"
        )

        save_debug(
            "debug_international_normal_post.html",
            candidate,
        )

        if has_country_selector(candidate):

            print(
                "International selector found after "
                "normal POST."
            )

            return candidate

    except Exception as exc:

        print(
            f"Normal POST fallback failed: {exc}"
        )

    # --------------------------------------------------------
    # Final diagnostic
    # --------------------------------------------------------

    print(
        "DEBUG: ddlMeDoOdrediste still not present."
    )

    print(
        f"DEBUG: Original page size: "
        f"{len(original_html):,} bytes"
    )

    save_debug(
        "debug_original_page.html",
        original_html,
    )

    raise RuntimeError(
        "Could not activate Međunarodni promet. "
        "The server accepts the AJAX request but does not "
        "return ddlMeDoOdrediste. "
        "See debug_original_page.html and "
        "debug_international_*.txt."
    )


# ============================================================
# Dopisnica
# ============================================================

def activate_dopisnica(
    session,
    html,
):
    """
    Select Dopisnica.
    """

    if not has_country_selector(html):

        raise RuntimeError(
            "Country selector is missing before Dopisnica."
        )

    print(
        "Dopisnica selected."
    )

    if "Dopisnica_Aktivna.png" in html:

        print(
            "Dopisnica already active."
        )

        return html

    html = post_normal(
        session,
        html,
        {
            "ImageButton8.x": "1",
            "ImageButton8.y": "1",
        },
    )

    if "Dopisnica_Aktivna.png" not in html:

        print(
            "WARNING: Dopisnica_Aktivna.png was not "
            "found after clicking ImageButton8."
        )

    return html


# ============================================================
# Airmail
# ============================================================

def activate_airmail(
    session,
    html,
):
    """
    Enable chbMeDoAvionski.
    """

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

    if checkbox.has_attr("checked"):

        print(
            "Avionski prijenos already enabled."
        )

        return html

    print(
        "Enabling Avionski prijenos..."
    )

    html = post_async(
        session,
        html,
        "chbMeDoAvionski",
        {
            "chbMeDoAvionski": "on",
        },
    )

    # AJAX responses must be merged with the previous page.
    merged = apply_ajax_response(
        html,
        html,
    )

    soup = BeautifulSoup(
        merged,
        "html.parser",
    )

    checkbox = soup.find(
        "input",
        id="chbMeDoAvionski",
    )

    if not checkbox:

        raise RuntimeError(
            "chbMeDoAvionski disappeared after "
            "the AJAX postback."
        )

    if not checkbox.has_attr("checked"):

        print(
            "WARNING: Server did not mark "
            "chbMeDoAvionski checked."
        )

    return merged


# ============================================================
# Country selection
# ============================================================

def select_country(
    session,
    html,
    code,
):
    """
    Reproduce:

        ddlMeDoOdrediste
        onchange -> __doPostBack(...)
    """

    response_text = post_async(
        session,
        html,
        "ddlMeDoOdrediste",
        {
            "ddlMeDoOdrediste": code,
        },
    )

    candidate = apply_ajax_response(
        html,
        response_text,
    )

    # If the response was a normal HTML document instead of
    # an AJAX delta, use it directly.
    if "<html" in response_text.lower():

        candidate = response_text

    return candidate


# ============================================================
# Calculate
# ============================================================

def calculate(
    session,
    html,
    code,
):
    """
    Calculate 10 g airmail postcard price/status.
    """

    return post_normal(
        session,
        html,
        {
            "ddlMeDoOdrediste": code,
            "chbMeDoAvionski": "on",
            "tbxMeDoAvioTezina": WEIGHT,
            "btnMeDoIzracunaj": "Izračunaj",
        },
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
    # 4. Read country list
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
            "No countries found in ddlMeDoOdrediste."
        )

    print(
        f"Found {len(countries)} destination entries."
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
            selected_html = select_country(
                session,
                html,
                code,
            )

            # Calculate.
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
    # 6. Write lists
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
