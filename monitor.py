#!/usr/bin/env python3

import requests
from bs4 import BeautifulSoup
from pathlib import Path
import sys


URL = "https://www.posta.ba/kalkulator-cijena/"

OUTPUT_FILE = Path("countries.txt")

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
    "Accept-Language": "bs-BA,bs;q=0.9,en-US;q=0.8,en;q=0.7",
}


def fetch_page():
    print(f"Fetching: {URL}")

    response = requests.get(
        URL,
        headers=HEADERS,
        timeout=60,
    )

    response.raise_for_status()

    print(f"HTTP status: {response.status_code}")
    print(f"Downloaded: {len(response.content):,} bytes")

    return response.text


def extract_countries(html):
    soup = BeautifulSoup(html, "html.parser")

    # This is the country dropdown identified from the HTML
    # provided from the website.
    country_select = soup.find(
        "select",
        id="ddlMeDoOdrediste"
    )

    if country_select is None:
        raise RuntimeError(
            "Could not find the country dropdown "
            '#ddlMeDoOdrediste in the HTML returned by the website.'
        )

    options = country_select.find_all("option")

    if not options:
        raise RuntimeError(
            "The country dropdown was found, "
            "but it contains no <option> elements."
        )

    countries = []

    for option in options:
        value = option.get("value", "")
        name = option.get_text(strip=True)

        # Ignore empty options.
        if not name:
            continue

        countries.append(
            (value, name)
        )

    if not countries:
        raise RuntimeError(
            "No country names were found in the dropdown."
        )

    return countries


def write_output(countries):
    # Keep the exact order from the website.
    # Each line contains the original option value and
    # the country name.
    lines = []

    for value, name in countries:
        lines.append(
            f'<option value="{value}">{name}</option>'
        )

    output = "\n".join(lines) + "\n"

    OUTPUT_FILE.write_text(
        output,
        encoding="utf-8",
    )

    print()
    print(f"Wrote {len(countries)} countries to {OUTPUT_FILE}")
    print()
    print("Countries:")
    print("=" * 70)

    for value, name in countries:
        print(f'<option value="{value}">{name}</option>')

    print("=" * 70)


def main():
    try:
        html = fetch_page()

        countries = extract_countries(html)

        write_output(countries)

        return 0

    except requests.RequestException as exc:
        print()
        print("ERROR: Unable to retrieve the website.")
        print(exc)
        return 1

    except Exception as exc:
        print()
        print("ERROR:")
        print(exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
