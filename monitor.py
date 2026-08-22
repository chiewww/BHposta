#!/usr/bin/env python3

import html
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup


CALCULATOR_URL = (
    "https://bhpwebout.posta.ba/"
    "KalkulatorCijena_WEB_app/Bos/Default.aspx"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": "bs-BA,bs;q=0.9,en;q=0.8",
}


def hidden_fields(soup):
    result = {}

    for item in soup.select('input[type="hidden"][name]'):
        result[item["name"]] = item.get("value", "")

    return result


def show_relevant_response(response_text):
    """
    Print only the portions of the ASP.NET AJAX response that
    contain useful control names / HTML.
    """

    print()
    print("=" * 70)
    print("DIAGNOSTIC INFORMATION")
    print("=" * 70)

    print()
    print("Response length:")
    print(len(response_text))

    print()
    print("First 2000 characters:")
    print("-" * 70)
    print(response_text[:2000])

    print()
    print("=" * 70)
    print("CONTROL NAMES FOUND IN RESPONSE")
    print("=" * 70)

    names = sorted(
        set(
            re.findall(
                r'(?:id|name)=["\']([^"\']+)["\']',
                html.unescape(response_text),
                flags=re.I,
            )
        )
    )

    for name in names:
        lower = name.lower()

        if (
            "ddl" in lower
            or "dopis" in lower
            or "me" in lower
            or "odred" in lower
            or "avion" in lower
            or "izrac" in lower
            or "tab" in lower
            or "update" in lower
        ):
            print(name)

    print()
    print("=" * 70)
    print("OCCURRENCES OF IMPORTANT WORDS")
    print("=" * 70)

    decoded = html.unescape(response_text)

    words = [
        "ddlMeDoOdrediste",
        "Odrediste",
        "odredišna",
        "odredis",
        "Dopisnica",
        "Dopis",
        "Avionski",
        "avionski",
        "Izračunaj",
        "Izracunaj",
        "UpdatePanel1",
        "ASPxTabControl1",
        "Međunarodni",
        "Medunarodni",
    ]

    for word in words:

        positions = []

        start = 0

        while True:
            position = decoded.lower().find(
                word.lower(),
                start
            )

            if position == -1:
                break

            positions.append(position)

            start = position + len(word)

        if positions:

            print()
            print(
                f'FOUND "{word}" '
                f'{len(positions)} time(s)'
            )

            for position in positions[:10]:

                begin = max(
                    0,
                    position - 500
                )

                end = min(
                    len(decoded),
                    position + 1500
                )

                print("-" * 70)
                print(
                    decoded[begin:end]
                )

    print()
    print("=" * 70)
    print("END DIAGNOSTIC INFORMATION")
    print("=" * 70)


def main():

    session = requests.Session()

    session.headers.update(
        HEADERS
    )

    print(
        "=" * 70
    )

    print(
        "BH Pošta diagnostic"
    )

    print(
        "=" * 70
    )

    print()
    print(
        "Downloading calculator..."
    )

    response = session.get(
        CALCULATOR_URL,
        timeout=60
    )

    response.raise_for_status()

    print(
        f"Initial response: "
        f"{response.status_code}, "
        f"{len(response.text):,} bytes"
    )

    initial_html = response.text

    soup = BeautifulSoup(
        initial_html,
        "html.parser"
    )

    fields = hidden_fields(
        soup
    )

    print()
    print(
        f"Hidden fields found: "
        f"{len(fields)}"
    )

    print()
    print(
        "Submitting international-tab AJAX request..."
    )

    fields.update({
        "ScriptManager1":
            "UpdatePanel1|btnMeDoIzracunaj",

        "ASPxTabControl1":
            '{"activeTabIndex":1}',

        "__EVENTTARGET":
            "",

        "__EVENTARGUMENT":
            "",

        "__ASYNCPOST":
            "true",
    })

    response = session.post(
        CALCULATOR_URL,
        data=fields,
        timeout=60,
        headers={
            "Referer": CALCULATOR_URL,
            "X-Requested-With":
                "XMLHttpRequest",
            "X-MicrosoftAjax":
                "Delta=true",
        },
    )

    response.raise_for_status()

    print(
        f"AJAX response: "
        f"{response.status_code}, "
        f"{len(response.text):,} bytes"
    )

    show_relevant_response(
        response.text
    )

    # Also save locally in the runner.
    Path(
        "debug"
    ).mkdir(
        parents=True,
        exist_ok=True
    )

    Path(
        "debug/response.txt"
    ).write_text(
        response.text,
        encoding="utf-8"
    )

    print()
    print(
        "Diagnostic completed."
    )


if __name__ == "__main__":
    main()
