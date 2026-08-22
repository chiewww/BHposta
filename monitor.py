import asyncio
import os
from pathlib import Path

from playwright.async_api import async_playwright


CALCULATOR_URL = os.environ.get(
    "CALCULATOR_URL",
    "https://www.posta.ba/kalkulator-cijena/",
)

DIAGNOSTIC_FILE = Path("diagnostic.txt")

TIMEOUT_MS = 30_000


async def main():

    print("=" * 70)
    print("JP BH POŠTA CALCULATOR DIAGNOSTIC")
    print("=" * 70)
    print()
    print(f"URL: {CALCULATOR_URL}")
    print()

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True
        )

        page = await browser.new_page(
            viewport={
                "width": 1440,
                "height": 1200,
            },
            locale="hr-HR",
        )

        page.set_default_timeout(TIMEOUT_MS)

        print("Opening page...")

        response = await page.goto(
            CALCULATOR_URL,
            wait_until="domcontentloaded",
            timeout=TIMEOUT_MS,
        )

        print(f"HTTP status: {response.status if response else 'unknown'}")
        print(f"Final URL: {page.url}")
        print()

        await page.wait_for_timeout(3000)

        # -------------------------------------------------------------
        # Basic page information
        # -------------------------------------------------------------

        title = await page.title()

        print(f"Page title: {title}")
        print()

        # -------------------------------------------------------------
        # Check expected selectors
        # -------------------------------------------------------------

        selectors = [
            "#ddlMeDoOdrediste",
            "#chbMeDoAvionski",
            "#tbxMeDoAvioTezina",
            "#btnMeDoIzracunaj",
            "#btnMeObPiIzracunaj",
            "#btnMeDoIzracunaj",
            "input[type='submit']",
            "input[type='button']",
            "input[type='image']",
        ]

        diagnostic_lines = []

        diagnostic_lines.append(
            "JP BH POŠTA CALCULATOR DIAGNOSTIC"
        )
        diagnostic_lines.append(
            "=" * 70
        )
        diagnostic_lines.append(
            f"Requested URL: {CALCULATOR_URL}"
        )
        diagnostic_lines.append(
            f"Final URL: {page.url}"
        )
        diagnostic_lines.append(
            f"Page title: {title}"
        )
        diagnostic_lines.append("")

        print("=" * 70)
        print("EXPECTED CONTROLS")
        print("=" * 70)

        diagnostic_lines.append(
            "EXPECTED CONTROLS"
        )
        diagnostic_lines.append(
            "=" * 70
        )

        for selector in selectors:

            count = await page.locator(selector).count()

            print(
                f"{selector:35} -> {count} found"
            )

            diagnostic_lines.append(
                f"{selector:35} -> {count} found"
            )

        print()

        # -------------------------------------------------------------
        # Destination dropdown
        # -------------------------------------------------------------

        destination = page.locator(
            "#ddlMeDoOdrediste"
        )

        destination_count = await destination.count()

        diagnostic_lines.append("")
        diagnostic_lines.append(
            "DESTINATION DROPDOWN"
        )
        diagnostic_lines.append(
            "=" * 70
        )

        print("=" * 70)
        print("DESTINATION DROPDOWN")
        print("=" * 70)

        if destination_count == 0:

            print(
                "NOT FOUND: #ddlMeDoOdrediste"
            )

            diagnostic_lines.append(
                "NOT FOUND: #ddlMeDoOdrediste"
            )

        else:

            options = await destination.locator(
                "option"
            ).evaluate_all(
                """
                options => options.map((option, index) => ({
                    index: index,
                    value: option.value,
                    name: option.textContent.trim(),
                    selected: option.selected
                }))
                """
            )

            print(
                f"Number of options: {len(options)}"
            )

            diagnostic_lines.append(
                f"Number of options: {len(options)}"
            )

            diagnostic_lines.append("")

            for option in options:

                line = (
                    f"{option['index'] + 1}. "
                    f"value={option['value']!r} "
                    f"name={option['name']!r} "
                    f"selected={option['selected']}"
                )

                print(line)

                diagnostic_lines.append(line)

        print()

        # -------------------------------------------------------------
        # Avionski prijenos checkbox
        # -------------------------------------------------------------

        print("=" * 70)
        print("AVIONSKI PRIJENOS")
        print("=" * 70)

        diagnostic_lines.append(
            "AVIONSKI PRIJENOS"
        )
        diagnostic_lines.append(
            "=" * 70
        )

        air = page.locator(
            "#chbMeDoAvionski"
        )

        if await air.count() == 0:

            print(
                "NOT FOUND: #chbMeDoAvionski"
            )

            diagnostic_lines.append(
                "NOT FOUND: #chbMeDoAvionski"
            )

        else:

            checked = await air.is_checked()

            html = await air.evaluate(
                "element => element.outerHTML"
            )

            print(
                f"Checked: {checked}"
            )
            print(
                f"HTML: {html}"
            )

            diagnostic_lines.append(
                f"Checked: {checked}"
            )
            diagnostic_lines.append(
                f"HTML: {html}"
            )

        print()

        # -------------------------------------------------------------
        # Weight input
        # -------------------------------------------------------------

        print("=" * 70)
        print("AIR WEIGHT INPUT")
        print("=" * 70)

        diagnostic_lines.append(
            "AIR WEIGHT INPUT"
        )
        diagnostic_lines.append(
            "=" * 70
        )

        weight = page.locator(
            "#tbxMeDoAvioTezina"
        )

        if await weight.count() == 0:

            print(
                "NOT FOUND: #tbxMeDoAvioTezina"
            )

            diagnostic_lines.append(
                "NOT FOUND: #tbxMeDoAvioTezina"
            )

        else:

            visible = await weight.is_visible()
            value = await weight.input_value()

            html = await weight.evaluate(
                "element => element.outerHTML"
            )

            print(
                f"Visible: {visible}"
            )
            print(
                f"Current value: {value!r}"
            )
            print(
                f"HTML: {html}"
            )

            diagnostic_lines.append(
                f"Visible: {visible}"
            )
            diagnostic_lines.append(
                f"Current value: {value!r}"
            )
            diagnostic_lines.append(
                f"HTML: {html}"
            )

        print()

        # -------------------------------------------------------------
        # Find every button/input that could be Izračunaj
        # -------------------------------------------------------------

        print("=" * 70)
        print("CALCULATION CONTROLS")
        print("=" * 70)

        diagnostic_lines.append(
            "CALCULATION CONTROLS"
        )
        diagnostic_lines.append(
            "=" * 70
        )

        controls = await page.locator(
            "input,button"
        ).evaluate_all(
            """
            elements => elements.map((element, index) => ({
                index: index,
                tag: element.tagName,
                type: element.getAttribute("type"),
                id: element.id,
                name: element.getAttribute("name"),
                value: element.getAttribute("value"),
                text: element.textContent.trim(),
                title: element.getAttribute("title"),
                onclick: element.getAttribute("onclick")
            }))
            """
        )

        for control in controls:

            combined = " ".join(
                str(control.get(key) or "")
                for key in [
                    "id",
                    "name",
                    "value",
                    "text",
                    "title",
                    "onclick",
                ]
            )

            if (
                "izracunaj" in combined.lower()
                or "izračunaj" in combined.lower()
            ):

                line = (
                    f"index={control['index']} "
                    f"tag={control['tag']} "
                    f"type={control['type']!r} "
                    f"id={control['id']!r} "
                    f"name={control['name']!r} "
                    f"value={control['value']!r} "
                    f"text={control['text']!r} "
                    f"title={control['title']!r} "
                    f"onclick={control['onclick']!r}"
                )

                print(line)

                diagnostic_lines.append(line)

        print()

        # -------------------------------------------------------------
        # All UpdatePanels
        # -------------------------------------------------------------

        print("=" * 70)
        print("UPDATEPANELS")
        print("=" * 70)

        diagnostic_lines.append(
            "UPDATEPANELS"
        )
        diagnostic_lines.append(
            "=" * 70
        )

        panels = await page.locator(
            "[id*='UpdatePanel'], [id*='updatePanel']"
        ).evaluate_all(
            """
            elements => elements.map(element => ({
                id: element.id,
                tag: element.tagName,
                className: element.className
            }))
            """
        )

        for panel in panels:

            line = (
                f"id={panel['id']!r} "
                f"tag={panel['tag']} "
                f"class={panel['className']!r}"
            )

            print(line)
            diagnostic_lines.append(line)

        print()

        # -------------------------------------------------------------
        # Relevant page HTML around the destination control
        # -------------------------------------------------------------

        print("=" * 70)
        print("DESTINATION CONTROL HTML")
        print("=" * 70)

        diagnostic_lines.append(
            "DESTINATION CONTROL HTML"
        )
        diagnostic_lines.append(
            "=" * 70
        )

        if destination_count:

            destination_html = await destination.evaluate(
                "element => element.outerHTML"
            )

            print(destination_html)

            diagnostic_lines.append(
                destination_html
            )

        print()

        # -------------------------------------------------------------
        # Search rendered page for the unavailable message
        # -------------------------------------------------------------

        ERROR_MESSAGE = (
            "Prijem pošiljaka se trenutno ne vrši za odabranu državu"
        )

        body_text = await page.locator(
            "body"
        ).inner_text()

        print("=" * 70)
        print("ERROR MESSAGE CHECK")
        print("=" * 70)

        diagnostic_lines.append(
            "ERROR MESSAGE CHECK"
        )
        diagnostic_lines.append(
            "=" * 70
        )

        if ERROR_MESSAGE in body_text:

            print(
                "ERROR MESSAGE IS CURRENTLY PRESENT"
            )

            diagnostic_lines.append(
                "ERROR MESSAGE IS CURRENTLY PRESENT"
            )

        else:

            print(
                "ERROR MESSAGE IS NOT CURRENTLY PRESENT"
            )

            diagnostic_lines.append(
                "ERROR MESSAGE IS NOT CURRENTLY PRESENT"
            )

        print()

        # -------------------------------------------------------------
        # Save screenshot
        # -------------------------------------------------------------

        screenshot_path = Path(
            "diagnostic.png"
        )

        await page.screenshot(
            path=str(screenshot_path),
            full_page=True,
        )

        print(
            f"Screenshot saved to: {screenshot_path}"
        )

        diagnostic_lines.append("")
        diagnostic_lines.append(
            f"Screenshot saved to: {screenshot_path}"
        )

        # -------------------------------------------------------------
        # Save diagnostic text
        # -------------------------------------------------------------

        DIAGNOSTIC_FILE.write_text(
            "\n".join(diagnostic_lines) + "\n",
            encoding="utf-8",
        )

        print(
            f"Diagnostic report saved to: {DIAGNOSTIC_FILE}"
        )

        print()

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
