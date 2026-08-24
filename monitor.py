import re
import time
from pathlib import Path
from html import unescape

import requests
from bs4 import BeautifulSoup


URL = "https://bhpwebout.posta.ba/KalkulatorCijena_WEB_app/Bos/Default.aspx"

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
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "bs-BA,bs;q=0.9,en-US;q=0.8,en;q=0.7",
    "Connection": "keep-alive",
}


# ============================================================
# Basic helpers
# ============================================================

def get_hidden_fields(html):
    """
    Return all ASP.NET hidden input fields.
    """

    soup = BeautifulSoup(html, "html.parser")

    data = {}

    for element in soup.select("input[type='hidden']"):
        name = element.get("name")

        if name:
            data[name] = element.get("value", "")

    return data


def parse_countries(html):
    """
    Read destination countries from:

        ddlMeDoOdrediste
    """

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
        name = option.get_text(" ", strip=True)

        if value and name:
            result.append((value, name))

    return result


def find_text(html, text):
    return text in unescape(html)


def page_text(html):
    return BeautifulSoup(
        unescape(html),
        "html.parser",
    ).get_text(
        " ",
        strip=True,
    )


# ============================================================
# DevExpress / ASP.NET response helpers
# ============================================================

def extract_devexpress_callback_html(response_text):
    """
    DevExpress callbacks do not necessarily return normal HTML.

    Depending on the server version/configuration, the response can
    contain records such as:

        2|...|callbackHtml|...

    or other pipe-delimited callback data.

    This function attempts to recover useful HTML from those
    responses.

    If the response is already normal HTML, it is returned unchanged.
    """

    text = response_text or ""

    if not text:
        return text

    # Already a normal HTML document.
    if (
        "<html" in text.lower()
        or "<form" in text.lower()
        or "<select" in text.lower()
        or "<input" in text.lower()
    ):
        return text

    # --------------------------------------------------------
    # ASP.NET AJAX delta format
    # --------------------------------------------------------

    markers = [
        "updatePanel|",
        "content|",
        "hiddenField|",
        "scriptBlock|",
    ]

    if any(marker in text for marker in markers):

        pieces = []

        parts = text.split("|")

        i = 0

        while i < len(parts):

            part = parts[i]

            if part in (
                "updatePanel",
                "content",
                "scriptBlock",
            ):

                if i + 2 < len(parts):

                    try:
                        length = int(parts[i + 1])
                        content = parts[i + 2]

                        pieces.append(content[:length])

                        i += 3
                        continue

                    except (ValueError, TypeError):
                        pass

            i += 1

        if pieces:

            combined = "\n".join(pieces)

            if (
                "<select" in combined.lower()
                or "<form" in combined.lower()
                or "<input" in combined.lower()
            ):
                return combined

    # --------------------------------------------------------
    # Generic fallback
    # --------------------------------------------------------

    # If the callback response contains an HTML fragment, extract
    # the largest useful portion.
    lower = text.lower()

    candidates = []

    for marker in (
        "<form",
        "<select",
        "<div",
        "<table",
        "<html",
    ):

        pos = lower.find(marker)

        if pos >= 0:
            candidates.append(pos)

    if candidates:

        start = min(candidates)

        candidate = text[start:]

        if (
            "<select" in candidate.lower()
            or "<form" in candidate.lower()
        ):
            return candidate

    return text


def debug_response(response_text, label):
    """
    Print useful information about unusual callback responses.
    """

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
# Normal ASP.NET requests
# ============================================================

def post_normal(session, html, extra):
    """
    Normal ASP.NET form POST.
    """

    data = get_hidden_fields(html)

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
# ASP.NET AJAX postback
# ============================================================

def post_async(
    session,
    html,
    event_target,
    extra=None,
):
    """
    ASP.NET UpdatePanel-style asynchronous postback.
    """

    data = get_hidden_fields(html)

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
# DevExpress callback
# ============================================================

def post_devexpress_callback(
    session,
    html,
    control_id,
    callback_parameter,
):
    """
    Perform a DevExpress-style callback.

    DevExpress controls commonly use:

        __CALLBACKID
        __CALLBACKPARAM

    rather than a normal ASP.NET __EVENTTARGET postback.
    """

    data = get_hidden_fields(html)

    data["__CALLBACKID"] = control_id
    data["__CALLBACKPARAM"] = callback_parameter

    headers = {
        **HEADERS,
        "X-Requested-With": "XMLHttpRequest",
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
# International tab
# ============================================================

def activate_international(session, html):
    """
    Activate:

        Međunarodni promet

    The page uses a DevExpress ASPxTabControl.

    A normal:

        __EVENTTARGET=ASPxTabControl1

    is NOT sufficient because DevExpress tab controls normally
    perform their own callback.

    We therefore try several known callback forms and only accept
    a result once ddlMeDoOdrediste actually appears.
    """

    print("Activating Međunarodni promet...")

    # --------------------------------------------------------
    # First: perhaps the international tab is already active.
    # --------------------------------------------------------

    if "ddlMeDoOdrediste" in html:

        print(
            "International destination selector is already present."
        )

        return html

    # --------------------------------------------------------
    # Attempt 1:
    # DevExpress callback.
    # --------------------------------------------------------

    callback_parameters = [
        "1",
        "1|",
        "0|1",
    ]

    for parameter in callback_parameters:

        print(
            "Trying DevExpress tab callback "
            f"parameter={parameter!r}..."
        )

        try:

            response_text = post_devexpress_callback(
                session,
                html,
                "ASPxTabControl1",
                parameter,
            )

            debug_response(
                response_text,
                "DevExpress tab callback",
            )

            candidate = extract_devexpress_callback_html(
                response_text
            )

            if "ddlMeDoOdrediste" in candidate:

                print(
                    "International tab activated "
                    "using DevExpress callback."
                )

                return candidate

        except Exception as exc:

            print(
                "DevExpress callback failed: "
                f"{exc}"
            )

    # --------------------------------------------------------
    # Attempt 2:
    # ASP.NET event target.
    # --------------------------------------------------------

    print(
        "Trying ASP.NET event-target fallback..."
    )

    try:

        data = get_hidden_fields(html)

        data["__EVENTTARGET"] = "ASPxTabControl1"
        data["__EVENTARGUMENT"] = "1"
        data["__ASYNCPOST"] = "true"

        response = session.post(
            URL,
            data=data,
            headers={
                **HEADERS,
                "X-Requested-With": "XMLHttpRequest",
                "X-MicrosoftAjax": "Delta=true",
                "Referer": URL,
                "Content-Type": (
                    "application/x-www-form-urlencoded"
                ),
            },
            timeout=90,
        )

        response.raise_for_status()

        response_text = response.text

        debug_response(
            response_text,
            "ASP.NET tab fallback",
        )

        candidate = extract_devexpress_callback_html(
            response_text
        )

        if "ddlMeDoOdrediste" in candidate:

            print(
                "International tab activated "
                "using ASP.NET fallback."
            )

            return candidate

    except Exception as exc:

        print(
            "ASP.NET tab fallback failed: "
            f"{exc}"
        )

    # --------------------------------------------------------
    # Attempt 3:
    # Normal POST with possible DevExpress tab value.
    # --------------------------------------------------------

    print(
        "Trying normal form POST fallback..."
    )

    try:

        data = get_hidden_fields(html)

        # Common DevExpress selected-index hidden fields.
        possible_fields = [
            "ASPxTabControl1",
            "ASPxTabControl1_VI",
            "ASPxTabControl1$VI",
        ]

        for field in possible_fields:
            data[field] = "1"

        response = session.post(
            URL,
            data=data,
            headers={
                **HEADERS,
                "Referer": URL,
                "Content-Type": (
                    "application/x-www-form-urlencoded"
                ),
            },
            timeout=90,
        )

        response.raise_for_status()

        response_text = response.text

        debug_response(
            response_text,
            "normal tab fallback",
        )

        candidate = extract_devexpress_callback_html(
            response_text
        )

        if "ddlMeDoOdrediste" in candidate:

            print(
                "International tab activated "
                "using normal POST fallback."
            )

            return candidate

    except Exception as exc:

        print(
            "Normal POST fallback failed: "
            f"{exc}"
        )

    # --------------------------------------------------------
    # Nothing worked.
    # --------------------------------------------------------

    print(
        "DEBUG: ddlMeDoOdrediste still not present "
        "after all international-tab attempts."
    )

    print(
        f"DEBUG: Original page size: "
        f"{len(html):,} bytes"
    )

    raise RuntimeError(
        "Could not activate Međunarodni promet. "
        "The DevExpress tab callback did not return "
        "ddlMeDoOdrediste."
    )


# ============================================================
# Dopisnica
# ============================================================

def activate_dopisnica(session, html):
    """
    Select:

        Dopisnica

    Control:

        ImageButton8
    """

    if "ddlMeDoOdrediste" not in html:

        raise RuntimeError(
            "Country selector is missing before Dopisnica."
        )

    print("Dopisnica selected.")

    # Already active.
    if "Dopisnica_Aktivna.png" in html:

        print(
            "Dopisnica is already active."
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
            "Warning: Dopisnica_Aktivna.png was not "
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

def activate_airmail(session, html):
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
            "Could not find chbMeDoAvionski."
        )

    # HTML checked state.
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

    candidate = extract_devexpress_callback_html(
        html
    )

    soup = BeautifulSoup(
        candidate,
        "html.parser",
    )

    checkbox = soup.find(
        "input",
        id="chbMeDoAvionski",
    )

    if (
        not checkbox
        or not checkbox.has_attr("checked")
    ):

        # Some ASP.NET pages don't return the checked
        # attribute even though the server-side value was
        # accepted. Do not immediately fail.

        print(
            "Warning: checkbox was not returned as "
            "checked after asynchronous postback."
        )

        # If the control still exists, continue.
        if checkbox:

            print(
                "chbMeDoAvionski still exists; "
                "continuing."
            )

            return candidate

        raise RuntimeError(
            "Avionski prijenos could not be enabled."
        )

    print(
        "Avionski prijenos enabled."
    )

    return candidate


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

    html = post_async(
        session,
        html,
        "ddlMeDoOdrediste",
        {
            "ddlMeDoOdrediste": code,
        },
    )

    return extract_devexpress_callback_html(
        html
    )


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
# Status detection
# ============================================================

def is_suspended(html):
    return (
        SUSPENDED_MESSAGE
        in unescape(html)
    )


def is_available(html):
    text = page_text(html)

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
    # 4. Read destination list
    # --------------------------------------------------------

    countries = parse_countries(
        html
    )

    if not countries:

        raise RuntimeError(
            "No countries found in "
            "ddlMeDoOdrediste."
        )

    print(
        f"Found {len(countries)} "
        f"destination entries."
    )

    available = []
    suspended = []
    unknown = []

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
            # Determine result.
            # ------------------------------------------------

            if is_suspended(html):

                print(
                    "    -> SUSPENDED",
                    flush=True,
                )

                suspended.append(
                    name
                )

            elif is_available(html):

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

        time.sleep(0.5)

    # --------------------------------------------------------
    # 6. Write results
    # --------------------------------------------------------

    AVAILABLE_FILE.write_text(
        "\n".join(available) + "\n",
        encoding="utf-8",
    )

    SUSPENDED_FILE.write_text(
        "\n".join(suspended) + "\n",
        encoding="utf-8",
    )

    UNKNOWN_FILE.write_text(
        "\n".join(unknown) + "\n",
        encoding="utf-8",
    )

    # --------------------------------------------------------
    # 7. Summary
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
        f"Available countries written to: "
        f"{AVAILABLE_FILE}"
    )

    print(
        f"Suspended countries written to: "
        f"{SUSPENDED_FILE}"
    )

    print(
        f"Unknown countries written to: "
        f"{UNKNOWN_FILE}"
    )


if __name__ == "__main__":
    main()
