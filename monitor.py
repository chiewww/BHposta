import asyncio
import os
from pathlib import Path

from playwright.async_api import async_playwright

URL = os.getenv(
"CALCULATOR_URL",
"https://www.posta.ba/kalkulator-cijena/",
)

OUTPUT = Path("posta-countries.txt")

COUNTRY_SELECTOR = "#ddlMeDoOdrediste"
INTERNATIONAL_TAB = "#ASPxTabControl1_T1T"
WEIGHT_SELECTOR = "#tbxMeDoAvioTezina"
CALCULATE_SELECTOR = "#btnMeDoIzracunaj"

MESSAGE = (
"Prijem pošiljaka se trenutno ne vrši za odabranu državu"
)

def write_output(list1, list2, status):
lines = []

```
lines.append("JP BH POŠTA COUNTRY MONITOR")
lines.append("=" * 70)
lines.append("STATUS: " + status)
lines.append("")

lines.append("LIST 1")
lines.append("Actual country dropdown contents")
lines.append("-" * 70)

for country in list1:
    lines.append(country["name"])

lines.append("")
lines.append("LIST 2")
lines.append(MESSAGE)
lines.append("-" * 70)

for country in list2:
    lines.append(country["name"])

lines.append("")

OUTPUT.write_text(
    "\n".join(lines),
    encoding="utf-8",
)
```

async def get_body_text(frame):
try:
return await frame.locator("body").inner_text()
except Exception:
return ""

async def find_calculator_frame(page):
print("Locating calculator iframe...")

```
for attempt in range(30):
    frames = page.frames

    print(
        f"Frame search {attempt + 1}/30 "
        f"({len(frames)} frames)"
    )

    for index, frame in enumerate(frames):
        url = frame.url or ""

        if "KalkulatorCijena_WEB_app" in url:
            print(
                f"Calculator iframe found: frame {index}"
            )
            print(
                f"URL: {url}"
            )
            return frame

    for index, frame in enumerate(frames):
        try:
            html = await frame.content()
        except Exception:
            continue

        if (
            "ddlMeDoOdrediste" in html
            and "btnMeDoIzracunaj" in html
        ):
            print(
                f"Calculator iframe found by HTML: frame {index}"
            )
            print(
                f"URL: {frame.url}"
            )
            return frame

    await page.wait_for_timeout(1000)

return None
```

async def select_international(frame):
print("Selecting Međunarodni promet...")

```
selector = INTERNATIONAL_TAB

try:
    locator = frame.locator(selector)

    count = await locator.count()

    print(
        f"{selector} matches: {count}"
    )

    if count == 0:
        print(
            "International tab selector was not found."
        )
        return False

    element = locator.first

    print(
        "International tab HTML:"
    )

    try:
        print(
            await element.evaluate(
                "(el) => el.outerHTML"
            )
        )
    except Exception:
        pass

    try:
        await element.click(
            force=True,
            timeout=10000,
        )

        print(
            "Clicked #ASPxTabControl1_T1T."
        )

        await frame.page.wait_for_timeout(2000)

        return True

    except Exception as exc:
        print(
            "Normal click failed:"
        )
        print(exc)

    try:
        await element.evaluate(
            "(el) => el.click()"
        )

        print(
            "JavaScript click succeeded."
        )

        await frame.page.wait_for_timeout(2000)

        return True

    except Exception as exc:
        print(
            "JavaScript click failed:"
        )
        print(exc)

except Exception as exc:
    print(
        "Could not select international tab:"
    )
    print(exc)

return False
```

async def get_country_dropdown(frame):
print("Locating country dropdown...")

```
for attempt in range(30):
    try:
        locator = frame.locator(
            COUNTRY_SELECTOR
        )

        count = await locator.count()

        if count:
            options = locator.locator("option")
            option_count = await options.count()

            print(
                f"Country dropdown found."
            )
            print(
                f"Options: {option_count}"
            )

            return locator.first

    except Exception:
        pass

    print(
        f"Waiting for country dropdown "
        f"{attempt + 1}/30..."
    )

    await frame.page.wait_for_timeout(1000)

return None
```

async def read_list1(dropdown):
print("")
print("=" * 70)
print("READING LIST 1")
print("=" * 70)

```
options = dropdown.locator("option")
count = await options.count()

countries = []

for index in range(count):
    option = options.nth(index)

    name = (
        await option.inner_text()
    ).strip()

    value = (
        await option.get_attribute("value")
    )

    country = {
        "name": name,
        "value": value or "",
    }

    countries.append(country)

    print(
        f"[{index}] {name}"
    )

print(
    f"LIST 1 contains {len(countries)} countries."
)

return countries
```

async def select_country(
dropdown,
country,
):
value = country["value"]
name = country["name"]

```
if value:
    await dropdown.select_option(
        value=value
    )
else:
    await dropdown.select_option(
        label=name
    )

await dropdown.page.wait_for_timeout(1200)
```

async def click_calculate(frame):
print(
"Clicking Izračunaj..."
)

```
button = frame.locator(
    CALCULATE_SELECTOR
)

count = await button.count()

print(
    f"Calculate button matches: {count}"
)

if count == 0:
    return False

button = button.first

try:
    await button.click(
        force=True,
        timeout=10000,
    )

    print(
        "Izračunaj clicked."
    )

    return True

except Exception as exc:
    print(
        "Normal click failed:"
    )
    print(exc)

try:
    await button.evaluate(
        "(el) => el.click()"
    )

    print(
        "JavaScript click succeeded."
    )

    return True

except Exception as exc:
    print(
        "JavaScript click failed:"
    )
    print(exc)

return False
```

async def check_message(frame):
for _ in range(30):
text = await get_body_text(frame)

```
    if MESSAGE in text:
        return True

    await frame.page.wait_for_timeout(300)

return False
```

async def test_country(
frame,
dropdown,
country,
):
name = country["name"]

```
print("")
print(
    "Testing: " + name
)

try:
    await select_country(
        dropdown,
        country,
    )

    weight = frame.locator(
        WEIGHT_SELECTOR
    )

    if await weight.count():
        try:
            await weight.fill("10")
        except Exception:
            pass

    clicked = await click_calculate(
        frame
    )

    if not clicked:
        print(
            "Could not click Izračunaj."
        )
        return False

    found = await check_message(
        frame
    )

    if found:
        print(
            "MESSAGE FOUND:"
        )
        print(
            MESSAGE
        )
        print(
            "LIST 2 ADD: " + name
        )
        return True

    print(
        "Message not found."
    )

    return False

except Exception as exc:
    print(
        "Country test failed:"
    )
    print(exc)
    return False
```

async def main():
print("=" * 70)
print("JP BH POŠTA COUNTRY MONITOR")
print("=" * 70)
print(
"URL: " + URL
)
print(
"Output: " + str(OUTPUT)
)

```
write_output(
    [],
    [],
    "STARTING",
)

async with async_playwright() as p:
    browser = await p.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ],
    )

    context = await browser.new_context(
        viewport={
            "width": 1440,
            "height": 1200,
        },
        locale="hr-HR",
    )

    page = await context.new_page()

    page.set_default_timeout(
        10000
    )

    try:
        print(
            "Opening calculator page..."
        )

        await page.goto(
            URL,
            wait_until="domcontentloaded",
            timeout=30000,
        )

        await page.wait_for_timeout(3000)

        frame = await find_calculator_frame(
            page
        )

        if frame is None:
            raise RuntimeError(
                "Calculator iframe not found."
            )

        print(
            "Calculator frame URL: "
            + frame.url
        )

        selected = await select_international(
            frame
        )

        if not selected:
            raise RuntimeError(
                "Could not select Međunarodni promet."
            )

        dropdown = await get_country_dropdown(
            frame
        )

        if dropdown is None:
            raise RuntimeError(
                "Could not find "
                + COUNTRY_SELECTOR
            )

        list1 = await read_list1(
            dropdown
        )

        if not list1:
            raise RuntimeError(
                "Country dropdown is empty."
            )

        list2 = []

        write_output(
            list1,
            list2,
            "TESTING",
        )

        print("")
        print("=" * 70)
        print("TESTING LIST 2")
        print("=" * 70)

        for index, country in enumerate(
            list1,
            1,
        ):
            print("")
            print(
                f"COUNTRY {index}/{len(list1)}"
            )

            found = await test_country(
                frame,
                dropdown,
                country,
            )

            if found:
                list2.append(
                    country
                )

            write_output(
                list1,
                list2,
                "TESTING",
            )

        write_output(
            list1,
            list2,
            "COMPLETE",
        )

        print("")
        print("=" * 70)
        print("MONITOR COMPLETE")
        print("=" * 70)

        print(
            f"List 1: {len(list1)} countries"
        )

        print(
            f"List 2: {len(list2)} countries"
        )

        print("")
        print(
            "LIST 2:"
        )

        for country in list2:
            print(
                country["name"]
            )

    except Exception as exc:
        print("")
        print("=" * 70)
        print("MONITOR FAILED")
        print("=" * 70)
        print(
            type(exc).__name__
            + ": "
            + str(exc)
        )

        try:
            Path("diagnostic.html").write_text(
                await page.content(),
                encoding="utf-8",
            )
        except Exception:
            pass

        try:
            if frame is not None:
                Path("iframe.html").write_text(
                    await frame.content(),
                    encoding="utf-8",
                )

                Path("iframe.txt").write_text(
                    await get_body_text(frame),
                    encoding="utf-8",
                )
        except Exception:
            pass

        try:
            await page.screenshot(
                path="diagnostic.png",
                full_page=True,
            )
        except Exception:
            pass

        raise

    finally:
        await context.close()
        await browser.close()
```

if **name** == "**main**":
asyncio.run(main())
