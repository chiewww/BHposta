#!/usr/bin/env python3

import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup
import urllib3


URL = "https://www.posta.ba/kalkulator-cijena/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": (
        "hr-HR,hr;q=0.9,bs;q=0.8,en;q=0.7"
    ),
}

DEBUG_INITIAL = Path(
    "debug_initial.html"
)

DEBUG_INTERNATIONAL = Path(
    "debug_international.html"
)

urllib3.disable_warnings(
    urllib3.exceptions.InsecureRequestWarning
)


def save_response(path, response):
    path.write_text(
        response.text,
        encoding="utf-8",
    )

    print(
        f"Saved response to: {path}"
    )


def find_calculator_form(response):
    """
    Find the actual ASP.NET calculator form.

    The page contains other forms, including an outer
    WordPress form. We must NOT simply use soup.find("form").
    """

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    forms = soup.find_all("form")

    print()
    print(
        f"Found {len(forms)} <form> elements."
    )

    for index, form in enumerate(forms, start=1):
        form_text = str(form)

        indicators = [
            "ASPxTabControl1",
            "ImageButton8",
            "ddlMeDoOdrediste",
            "pnlMeDopisnice",
            "ddlMeObPiOderdiste",
        ]

        matches = [
            item
            for item in indicators
            if item in form_text
        ]

        print()
        print(
            f"FORM #{index}"
        )

        print(
            f"  action = {form.get('action')}"
        )

        print(
            f"  method = {form.get('method')}"
        )

        if matches:
            print(
                "  calculator controls = "
                + ", ".join(matches)
            )
        else:
            print(
                "  calculator controls = NONE"
            )

        if matches:
            print()
            print(
                f"Using FORM #{index}."
            )

            return soup, form

    raise RuntimeError(
        "Could not find the ASP.NET calculator form. "
        "None of the forms contained the expected "
        "calculator controls."
    )


def hidden_fields(form):
    data = {}

    for element in form.select(
        'input[type="hidden"]'
    ):
        name = element.get("name")

        if name:
            data[name] = element.get(
                "value",
                "",
            )

    return data


def inspect_calculator(response, label):
    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    print()
    print("=" * 70)
    print(label)
    print("=" * 70)

    controls = [
        "ASPxTabControl1",
        "ASPxTabControl1_AT1",
        "ImageButton8",
        "pnlMeDopisnice",
        "ddlMeDoOdrediste",
        "pnlMeObicnoPismo",
        "ddlMeObPiOderdiste",
    ]

    for control_id in controls:
        element = soup.find(
            id=control_id
        )

        if element is None:
            print(
                f"{control_id}: NOT FOUND"
            )
        else:
            print(
                f"{control_id}: FOUND"
            )

            if control_id == "ImageButton8":
                print(
                    f"  src = "
                    f"{element.get('src')}"
                )

    print("=" * 70)


def main():
    session = requests.Session()

    try:
        # --------------------------------------------------
        # STEP 1
        # --------------------------------------------------

        print(
            "STEP 1: Fetching calculator page..."
        )

        response = session.get(
            URL,
            headers=HEADERS,
            timeout=60,
            verify=False,
            allow_redirects=True,
        )

        response.raise_for_status()

        print(
            f"HTTP status: "
            f"{response.status_code}"
        )

        print(
            f"Final URL: "
            f"{response.url}"
        )

        print(
            f"Downloaded: "
            f"{len(response.content):,} bytes"
        )

        save_response(
            DEBUG_INITIAL,
            response,
        )

        inspect_calculator(
            response,
            "INITIAL CALCULATOR PAGE",
        )

        # --------------------------------------------------
        # STEP 2
        # --------------------------------------------------

        print()
        print(
            "STEP 2: Finding the calculator form..."
        )

        soup, form = find_calculator_form(
            response
        )

        print()
        print(
            "Calculator form:"
        )

        print(
            f"Action: "
            f"{form.get('action')}"
        )

        print(
            f"Method: "
            f"{form.get('method')}"
        )

        # --------------------------------------------------
        # STEP 3
        # --------------------------------------------------

        print()
        print(
            "STEP 3: Collecting ASP.NET state..."
        )

        data = hidden_fields(
            form
        )

        print(
            f"Hidden fields collected: "
            f"{len(data)}"
        )

        for name in sorted(data):
            if name in (
                "__VIEWSTATE",
                "__VIEWSTATEGENERATOR",
                "__EVENTVALIDATION",
                "__EVENTTARGET",
                "__EVENTARGUMENT",
            ):
                value = data[name]

                print(
                    f"  {name}: "
                    f"{len(value)} characters"
                )

        # --------------------------------------------------
        # STEP 4
        # --------------------------------------------------
        #
        # IMPORTANT:
        #
        # We are NOT going to submit anything yet.
        #
        # First we need to confirm that we found the
        # correct ASP.NET form.
        #
        # The previous script accidentally submitted the
        # outer WordPress form to https://www.posta.ba/.
        #
        # This script stops here so we can verify the form.
        #

        print()
        print(
            "=" * 70
        )

        print(
            "SUCCESS: The correct calculator form "
            "was found."
        )

        print(
            "=" * 70
        )

        print()
        print(
            "The form action above should be the "
            "calculator's ASP.NET action, not the "
            "WordPress homepage form."
        )

        print()
        print(
            "No POST was performed."
        )

        return 0

    except requests.RequestException as exc:
        print()
        print(
            "ERROR: HTTP request failed:"
        )
        print(exc)
        return 1

    except Exception as exc:
        print()
        print(
            "ERROR:"
        )
        print(exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
