#!/usr/bin/env python3

import re
import sys
from urllib.parse import urljoin

import requests
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

urllib3.disable_warnings(
    urllib3.exceptions.InsecureRequestWarning
)


def print_section(title):
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def main():
    session = requests.Session()

    try:
        print_section(
            "STEP 1: FETCHING CALCULATOR PAGE"
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
            f"HTTP status: {response.status_code}"
        )

        print(
            f"Final URL: {response.url}"
        )

        print(
            f"Content-Type: "
            f"{response.headers.get('Content-Type')}"
        )

        print(
            f"Downloaded: "
            f"{len(response.content):,} bytes"
        )

        html = response.text

        # --------------------------------------------------
        # Search for calculator-related strings
        # --------------------------------------------------

        print_section(
            "STEP 2: SEARCHING PAGE FOR CALCULATOR MARKERS"
        )

        markers = [
            "ASPxTabControl1",
            "ImageButton8",
            "ddlMeDoOdrediste",
            "pnlMeDopisnice",
            "kalkulator",
            "calculator",
            "Dopisnica",
            "Međunarodni promet",
        ]

        for marker in markers:
            count = html.lower().count(
                marker.lower()
            )

            print(
                f"{marker}: {count} occurrence(s)"
            )

        # --------------------------------------------------
        # Find iframe elements
        # --------------------------------------------------

        print_section(
            "STEP 3: SEARCHING FOR IFRAMES"
        )

        iframe_pattern = re.compile(
            r"<iframe\b[^>]*>",
            re.IGNORECASE,
        )

        iframes = iframe_pattern.findall(
            html
        )

        print(
            f"Found {len(iframes)} iframe(s)."
        )

        if iframes:
            for number, iframe in enumerate(
                iframes,
                start=1,
            ):
                print()
                print(
                    f"IFRAME #{number}:"
                )

                print(iframe)

                src_match = re.search(
                    r"""src\s*=\s*["']([^"']+)["']""",
                    iframe,
                    re.IGNORECASE,
                )

                if src_match:
                    src = src_match.group(1)

                    absolute_url = urljoin(
                        response.url,
                        src,
                    )

                    print(
                        f"Absolute URL: "
                        f"{absolute_url}"
                    )
        else:
            print(
                "No iframe elements found."
            )

        # --------------------------------------------------
        # Search for URLs containing calculator
        # --------------------------------------------------

        print_section(
            "STEP 4: URLS CONTAINING 'KALKULATOR' "
            "OR 'CALCULATOR'"
        )

        url_pattern = re.compile(
            r"""https?://[^"'<>\s]+""",
            re.IGNORECASE,
        )

        urls = url_pattern.findall(
            html
        )

        matching_urls = []

        for found_url in urls:
            clean_url = found_url.rstrip(
                ".,);"
            )

            if (
                "kalkulator" in clean_url.lower()
                or
                "calculator" in clean_url.lower()
            ):
                if clean_url not in matching_urls:
                    matching_urls.append(
                        clean_url
                    )

        if matching_urls:
            for found_url in matching_urls:
                print(found_url)
        else:
            print(
                "No calculator-related URLs "
                "found in the HTML."
            )

        # --------------------------------------------------
        # Search for AJAX / JavaScript URLs
        # --------------------------------------------------

        print_section(
            "STEP 5: JAVASCRIPT REFERENCES "
            "RELATED TO CALCULATOR"
        )

        script_pattern = re.compile(
            r"""<script\b[^>]*src\s*=\s*["']([^"']+)["']""",
            re.IGNORECASE,
        )

        scripts = script_pattern.findall(
            html
        )

        calculator_scripts = []

        for script in scripts:
            absolute_script = urljoin(
                response.url,
                script,
            )

            if (
                "kalkulator"
                in absolute_script.lower()
                or
                "calculator"
                in absolute_script.lower()
            ):
                calculator_scripts.append(
                    absolute_script
                )

        if calculator_scripts:
            for script in calculator_scripts:
                print(script)
        else:
            print(
                "No calculator-specific "
                "JavaScript files found."
            )

        # --------------------------------------------------
        # Search around text "Kalkulator"
        # --------------------------------------------------

        print_section(
            "STEP 6: HTML AROUND 'KALKULATOR'"
        )

        lower_html = html.lower()

        positions = []

        search_terms = [
            "kalkulator",
            "calculator",
            "dopisnica",
        ]

        for term in search_terms:
            start = 0

            while True:
                position = lower_html.find(
                    term,
                    start,
                )

                if position == -1:
                    break

                positions.append(
                    (
                        position,
                        term,
                    )
                )

                start = position + len(term)

        positions.sort()

        if positions:
            shown = set()

            for position, term in positions[:20]:
                context_start = max(
                    0,
                    position - 500,
                )

                context_end = min(
                    len(html),
                    position + 1000,
                )

                context = html[
                    context_start:context_end
                ]

                key = (
                    context_start,
                    context_end,
                )

                if key in shown:
                    continue

                shown.add(key)

                print()
                print(
                    f"--- occurrence: "
                    f"{term} ---"
                )

                print(context)

        else:
            print(
                "No occurrences found."
            )

        # --------------------------------------------------
        # Save complete response
        # --------------------------------------------------

        with open(
            "debug_page.html",
            "w",
            encoding="utf-8",
        ) as file:
            file.write(html)

        print_section(
            "DONE"
        )

        print(
            "Saved complete response as "
            "debug_page.html"
        )

        return 0

    except requests.RequestException as exc:
        print_section(
            "HTTP ERROR"
        )

        print(exc)

        return 1

    except Exception as exc:
        print_section(
            "ERROR"
        )

        print(exc)

        return 1


if __name__ == "__main__":
    sys.exit(main())
