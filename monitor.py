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
UNKNOWN_FILE = Path("unknown_countries.txt")

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
        "application/xml;q=0.9,image/avif,"
        "image/webp,*/*;q=0.8"
    ),
    "Accept-Language": (
        "bs-BA,bs;q=0.9,en-US;q=0.8,en;q=0.7"
    ),
    "Connection": "keep-alive",
}


# ============================================================
# ASP.NET hidden fields
# ============================================================

def get_hidden_fields(html):
    """
    Extract all hidden ASP.NET fields from a normal HTML page
    or an HTML fragment.
    """

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

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


# ============================================================
# Country parsing
# ============================================================

def parse_countries(html):
    """
    Read destination countries from:

        ddlMeDoOdrediste
    """

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

    result = []

    for option in select.find_all("option"):

        value = option.get("value")
        name = option.get_text(
            " ",
            strip=True,
        )

        if value and name:
            result.append(
                (value, name)
            )

    return result


# ============================================================
# ASP.NET AJAX delta parser
# ============================================================

def parse_aspnet_ajax_delta(response_text):
    """
    Parse an ASP.NET AJAX UpdatePanel response.

    Typical response:

        1|#||4|6967|updatePanel|UpdatePanel1|
        <6967 chars of HTML>
        |hiddenField|__VIEWSTATE|...
        |...

    The important detail is that the record length appears
    BEFORE the record type:

        |6967|updatePanel|UpdatePanel1|<content>

    This function extracts:

        1. UpdatePanel HTML
        2. hiddenField values

    and returns:

        {
            "html": "...",
            "hidden_fields": {...},
            "is_delta": True
        }
    """

    text = response_text or ""

    if not text:
        return {
            "html": "",
            "hidden_fields": {},
            "is_delta": False,
        }

    # Normal HTML response.
    if (
        "<html" in text.lower()
        or "<form" in text.lower()
    ):
        return {
            "html": text,
            "hidden_fields": get_hidden_fields(
                text
            ),
            "is_delta": False,
        }

    # ASP.NET AJAX responses normally begin with:
    #
    #   version|#||...
    #
    if "|#|" not in text:
        return {
            "html": text,
            "hidden_fields": {},
            "is_delta": False,
        }

    update_panels = []
    hidden_fields = {}

    # --------------------------------------------------------
    # Parse records sequentially.
    #
    # A record has the form:
    #
    #   <length>|<type>|<id>|<content>
    #
    # Content may contain pipes, so we MUST use the length
    # rather than split("|") for the content.
    # --------------------------------------------------------

    pos = 0

    while pos < len(text):

        # Find the next numeric record length.
        match = re.search(
            r"(\d+)\|",
            text[pos:],
        )

        if not match:
            break

        length_start = (
            pos + match.start()
        )

        length_end = (
            pos + match.end()
        )

        try:
            content_length = int(
                match.group(1)
            )
        except ValueError:
            pos = length_end
            continue

        record_start = length_end

        # Find record type.
        type_end = text.find(
            "|",
            record_start,
        )

        if type_end < 0:
            break

        record_type = text[
            record_start:type_end
        ]

        # Find record ID.
        id_start = type_end + 1

        id_end = text.find(
            "|",
            id_start,
        )

        if id_end < 0:
            break

        record_id = text[
            id_start:id_end
        ]

        content_start = id_end + 1

        content_end = (
            content_start
            + content_length
        )

        if content_end > len(text):
            # Response is malformed/truncated.
            break

        content = text[
            content_start:content_end
        ]

        # ----------------------------------------------------
        # UpdatePanel
        # ----------------------------------------------------

        if record_type == "updatePanel":

            update_panels.append(
                (
                    record_id,
                    content,
                )
            )

        # ----------------------------------------------------
        # Hidden field
        # ----------------------------------------------------

        elif record_type == "hiddenField":

            hidden_fields[
                record_id
            ] = content

        # ----------------------------------------------------
        # Other ASP.NET AJAX record types are ignored.
        # ----------------------------------------------------

        pos = content_end

    # --------------------------------------------------------
    # Combine UpdatePanel HTML.
    # --------------------------------------------------------

    combined_html = "\n".join(
        content
        for _, content in update_panels
    )

    return {
        "html": combined_html,
        "hidden_fields": hidden_fields,
        "is_delta": True,
    }


def apply_aspnet_ajax_response(
    current_html,
    response_text,
):
    """
    Apply an ASP.NET AJAX response to the current page.

    If the server returned a normal HTML page, use that.

    If it returned an UpdatePanel delta:

      - extract UpdatePanel HTML
      - extract hidden fields
      - combine them into a usable HTML document

    We intentionally preserve the old hidden fields when a
    callback does not return every hidden field.
    """

    parsed = parse_aspnet_ajax_delta(
        response_text
    )

    if not parsed["is_delta"]:

        return response_text

    update_html = parsed["html"]
    returned_hidden = parsed[
        "hidden_fields"
    ]

    if not update_html:

        print(
            "WARNING: AJAX response contained "
            "no UpdatePanel HTML."
        )

        return current_html

    # --------------------------------------------------------
    # Extract hidden fields from UpdatePanel content too.
    # --------------------------------------------------------

    panel_hidden = get_hidden_fields(
        update_html
    )

    all_hidden = {}

    # Current page state first.
    all_hidden.update(
        get_hidden_fields(
            current_html
        )
    )

    # Then fields returned by the AJAX response.
    all_hidden.update(
        returned_hidden
    )

    # Finally fields physically present in the
    # UpdatePanel HTML.
    all_hidden.update(
        panel_hidden
    )

    # --------------------------------------------------------
    # If the UpdatePanel itself contains the form controls,
    # make a synthetic usable HTML document.
    # --------------------------------------------------------

    hidden_html = []

    for name, value in all_hidden.items():

        hidden_html.append(
            '<input type="hidden" '
            f'name="{escape_html(name)}" '
            f'id="{escape_html(name)}" '
            f'value="{escape_html(value)}">'
        )

    return (
        "<html>"
        "<body>"
        '<form id="aspnetForm">'
        + "".join(hidden_html)
        + update_html
        + "</form>"
        "</body>"
        "</html>"
    )


def escape_html(value):
    """
    Minimal HTML escaping for synthetic hidden inputs.
    """

    value = str(value)

    return (
        value
        .replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# ============================================================
# Diagnostics
# ============================================================

def debug_response(
    response_text,
    label,
):
    print(
        f"DEBUG: {label} response size: "
        f"{len(response_text):,} bytes"
    )

    preview = re.sub(
        r"\s+",
        " ",
        response_text[:500],
    )

    print(
        f"DEBUG: {label} preview: "
        f"{preview}"
    )


# ============================================================
# Normal ASP.NET POST
# ============================================================

def post_normal(
    session,
    html,
    extra,
):
    """
    Normal ASP.NET form POST.
    """

    data = get_hidden_fields(
        html
    )

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
# ASP.NET AJAX POST
# ============================================================

def post_async(
    session,
    html,
    event_target,
    extra=None,
):
    """
    ASP.NET UpdatePanel asynchronous postback.

    Returns the parsed HTML state rather than the raw
    ASP.NET AJAX delta.
    """

    data = get_hidden_fields(
        html
    )

    data["__EVENTTARGET"] = (
        event_target
    )

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

    return apply_aspnet_ajax_response(
        html,
        response.text,
    )


# ============================================================
# International tab
# ============================================================

def activate_international(
    session,
    html,
):
    """
    Activate Međunarodni promet.

    The working mechanism observed from the server is the
    ASP.NET AJAX UpdatePanel callback.

    IMPORTANT:

    The server response is NOT a normal HTML page. It starts
    approximately like:

        1|#||4|6967|updatePanel|UpdatePanel1|...

    Therefore the response must be parsed as an ASP.NET AJAX
    delta before looking for ddlMeDoOdrediste.
    """

    print(
        "Activating Međunarodni promet..."
    )

    # --------------------------------------------------------
    # Already active?
    # --------------------------------------------------------

    if (
        "ddlMeDoOdrediste"
        in html
    ):

        print(
            "International destination "
            "selector is already present."
        )

        return html

    # --------------------------------------------------------
    # Use the ASP.NET event-target callback.
    #
    # This is the request that returned:
    #
    #   1|#||4|6967|updatePanel|UpdatePanel1|...
    #
    # in your log.
    # --------------------------------------------------------

    print(
        "Sending ASP.NET asynchronous "
        "tab postback..."
    )

    data = get_hidden_fields(
        html
    )

    data["__EVENTTARGET"] = (
        "ASPxTabControl1"
    )

    data["__EVENTARGUMENT"] = "1"

    data["__ASYNCPOST"] = "true"

    headers = {
        **HEADERS,
        "X-Requested-With": "XMLHttpRequest",
        "X-MicrosoftAjax": "Delta=true",
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

    response_text = response.text

    debug_response(
        response_text,
        "international-tab AJAX",
    )

    # --------------------------------------------------------
    # Parse the actual UpdatePanel response.
    # --------------------------------------------------------

    parsed = parse_aspnet_ajax_delta(
        response_text
    )

    if parsed["is_delta"]:

        print(
            "ASP.NET AJAX delta detected."
        )

        print(
            "UpdatePanel count: "
            f"{len(parsed['html']) > 0}"
        )

        print(
            "Returned hidden fields: "
            f"{len(parsed['hidden_fields'])}"
        )

    candidate = apply_aspnet_ajax_response(
        html,
        response_text,
    )

    # --------------------------------------------------------
    # Verify the destination selector.
    # --------------------------------------------------------

    if (
        "ddlMeDoOdrediste"
        in candidate
    ):

        countries = parse_countries(
            candidate
        )

        print(
            "International tab activated."
        )

        print(
            f"Destination selector contains "
            f"{len(countries)} entries."
        )

        return candidate

    # --------------------------------------------------------
    # Diagnostics.
    # --------------------------------------------------------

    print(
        "DEBUG: ddlMeDoOdrediste still not "
        "present after applying AJAX response."
    )

    print(
        f"DEBUG: Parsed HTML size: "
        f"{len(candidate):,} bytes"
    )

    if parsed["is_delta"]:

        print(
            "DEBUG: ASP.NET AJAX parser found "
            f"{len(parsed['html']):,} bytes "
            "of UpdatePanel content."
        )

    # Save the raw callback for debugging.
    Path(
        "debug_international_response.txt"
    ).write_text(
        response_text,
        encoding="utf-8",
    )

    print(
        "DEBUG: Raw AJAX response saved to "
        "debug_international_response.txt"
    )

    raise RuntimeError(
        "Could not activate Međunarodni promet. "
        "The AJAX response was received but "
        "ddlMeDoOdrediste was not found."
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

    Control:

        ImageButton8
    """

    if (
        "ddlMeDoOdrediste"
        not in html
    ):

        raise RuntimeError(
            "Country selector is missing "
            "before Dopisnica."
        )

    print(
        "Dopisnica selected."
    )

    # --------------------------------------------------------
    # Already active.
    # --------------------------------------------------------

    if (
        "Dopisnica_Aktivna.png"
        in html
    ):

        print(
            "Dopisnica is already active."
        )

        return html

    # --------------------------------------------------------
    # Normal ASP.NET postback.
    # --------------------------------------------------------

    html = post_normal(
        session,
        html,
        {
            "ImageButton8.x": "1",
            "ImageButton8.y": "1",
        },
    )

    if (
        "Dopisnica_Aktivna.png"
        not in html
    ):

        print(
            "Warning: "
            "Dopisnica_Aktivna.png was not "
            "found after clicking ImageButton8."
        )

    else:

        print(
            "Dopisnica activated."
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
    Enable:

        chbMeDoAvionski
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
            "Could not find "
            "chbMeDoAvionski."
        )

    # --------------------------------------------------------
    # Already checked.
    # --------------------------------------------------------

    if checkbox.has_attr(
        "checked"
    ):

        print(
            "Avionski prijenos "
            "already enabled."
        )

        return html

    print(
        "Enabling Avionski prijenos..."
    )

    # --------------------------------------------------------
    # AJAX checkbox postback.
    # --------------------------------------------------------

    html = post_async(
        session,
        html,
        "chbMeDoAvionski",
        {
            "chbMeDoAvionski": "on",
        },
    )

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
            "after asynchronous postback."
        )

    if not checkbox.has_attr(
        "checked"
    ):

        print(
            "Warning: "
            "chbMeDoAvionski was returned "
            "without checked attribute."
        )

        print(
            "The control still exists; "
            "continuing."
        )

    else:

        print(
            "Avionski prijenos enabled."
        )

    return html


# ============================================================
# Country selection
# ============================================================

def select_country(
    session,
    html,
    code,
):
    """
    Select a destination from:

        ddlMeDoOdrediste

    The control performs an ASP.NET AJAX postback.
    """

    html = post_async(
        session,
        html,
        "ddlMeDoOdrediste",
        {
            "ddlMeDoOdrediste": code,
        },
    )

    return html


# ============================================================
# Calculate
# ============================================================

def calculate(
    session,
    html,
    code,
):
    """
    Calculate the 10 g airmail postcard price/status.
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

    # Explicit price/result.
    if "Ukupna cijena" in text:
        return True

    # Any KM price.
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

    # --------------------------------------------------------
    # Open calculator.
    # --------------------------------------------------------

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
    # 4. Read country list.
    # --------------------------------------------------------

    countries = parse_countries(
        html
    )

    if not countries:

        raise RuntimeError(
            "No countries found in "
            "ddlMeDoOdrediste."
        )

    print()
    print(
        f"Found {len(countries)} "
        "destination entries."
    )
    print()

    available = []
    suspended = []
    unknown = []

    # --------------------------------------------------------
    # 5. Test every destination.
    # --------------------------------------------------------

    for index, (
        code,
        name,
    ) in enumerate(
        countries,
        start=1,
    ):

        print(
            f"[{index}/{len(countries)}] "
            f"{name} ({code})",
            flush=True,
        )

        try:

            # ------------------------------------------------
            # Select destination.
            # ------------------------------------------------

            html = select_country(
                session,
                html,
                code,
            )

            # ------------------------------------------------
            # Calculate.
            # ------------------------------------------------

            html = calculate(
                session,
                html,
                code,
            )

            # ------------------------------------------------
            # Determine status.
            # ------------------------------------------------

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

                unknown.append(
                    name
                )

        except Exception as exc:

            print(
                f"    -> ERROR: {exc}",
                flush=True,
            )

            unknown.append(
                name
            )

        time.sleep(
            0.5
        )

    # --------------------------------------------------------
    # 6. Write results.
    # --------------------------------------------------------

    AVAILABLE_FILE.write_text(
        "\n".join(
            available
        ) + "\n",
        encoding="utf-8",
    )

    SUSPENDED_FILE.write_text(
        "\n".join(
            suspended
        ) + "\n",
        encoding="utf-8",
    )

    UNKNOWN_FILE.write_text(
        "\n".join(
            unknown
        ) + "\n",
        encoding="utf-8",
    )

    # --------------------------------------------------------
    # 7. Summary.
    # --------------------------------------------------------

    print()
    print(
        "Finished."
    )
    print()

    print(
        f"Available: "
        f"{len(available)}"
    )

    print(
        f"Suspended: "
        f"{len(suspended)}"
    )

    print(
        f"Unknown/errors: "
        f"{len(unknown)}"
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

    print(
        "Unknown countries written to: "
        f"{UNKNOWN_FILE}"
    )


if __name__ == "__main__":
    main()
