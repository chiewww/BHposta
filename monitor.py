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
# ASP.NET helpers
# ============================================================

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


def apply_async_delta(html, delta):
    """
    Apply an ASP.NET AJAX UpdatePanel delta response to the
    current full HTML document.

    ASP.NET AJAX responses look approximately like:

        40|updatePanel|UpdatePanel2|<html...>
        0|hiddenField|__EVENTTARGET|
        17704|hiddenField|__VIEWSTATE|...
        ...
        27|panelsToRefreshIDs|...
        2|asyncPostBackTimeout|90|

    The response is NOT itself a complete HTML page.
    """

    soup = BeautifulSoup(html, "html.parser")

    pos = 0
    length = len(delta)

    update_count = 0
    hidden_count = 0

    while pos < length:

        # Find the beginning of the next record.
        match = re.match(
            r"(\d+)\|([^|]*)\|([^|]*)\|",
            delta[pos:],
        )

        if not match:
            break

        content_length = int(match.group(1))
        record_type = match.group(2)
        record_id = match.group(3)

        header_length = match.end()

        content_start = pos + header_length
        content_end = content_start + content_length

        content = delta[
            content_start:content_end
        ]

        # Move exactly to the next record.
        pos = content_end

        # ----------------------------------------------------
        # UpdatePanel
        # ----------------------------------------------------

        if record_type == "updatePanel":

            panel = soup.find(
                id=record_id
            )

            if panel:
                new_panel = BeautifulSoup(
                    content,
                    "html.parser",
                )

                # Replace the panel's contents while retaining
                # the existing UpdatePanel wrapper.
                panel.clear()

                for child in list(new_panel.contents):
                    panel.append(child)

                update_count += 1

            else:
                print(
                    f"Warning: UpdatePanel '{record_id}' "
                    f"was returned but does not exist locally."
                )

        # ----------------------------------------------------
        # Hidden field
        # ----------------------------------------------------

        elif record_type == "hiddenField":

            element = soup.find(
                "input",
                {
                    "type": "hidden",
                    "name": record_id,
                },
            )

            if not element:
                element = soup.find(
                    "input",
                    id=record_id,
                )

            if element:
                element["value"] = content

            else:
                # Some hidden fields may not have existed in
                # the initial HTML.
                new_element = soup.new_tag(
                    "input",
                    type="hidden",
                    name=record_id,
                    value=content,
                )

                if record_id:
                    new_element["id"] = record_id

                form = soup.find("form")

                if form:
                    form.append(new_element)

            hidden_count += 1

        # ----------------------------------------------------
        # Other ASP.NET AJAX records
        # ----------------------------------------------------

        elif record_type in {
            "asyncPostBackControlIDs",
            "postBackControlIDs",
            "updatePanelIDs",
            "childUpdatePanelIDs",
            "panelsToRefreshIDs",
            "asyncPostBackTimeout",
            "formAction",
            "scriptBlock",
            "scriptStartupBlock",
            "pageRedirect",
        }:
            # These records contain AJAX framework metadata or
            # JavaScript. We don't need to insert them into the
            # page for our requests.
            pass

        else:
            # Keep this quiet for normal operation, but make
            # unknown records visible while debugging.
            print(
                f"Notice: Ignoring ASP.NET AJAX record "
                f"type='{record_type}', id='{record_id}'"
            )

    if update_count == 0:
        print(
            "Warning: AJAX response contained no UpdatePanel "
            "content."
        )

    if hidden_count == 0:
        print(
            "Warning: AJAX response contained no hidden fields."
        )

    return str(soup)


# ============================================================
# HTTP POST helpers
# ============================================================

def post_async(session, html, event_target, extra=None):
    """
    Perform an ASP.NET AJAX UpdatePanel postback and merge
    the returned delta into the current full HTML document.
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
    }

    response = session.post(
        URL,
        data=data,
        headers=headers,
        timeout=90,
    )

    response.raise_for_status()

    delta = response.text

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # An async response is a delta, not a complete HTML page.
    # Merge it into our existing page.
    # --------------------------------------------------------

    if (
        "|updatePanel|"
        not in delta
        and "|hiddenField|"
        not in delta
    ):
        print(
            "Warning: response does not look like an "
            "ASP.NET AJAX delta."
        )

        # This is useful if the server unexpectedly sends a
        # complete page.
        if "<html" in delta.lower():
            return delta

    return apply_async_delta(
        html,
        delta,
    )


def post_normal(session, html, extra):
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
# Tab / service activation
# ============================================================

def activate_international(session, html):
    """
    Activate Međunarodni promet.

    The server uses ASP.NET AJAX UpdatePanels, so the response
    must be merged into the existing page.
    """

    print("Activating Međunarodni promet...")

    # --------------------------------------------------------
    # First check whether the country selector is already
    # present.
    # --------------------------------------------------------

    if parse_countries(html):
        print(
            "International destination selector already present."
        )
        return html

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
        },
        timeout=90,
    )

    response.raise_for_status()

    delta = response.text

    # --------------------------------------------------------
    # Merge UpdatePanel2 into our original document.
    # --------------------------------------------------------

    html = apply_async_delta(
        html,
        delta,
    )

    countries = parse_countries(html)

   if not countries:

    print()
    print(
        "DEBUG: ddlMeDoOdrediste still not present "
        "after applying the AJAX response."
    )

    print(
        "DEBUG: Response size:",
        len(delta),
        "bytes",
    )

    print(
        "DEBUG: Response beginning:"
    )

    print(
        repr(delta[:1000])
    )

    print(
        "DEBUG: Response ending:"
    )

    print(
        repr(delta[-1000:])
    )

    raise RuntimeError(
        "Could not activate Međunarodni promet. "
        "After applying the ASP.NET AJAX delta, "
        "ddlMeDoOdrediste is still missing."
    )

    print(
        f"International destination selector found "
        f"({len(countries)} entries)."
    )

    return html


def activate_dopisnica(session, html):
    """
    Activate Dopisnica.
    """

    if not parse_countries(html):
        raise RuntimeError(
            "Country selector is missing before Dopisnica."
        )

    print("Dopisnica selected.")

    # If already active, don't click again.
    if "Dopisnica_Aktivna.png" in html:
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
            "Warning: Dopisnica_Aktivna.png was not found "
            "after clicking ImageButton8."
        )

    return html


def activate_airmail(session, html):
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
            "Could not find chbMeDoAvionski after applying "
            "the current page/update-panel state."
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
            "chbMeDoAvionski disappeared after the "
            "ASP.NET AJAX postback."
        )

    if not checkbox.has_attr("checked"):

        # ASP.NET sometimes represents a checked checkbox
        # through the returned form state rather than the
        # literal HTML attribute.
        value = checkbox.get("value")

        if value != "on":
            raise RuntimeError(
                "Avionski prijenos could not be enabled."
            )

    return html


# ============================================================
# Country selection / calculation
# ============================================================

def select_country(session, html, code):
    """
    Reproduce:

        ddlMeDoOdrediste
        onchange -> __doPostBack(...)
    """

    return post_async(
        session,
        html,
        "ddlMeDoOdrediste",
        {
            "ddlMeDoOdrediste": code,
        },
    )


def calculate(session, html, code):
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
    return SUSPENDED_MESSAGE in unescape(html)


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

    # ---------------------------------------------------------
    # 1. Međunarodni promet
    # ---------------------------------------------------------

    html = activate_international(
        session,
        html,
    )

    # ---------------------------------------------------------
    # 2. Dopisnica
    # ---------------------------------------------------------

    html = activate_dopisnica(
        session,
        html,
    )

    # ---------------------------------------------------------
    # 3. Avionski prijenos
    # ---------------------------------------------------------

    html = activate_airmail(
        session,
        html,
    )

    # ---------------------------------------------------------
    # 4. Read destination list
    # ---------------------------------------------------------

    countries = parse_countries(
        html
    )

    if not countries:
        raise RuntimeError(
            "No countries found in ddlMeDoOdrediste."
        )

    print(
        f"Found {len(countries)} destination entries."
    )

    available = []
    suspended = []

    # ---------------------------------------------------------
    # 5. Test every destination at 10 g
    # ---------------------------------------------------------

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

            # Calculate.
            html = calculate(
                session,
                html,
                code,
            )

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

        except Exception as exc:

            print(
                f"    -> ERROR: {exc}",
                flush=True,
            )

        time.sleep(0.5)

    # ---------------------------------------------------------
    # 6. Write results
    # ---------------------------------------------------------

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
    print()

    print(
        f"Available countries written to: "
        f"{AVAILABLE_FILE}"
    )

    print(
        f"Suspended countries written to: "
        f"{SUSPENDED_FILE}"
    )


if __name__ == "__main__":
    main()
