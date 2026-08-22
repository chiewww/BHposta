import asyncio
import os
import re
from pathlib import Path

from playwright.async_api import async_playwright


# ============================================================
# CONFIGURATION
# ============================================================

URL = os.environ.get(
    "CALCULATOR_URL",
    "https://www.posta.ba/kalkulator-cijena/",
)

IFRAME_URL_PART = "KalkulatorCijena_WEB_app"

OUTPUT_DIR = Path(".")


# ============================================================
# HELPERS
# ============================================================

def section(title):
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def save_text(filename, text):
    path = OUTPUT_DIR / filename
    path.write_text(text, encoding="utf-8")
    print(f"Saved: {path} ({len(text):,} bytes)")


def clean_text(text):
    return re.sub(r"\s+", " ", text or "").strip()


# ============================================================
# MAIN
# ============================================================

async def main():

    section("JP BH POŠTA CALCULATOR IFRAME DIAGNOSTIC")

    print(f"URL: {URL}")

    if not URL:
        raise RuntimeError("CALCULATOR_URL is empty")

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True
        )

        context = await browser.new_context(
            viewport={
                "width": 1440,
                "height": 1200,
            },
            locale="hr-HR",
        )

        page = await context.new_page()

        # --------------------------------------------------------
        # PAGE NAVIGATION
        # --------------------------------------------------------

        section("OPENING MAIN PAGE")

        print("Opening page...")

        response = await page.goto(
            URL,
            wait_until="domcontentloaded",
            timeout=60_000,
        )

        if response:
            print(f"HTTP status: {response.status}")
        else:
            print("No HTTP response object returned.")

        print(f"Final URL: {page.url}")

        try:
            print(f"Page title: {await page.title()}")
        except Exception:
            print("Could not read page title.")

        # Give JavaScript/iframes time to initialize.
        await page.wait_for_timeout(8_000)

        # --------------------------------------------------------
        # SAVE MAIN PAGE
        # --------------------------------------------------------

        section("SAVING MAIN PAGE")

        main_html = await page.content()

        save_text(
            "page.html",
            main_html,
        )

        # --------------------------------------------------------
        # MAIN PAGE INFORMATION
        # --------------------------------------------------------

        section("MAIN PAGE INFORMATION")

        print(f"Main page HTML length: {len(main_html):,}")

        # --------------------------------------------------------
        # RAW HTML SEARCH
        # --------------------------------------------------------

        section("SEARCHING MAIN PAGE HTML")

        search_strings = [
            "ddlMeDoOdrediste",
            "chbMeDoAvionski",
            "tbxMeDoAvioTezina",
            "btnMeDoIzracunaj",
            "btnMeObPiIzracunaj",
            "Međunarodni promet",
            "Unutrašnji promet",
            "UpdatePanel",
            "ASPxTabControl1",
            "Kalkulator",
            "Prijem pošiljaka",
            "Izračunaj",
        ]

        for value in search_strings:
            count = main_html.lower().count(value.lower())

            print(
                f"{value!r:<45} -> {count}"
            )

        # --------------------------------------------------------
        # FRAME INFORMATION
        # --------------------------------------------------------

        section("IFRAMES")

        frames = page.frames

        print(f"Number of frames: {len(frames)}")

        for index, frame in enumerate(frames):

            print()
            print(f"FRAME {index}")
            print("-" * 70)

            print(f"URL: {frame.url}")

            try:
                frame_html = await frame.content()

                print(
                    f"HTML length: {len(frame_html):,}"
                )

            except Exception as exc:
                print(
                    f"Could not read frame HTML: {exc}"
                )

        # --------------------------------------------------------
        # FIND CALCULATOR FRAME
        # --------------------------------------------------------

        section("LOCATING CALCULATOR IFRAME")

        calculator_frame = None

        for index, frame in enumerate(page.frames):

            frame_url = frame.url or ""

            print(
                f"Checking frame {index}: {frame_url}"
            )

            if IFRAME_URL_PART.lower() in frame_url.lower():

                calculator_frame = frame

                print()
                print(
                    f"FOUND CALCULATOR FRAME: {index}"
                )
                print(
                    f"Calculator URL: {frame_url}"
                )

                break

        if calculator_frame is None:

            print()
            print(
                "ERROR: Calculator iframe was not found."
            )

            print()
            print("All frame URLs:")

            for index, frame in enumerate(page.frames):
                print(
                    f"{index}: {frame.url}"
                )

            await page.screenshot(
                path="diagnostic.png",
                full_page=True,
            )

            print(
                "Screenshot saved to diagnostic.png"
            )

            await browser.close()

            raise RuntimeError(
                "Calculator iframe not found."
            )

        # --------------------------------------------------------
        # WAIT FOR IFRAME
        # --------------------------------------------------------

        section("WAITING FOR CALCULATOR IFRAME")

        print(
            "Waiting for calculator document..."
        )

        try:

            await calculator_frame.wait_for_load_state(
                "domcontentloaded",
                timeout=30_000,
            )

        except Exception as exc:

            print(
                f"domcontentloaded wait ended with: {exc}"
            )

        # Allow ASP.NET / JavaScript initialization.
        await page.wait_for_timeout(8_000)

        # --------------------------------------------------------
        # GET IFRAME HTML
        # --------------------------------------------------------

        section("CALCULATOR IFRAME HTML")

        try:

            iframe_html = await calculator_frame.content()

        except Exception as exc:

            await browser.close()

            raise RuntimeError(
                f"Could not obtain calculator iframe HTML: {exc}"
            )

        print(
            f"Calculator iframe HTML length: "
            f"{len(iframe_html):,}"
        )

        save_text(
            "iframe.html",
            iframe_html,
        )

        # --------------------------------------------------------
        # SAVE IFRAME BODY TEXT
        # --------------------------------------------------------

        try:

            body_text = await calculator_frame.locator(
                "body"
            ).inner_text()

        except Exception as exc:

            body_text = (
                f"Could not obtain body text: {exc}"
            )

        save_text(
            "iframe.txt",
            body_text,
        )

        section("CALCULATOR IFRAME TEXT")

        print(
            clean_text(body_text)[:20_000]
        )

        # --------------------------------------------------------
        # SEARCH IFRAME HTML
        # --------------------------------------------------------

        section("SEARCHING CALCULATOR IFRAME HTML")

        for value in search_strings:

            count = iframe_html.lower().count(
                value.lower()
            )

            print(
                f"{value!r:<45} -> {count}"
            )

        # --------------------------------------------------------
        # EXPECTED SELECTORS
        # --------------------------------------------------------

        section("EXPECTED CALCULATOR CONTROLS")

        expected_selectors = [
            "#ddlMeDoOdrediste",
            "#chbMeDoAvionski",
            "#tbxMeDoAvioTezina",
            "#btnMeDoIzracunaj",
            "#btnMeObPiIzracunaj",
            "#btnMeDoIzracunaj",
            "input[type='submit']",
            "input[type='button']",
            "input[type='image']",
            "select",
            "input",
            "button",
        ]

        found_any_expected = False

        for selector in expected_selectors:

            try:

                count = await calculator_frame.locator(
                    selector
                ).count()

            except Exception as exc:

                print(
                    f"{selector:<40} -> ERROR: {exc}"
                )

                continue

            print(
                f"{selector:<40} -> {count}"
            )

            if count > 0:
                found_any_expected = True

        # --------------------------------------------------------
        # LIST SELECT ELEMENTS
        # --------------------------------------------------------

        section("SELECT ELEMENTS")

        select_count = await calculator_frame.locator(
            "select"
        ).count()

        print(
            f"Number of <select> elements: {select_count}"
        )

        for index in range(select_count):

            select = calculator_frame.locator(
                "select"
            ).nth(index)

            try:

                element_id = await select.get_attribute(
                    "id"
                )

                name = await select.get_attribute(
                    "name"
                )

                classes = await select.get_attribute(
                    "class"
                )

                options = await select.locator(
                    "option"
                ).count()

                print()
                print(
                    f"SELECT #{index}"
                )

                print(
                    f"  id      = {element_id}"
                )

                print(
                    f"  name    = {name}"
                )

                print(
                    f"  class   = {classes}"
                )

                print(
                    f"  options = {options}"
                )

                # Print first several options.
                for option_index in range(
                    min(options, 20)
                ):

                    option = select.locator(
                        "option"
                    ).nth(option_index)

                    option_text = clean_text(
                        await option.inner_text()
                    )

                    option_value = (
                        await option.get_attribute(
                            "value"
                        )
                    )

                    selected = (
                        await option.get_attribute(
                            "selected"
                        )
                    )

                    print(
                        f"    [{option_index}] "
                        f"value={option_value!r} "
                        f"selected={selected!r} "
                        f"text={option_text!r}"
                    )

                if options > 20:
                    print(
                        f"    ... "
                        f"{options - 20} more options"
                    )

            except Exception as exc:

                print(
                    f"  ERROR reading SELECT #{index}: "
                    f"{exc}"
                )

        # --------------------------------------------------------
        # LIST INPUT ELEMENTS
        # --------------------------------------------------------

        section("INPUT ELEMENTS")

        input_count = await calculator_frame.locator(
            "input"
        ).count()

        print(
            f"Number of <input> elements: {input_count}"
        )

        for index in range(input_count):

            element = calculator_frame.locator(
                "input"
            ).nth(index)

            try:

                element_type = (
                    await element.get_attribute(
                        "type"
                    )
                )

                element_id = (
                    await element.get_attribute(
                        "id"
                    )
                )

                name = (
                    await element.get_attribute(
                        "name"
                    )
                )

                value = (
                    await element.get_attribute(
                        "value"
                    )
                )

                title = (
                    await element.get_attribute(
                        "title"
                    )
                )

                classes = (
                    await element.get_attribute(
                        "class"
                    )
                )

                print(
                    f"[{index}] "
                    f"type={element_type!r} "
                    f"id={element_id!r} "
                    f"name={name!r} "
                    f"value={value!r} "
                    f"title={title!r} "
                    f"class={classes!r}"
                )

            except Exception as exc:

                print(
                    f"[{index}] ERROR: {exc}"
                )

        # --------------------------------------------------------
        # LIST BUTTON ELEMENTS
        # --------------------------------------------------------

        section("BUTTON ELEMENTS")

        button_count = await calculator_frame.locator(
            "button"
        ).count()

        print(
            f"Number of <button> elements: {button_count}"
        )

        for index in range(button_count):

            element = calculator_frame.locator(
                "button"
            ).nth(index)

            try:

                element_id = (
                    await element.get_attribute(
                        "id"
                    )
                )

                name = (
                    await element.get_attribute(
                        "name"
                    )
                )

                element_type = (
                    await element.get_attribute(
                        "type"
                    )
                )

                text = clean_text(
                    await element.inner_text()
                )

                print(
                    f"[{index}] "
                    f"type={element_type!r} "
                    f"id={element_id!r} "
                    f"name={name!r} "
                    f"text={text!r}"
                )

            except Exception as exc:

                print(
                    f"[{index}] ERROR: {exc}"
                )

        # --------------------------------------------------------
        # FORM ELEMENTS
        # --------------------------------------------------------

        section("FORMS")

        form_count = await calculator_frame.locator(
            "form"
        ).count()

        print(
            f"Number of <form> elements: {form_count}"
        )

        for index in range(form_count):

            form = calculator_frame.locator(
                "form"
            ).nth(index)

            try:

                form_id = await form.get_attribute(
                    "id"
                )

                form_name = await form.get_attribute(
                    "name"
                )

                action = await form.get_attribute(
                    "action"
                )

                method = await form.get_attribute(
                    "method"
                )

                print(
                    f"[{index}] "
                    f"id={form_id!r} "
                    f"name={form_name!r} "
                    f"method={method!r} "
                    f"action={action!r}"
                )

            except Exception as exc:

                print(
                    f"[{index}] ERROR: {exc}"
                )

        # --------------------------------------------------------
        # SEARCH FOR COUNTRY-LIKE OPTIONS
        # --------------------------------------------------------

        section("COUNTRY OPTION SEARCH")

        all_options = calculator_frame.locator(
            "option"
        )

        option_count = await all_options.count()

        print(
            f"Total <option> elements: {option_count}"
        )

        country_keywords = [
            "Afganistan",
            "Albanija",
            "Australija",
            "Austrija",
            "Bosna",
            "Hrvatska",
            "Njema",
            "Njemacka",
            "Srbija",
            "Slovenija",
            "Italija",
            "Francuska",
            "Njemačka",
            "SAD",
            "Velika Britanija",
        ]

        matches = []

        for index in range(option_count):

            option = all_options.nth(index)

            try:

                text = clean_text(
                    await option.inner_text()
                )

                value = (
                    await option.get_attribute(
                        "value"
                    )
                )

                for keyword in country_keywords:

                    if keyword.lower() in text.lower():

                        matches.append(
                            (
                                index,
                                value,
                                text,
                            )
                        )

                        break

            except Exception:
                continue

        if matches:

            print(
                "Country-like options found:"
            )

            for index, value, text in matches:

                print(
                    f"[{index}] "
                    f"value={value!r} "
                    f"text={text!r}"
                )

        else:

            print(
                "No country-like options found."
            )

        # --------------------------------------------------------
        # ERROR MESSAGE SEARCH
        # --------------------------------------------------------

        section("ERROR MESSAGE SEARCH")

        error_message = (
            "Prijem pošiljaka se trenutno ne vrši "
            "za odabranu državu"
        )

        body_lower = body_text.lower()

        if error_message.lower() in body_lower:

            print(
                "ERROR MESSAGE IS CURRENTLY PRESENT"
            )

        else:

            print(
                "ERROR MESSAGE IS NOT CURRENTLY PRESENT"
            )

        # --------------------------------------------------------
        # SCREENSHOT
        # --------------------------------------------------------

        section("SCREENSHOT")

        try:

            await page.screenshot(
                path="diagnostic.png",
                full_page=True,
            )

            print(
                "Screenshot saved to diagnostic.png"
            )

        except Exception as exc:

            print(
                f"Could not save screenshot: {exc}"
            )

        # --------------------------------------------------------
        # FINAL DIAGNOSTIC REPORT
        # --------------------------------------------------------

        section("FINAL DIAGNOSTIC SUMMARY")

        report_lines = [
            "JP BH POŠTA CALCULATOR IFRAME DIAGNOSTIC",
            "",
            f"Main URL: {URL}",
            f"Final URL: {page.url}",
            "",
            f"Main HTML length: {len(main_html):,}",
            f"Iframe HTML length: {len(iframe_html):,}",
            f"Number of frames: {len(page.frames)}",
            "",
            f"Calculator iframe URL:",
            calculator_frame.url,
            "",
            f"Select elements: {select_count}",
            f"Input elements: {input_count}",
            f"Button elements: {button_count}",
            f"Form elements: {form_count}",
            f"Option elements: {option_count}",
            "",
            "Expected selectors:",
        ]

        for selector in expected_selectors:

            try:

                count = await calculator_frame.locator(
                    selector
                ).count()

                report_lines.append(
                    f"{selector}: {count}"
                )

            except Exception as exc:

                report_lines.append(
                    f"{selector}: ERROR {exc}"
                )

        report_lines.extend(
            [
                "",
                "Error message present:",
                str(
                    error_message.lower()
                    in body_lower
                ),
            ]
        )

        save_text(
            "diagnostic.txt",
            "\n".join(report_lines),
        )

        # --------------------------------------------------------
        # IMPORTANT RESULT
        # --------------------------------------------------------

        if not found_any_expected:

            print()
            print("=" * 70)
            print("IMPORTANT")
            print("=" * 70)

            print(
                "The calculator iframe was found, but none of "
                "the expected controls were found."
            )

            print(
                "This means the embedded application may still "
                "be loading, redirecting, protected, or generating "
                "its controls dynamically."
            )

            print()
            print(
                "The following files contain the evidence:"
            )

            print(
                "  iframe.html"
            )

            print(
                "  iframe.txt"
            )

            print(
                "  diagnostic.txt"
            )

            print(
                "  diagnostic.png"
            )

        else:

            print()
            print("=" * 70)
            print("EXPECTED CONTROLS FOUND")
            print("=" * 70)

            print(
                "At least one expected calculator control "
                "was found inside the iframe."
            )

        await browser.close()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    asyncio.run(main())
