import asyncio
import os
from pathlib import Path

from playwright.async_api import async_playwright


URL = os.environ.get(
    "CALCULATOR_URL",
    "https://www.posta.ba/kalkulator-cijena/"
)


def section(title):
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


async def main():
    section("JP BH POŠTA CALCULATOR DIAGNOSTIC 2")

    print(f"URL: {URL}")

    if not URL:
        raise RuntimeError("CALCULATOR_URL is empty")

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True
        )

        context = await browser.new_context(
            viewport={"width": 1440, "height": 1200},
            locale="hr-HR",
        )

        page = await context.new_page()

        # Capture browser console messages.
        page.on(
            "console",
            lambda msg: print(
                f"[CONSOLE {msg.type}] {msg.text}"
            )
        )

        # Capture page errors.
        page.on(
            "pageerror",
            lambda exc: print(
                f"[PAGE ERROR] {exc}"
            )
        )

        # Capture requests/responses involving interesting resources.
        async def response_handler(response):
            url = response.url.lower()

            interesting = (
                "default.aspx" in url
                or "dxr.axd" in url
                or "post" in url
            )

            if interesting:
                print(
                    f"[RESPONSE] {response.status} {response.url}"
                )

        page.on("response", response_handler)

        section("OPENING PAGE")

        response = await page.goto(
            URL,
            wait_until="domcontentloaded",
            timeout=60000,
        )

        print(
            f"HTTP status: "
            f"{response.status if response else 'unknown'}"
        )

        print(f"Final URL: {page.url}")
        print(f"Page title: {await page.title()}")

        section("WAITING FOR JAVASCRIPT")

        await page.wait_for_timeout(5000)

        print("Waited 5 seconds.")

        # Try network idle, but don't fail if the site keeps connections open.
        try:
            await page.wait_for_load_state(
                "networkidle",
                timeout=30000,
            )
            print("Network became idle.")
        except Exception as e:
            print(
                "Network did not become idle within timeout:"
            )
            print(e)

        await page.wait_for_timeout(5000)

        print("Waited another 5 seconds.")

        section("PAGE INFORMATION")

        print(f"URL: {page.url}")
        print(f"Title: {await page.title()}")

        print(
            "Body exists:",
            await page.locator("body").count()
        )

        body_text = await page.locator("body").inner_text()

        print(
            f"Body text length: {len(body_text)}"
        )

        print()
        print("FIRST 10000 CHARACTERS OF BODY TEXT")
        print("-" * 70)
        print(body_text[:10000])

        section("RAW HTML")

        html = await page.content()

        print(
            f"HTML length: {len(html)}"
        )

        Path("page.html").write_text(
            html,
            encoding="utf-8",
        )

        print("Saved page.html")

        section("SEARCHING RAW HTML")

        searches = [
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

        for text in searches:
            count = html.count(text)

            print(
                f"{text!r:<45} -> {count}"
            )

        section("IFRAMES")

        frames = page.frames

        print(
            f"Number of frames: {len(frames)}"
        )

        for i, frame in enumerate(frames):
            print()
            print(f"FRAME {i}")
            print(f"URL: {frame.url}")

            try:
                frame_html = await frame.content()

                print(
                    f"HTML length: {len(frame_html)}"
                )

                for text in searches:
                    count = frame_html.count(text)

                    if count:
                        print(
                            f"  {text!r}: {count}"
                        )

            except Exception as e:
                print(
                    f"Could not inspect frame: {e}"
                )

        section("FORMS")

        forms = page.locator("form")

        form_count = await forms.count()

        print(
            f"Forms found: {form_count}"
        )

        for i in range(form_count):
            form = forms.nth(i)

            print()
            print(f"FORM {i}")

            try:
                print(
                    "id:",
                    await form.get_attribute("id")
                )

                print(
                    "action:",
                    await form.get_attribute("action")
                )

                print(
                    "method:",
                    await form.get_attribute("method")
                )

            except Exception as e:
                print(e)

        section("EXPECTED CONTROLS")

        selectors = [
            "#ddlMeDoOdrediste",
            "#chbMeDoAvionski",
            "#tbxMeDoAvioTezina",
            "#btnMeDoIzracunaj",
            "#btnMeObPiIzracunaj",
            "input[type='submit']",
            "input[type='button']",
            "input[type='image']",
        ]

        for selector in selectors:

            try:
                count = await page.locator(selector).count()

                print(
                    f"{selector:<40} -> {count}"
                )

            except Exception as e:
                print(
                    f"{selector:<40} -> ERROR {e}"
                )

        section("ALL SELECT ELEMENTS")

        selects = page.locator("select")

        select_count = await selects.count()

        print(
            f"Select elements: {select_count}"
        )

        for i in range(select_count):

            select = selects.nth(i)

            print()
            print(f"SELECT {i}")

            try:
                print(
                    "id:",
                    await select.get_attribute("id")
                )

                print(
                    "name:",
                    await select.get_attribute("name")
                )

                print(
                    "options:",
                    await select.locator("option").count()
                )

            except Exception as e:
                print(e)

        section("BUTTONS / INPUTS")

        inputs = page.locator("input")

        input_count = await inputs.count()

        print(
            f"Input elements: {input_count}"
        )

        for i in range(min(input_count, 200)):

            element = inputs.nth(i)

            try:
                tag = await element.evaluate(
                    "(el) => el.tagName"
                )

                element_id = await element.get_attribute("id")
                name = await element.get_attribute("name")
                input_type = await element.get_attribute("type")
                value = await element.get_attribute("value")

                print(
                    f"{i:3d}: "
                    f"tag={tag} "
                    f"type={input_type!r} "
                    f"id={element_id!r} "
                    f"name={name!r} "
                    f"value={value!r}"
                )

            except Exception as e:
                print(
                    f"{i:3d}: ERROR {e}"
                )

        section("SCREENSHOT")

        await page.screenshot(
            path="diagnostic.png",
            full_page=True,
        )

        print(
            "Saved diagnostic.png"
        )

        section("FINAL STATUS")

        if "ddlMeDoOdrediste" in html:
            print(
                "SUCCESS: ddlMeDoOdrediste exists in raw HTML."
            )
            print(
                "The problem is likely DOM/rendering/timing."
            )
        else:
            print(
                "ddlMeDoOdrediste is NOT present in raw HTML."
            )
            print(
                "The server response received by GitHub Actions "
                "differs from the HTML you supplied."
            )

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
