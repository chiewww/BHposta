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


def inspect_response(response, label):
    print()
    print("=" * 70)
    print(label)
    print("=" * 70)

    print(
        f"Final URL: {response.url}"
    )

    print(
        f"Status: {response.status_code}"
    )

    print(
        f"Content-Type: "
        f"{response.headers.get('Content-Type')}"
    )

    print(
        f"Content-Length: "
        f"{response.headers.get('Content-Length')}"
    )

    print(
        f"Location: "
        f"{response.headers.get('Location')}"
    )

    print(
        f"X-Requested-With: "
        f"{response.headers.get('X-Requested-With')}"
    )

    print(
        f"Response bytes: "
        f"{len(response.content):,}"
    )

    print()
    print("--- RESPONSE BEGINNING ---")

    beginning = response.text[:3000]

    print(beginning)

    print("--- RESPONSE ENDING ---")
    print("=" * 70)


def get_form(response):
    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    form = soup.find("form")

    if form is None:
        raise RuntimeError(
            "Could not find <form> in response."
        )

    return soup, form


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


def main():
    session = requests.Session()

    try:
        print(
            "STEP 1: GET calculator..."
        )

        response = session.get(
            URL,
            headers=HEADERS,
            timeout=60,
            verify=False,
        )

        response.raise_for_status()

        print(
            f"HTTP status: "
            f"{response.status_code}"
        )

        print(
            f"Downloaded: "
            f"{len(response.content):,} bytes"
        )

        save_response(
            DEBUG_INITIAL,
            response,
        )

        soup, form = get_form(
            response
        )

        print()
        print(
            "Form information:"
        )

        print(
            f"Form action: "
            f"{form.get('action')}"
        )

        print(
            f"Form method: "
            f"{form.get('method')}"
        )

        print()
        print(
            "STEP 2: Attempting "
            "International tab request..."
        )

        data = hidden_fields(form)

        data["__EVENTTARGET"] = (
            "ASPxTabControl1"
        )

        data["__EVENTARGUMENT"] = "1"

        action = form.get(
            "action"
        )

        if action:
            post_url = (
                requests.compat.urljoin(
                    response.url,
                    action,
                )
            )
        else:
            post_url = response.url

        print(
            f"POST URL: {post_url}"
        )

        response2 = session.post(
            post_url,
            data=data,
            headers={
                **HEADERS,
                "Referer": response.url,
                "Content-Type": (
                    "application/x-www-form-urlencoded"
                ),
            },
            timeout=60,
            verify=False,
            allow_redirects=False,
        )

        save_response(
            DEBUG_INTERNATIONAL,
            response2,
        )

        inspect_response(
            response2,
            "INTERNATIONAL TAB RESPONSE",
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
