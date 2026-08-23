# monitor.py

import asyncio
import os
import sys
from pathlib import Path

from playwright.async_api import (
async_playwright,
TimeoutError as PlaywrightTimeoutError,
)

URL = os.getenv(
"CALCULATOR_URL",
"https://www.posta.ba/kalkulator-cijena/",
)

CALCULATOR_IFRAME_URL_PART = (
"bhpwebout.posta.ba/KalkulatorCijena_WEB_app"
)

OUTPUT_FILE = Path("posta-countries.txt")

NAVIGATION_TIMEOUT = 30_000
DEFAULT_TIMEOUT = 8_000
FRAME_WAIT_TIMEOUT = 30_000

# Give each country enough time for the ASP.NET postback

# caused by changing the country dropdown.

PER_COUNTRY_TIMEOUT = 12_000

BETWEEN_COUNTRIES_MS = 300

UNAVAILABLE_MESSAGE = (
"Prijem pošiljaka se trenutno ne vrši za odabranu državu"
)

def section(title):
print()
print("=" * 70)
print(title)
print("=" * 70)

def save_text(path, text):
try:
path.write_text(
text or "",
encoding="utf-8",
)

```
    print(
        f"Saved {path} "
        f"({len(text or ''):,} bytes)"
    )

except Exception as exc:
    print(
        f"Could not save {path}: {exc}"
    )
```

async def safe_page_content(page):
try:
return await page.content()
except Exception:
return ""

async def frame_content(frame):
try:
return await frame.content()
except Exception:
return ""

async def find_calculator_frame(page):
section("LOCATING CALCULATOR IFRAME")

```
for attempt in range(1, 31):

    frames = page.frames

    print(
        f"Frame search {attempt}/30 "
        f"({len(frames)} frames)"
    )

    for index, frame in enumerate(frames):

        frame_url = frame.url or ""

        print(
            f"Frame {index}: {frame_url}"
        )

        if (
            CALCULATOR_IFRAME_URL_PART.casefold()
            in frame_url.casefold()
        ):
            print()
            print(
                f"Calculator iframe found: frame {index}"
            )
            print(
                f"URL: {frame_url}"
            )

            return frame

    # HTML fallback.
    for index, frame in enumerate(frames):

        html = await frame_content(frame)

        if not html:
            continue

        markers = (
            "ASPxTabControl1_TC",
            "ASPxTabControl1_T1",
            "ddlMeDoOdrediste",
            "btnMeDoIzracunaj",
            "Međunarodni promet",
        )

        if any(
            marker in html
            for marker in markers
        ):
            print()
            print(
                "Calculator iframe found by HTML:"
                f" frame {index}"
            )

            print(
                f"URL: {frame.url}"
            )

            return frame

    if attempt < 30:
        await page.wait_for_timeout(1_000)

return None
```

async def select_international_tab(frame):
"""
Select the actual DevExpress tab.

```
The HTML supplied by the user shows:

    <li id="ASPxTabControl1_T1">
        <a id="ASPxTabControl1_T1T">
            <span class="dx-vam">
                Međunarodni promet
            </span>
        </a>
    </li>

Therefore we use the actual control instead of trying to
click generic text.
"""

section("SELECTING MEĐUNARODNI PROMET")

selectors = (
    "#ASPxTabControl1_T1T",
    "#ASPxTabControl1_T1 a",
    "#ASPxTabControl1_T1",
)

for selector in selectors:

    try:
        locator = frame.locator(selector)

        count = await locator.count()

        print(
            f"Selector {selector}: {count} match(es)"
        )

        if count == 0:
            continue

        element = locator.first

        try:
            print(
                "Visible:",
                await element.is_visible(),
            )
        except Exception:
            pass

        try:
            print(
                "Outer HTML:",
                (
                    await element.evaluate(
                        "(el) => el.outerHTML"
                    )
                )[:2000],
            )
        except Exception:
            pass

        # Normal Playwright click.
        try:
            await element.scroll_into_view_if_needed()

            await element.click(
                timeout=DEFAULT_TIMEOUT,
                force=True,
            )

            print(
                f"Clicked {selector}"
            )

            await frame.page.wait_for_timeout(
                1_500
            )

            return True

        except Exception as exc:

            print(
                f"Normal click failed for "
                f"{selector}: {exc}"
            )

        # JavaScript click fallback.
        try:

            await element.evaluate(
                """
                (el) => {
                    el.click();
                }
                """
            )

            print(
                f"JavaScript click succeeded "
                f"for {selector}"
            )

            await frame.page.wait_for_timeout(
                1_500
            )

            return True

        except Exception as exc:

            print(
                f"JavaScript click failed for "
                f"{selector}: {exc}"
            )

    except Exception as exc:

        print(
            f"Selector error for "
            f"{selector}: {exc}"
        )

# Final fallback: find the exact span supplied by the user
# and click the actual tab <li>.
try:

    span = frame.locator(
        "span.dx-vam",
    ).filter(
        has_text="Međunarodni promet",
    )

    count = await span.count()

    print(
        f"Exact international tab spans: {count}"
    )

    for i in range(count):

        candidate = span.nth(i)

        try:

            text = (
                await candidate.inner_text()
            ).strip()

            if text != "Međunarodni promet":
                continue

            parent_li = candidate.locator(
                "xpath=ancestor::li[1]"
            )

            if await parent_li.count() == 0:
                continue

            print(
                "Found actual international "
                "tab <li> through span."
            )

            print(
                (
                    await parent_li.evaluate(
                        "(el) => el.outerHTML"
                    )
                )[:3000]
            )

            try:

                await parent_li.click(
                    timeout=DEFAULT_TIMEOUT,
                    force=True,
                )

                print(
                    "Clicked actual international "
                    "tab <li>."
                )

                await frame.page.wait_for_timeout(
                    1_500
                )

                return True

            except Exception as exc:

                print(
                    f"Tab <li> click failed: {exc}"
                )

                try:

                    await parent_li.evaluate(
                        "(el) => el.click()"
                    )

                    print(
                        "JavaScript clicked "
                        "actual tab <li>."
                    )

                    await frame.page.wait_for_timeout(
                        1_500
                    )

                    return True

                except Exception as js_exc:

                    print(
                        "JavaScript tab click failed:"
                        f" {js_exc}"
                    )

        except Exception:
            continue

except Exception as exc:

    print(
        f"Span fallback failed: {exc}"
    )

return False
```

async def find_country_dropdown(frame):
"""
Actual selector supplied by the user:

```
    #ddlMeDoOdrediste

This is the authoritative selector.
"""

section("LOCATING COUNTRY DROPDOWN")

selector = "#ddlMeDoOdrediste"

try:

    dropdown = frame.locator(selector)

    count = await dropdown.count()

    print(
        f"{selector}: {count} match(es)"
    )

    if count == 0:
        return None

    dropdown = dropdown.first

    try:
        print(
            "Visible:",
            await dropdown.is_visible(),
        )
    except Exception:
        pass

    option_count = await dropdown.locator(
        "option"
    ).count()

    print(
        f"Country options: {option_count}"
    )

    if option_count == 0:
        return None

    return dropdown

except Exception as exc:

    print(
        f"Could not locate country dropdown: {exc}"
    )

    return None
```

async def wait_for_country_dropdown(
frame,
timeout_ms=FRAME_WAIT_TIMEOUT,
):

```
deadline = (
    asyncio.get_running_loop().time()
    + timeout_ms / 1000
)

while (
    asyncio.get_running_loop().time()
    < deadline
):

    dropdown = (
        await find_country_dropdown(frame)
    )

    if dropdown is not None:
        return dropdown

    await frame.page.wait_for_timeout(
        500
    )

return None
```

async def read_list_1(dropdown):
"""
LIST 1:

```
The actual contents of the country dropdown.

NOTHING is filtered out.

Original order is preserved.

The visible option text is written exactly as supplied
by the website, after only removing surrounding whitespace.
"""

section("READING LIST 1")

options = dropdown.locator("option")

count = await options.count()

print(
    f"Dropdown option count: {count}"
)

countries = []

for index in range(count):

    option = options.nth(index)

    try:

        name = (
            await option.inner_text()
        ).strip()

        value = (
            await option.get_attribute(
                "value"
            )
        )

        if not name:
            name = ""

        country = {
            "index": index,
            "name": name,
            "value": value or "",
        }

        countries.append(country)

        print(
            f"[{index:03d}] "
            f"{name} "
            f"(value={value or ''})"
        )

    except Exception as exc:

        print(
            f"Could not read option "
            f"{index}: {exc}"
        )

print()
print(
    f"LIST 1 OPTIONS READ: {len(countries)}"
)

return countries
```

async def get_body_text(frame):
try:

```
    return await frame.locator(
        "body"
    ).inner_text(
        timeout=5_000
    )

except Exception:
    return ""
```

async def get_exact_unavailable_message_count(
frame,
):
try:

```
    body = await get_body_text(frame)

    return body.count(
        UNAVAILABLE_MESSAGE
    )

except Exception:
    return 0
```

async def select_weight(frame):
"""
The actual weight field supplied by the user is:

```
    #tbxMeDoAvioTezina

Set it to the existing default value, which is 10 grams.
"""

selector = "#tbxMeDoAvioTezina"

try:

    weight = frame.locator(selector)

    if await weight.count() == 0:
        print(
            "Weight field not found."
        )
        return False

    weight = weight.first

    current = (
        await weight.input_value()
    )

    print(
        f"Weight field current value: {current}"
    )

    # Keep the website's existing value if present.
    # If empty, use 10 grams.
    if not current.strip():

        await weight.fill("10")

        print(
            "Weight field set to 10 grams."
        )

    return True

except Exception as exc:

    print(
        f"Could not prepare weight field: {exc}"
    )

    return False
```

async def click_calculate(frame):
"""
Actual button supplied by the user:

```
    #btnMeDoIzracunaj
"""

selector = "#btnMeDoIzracunaj"

try:

    button = frame.locator(selector)

    count = await button.count()

    print(
        f"Calculate button matches: {count}"
    )

    if count == 0:
        return False

    button = button.first

    print(
        "Calculate button:",
        await button.get_attribute("value"),
    )

    await button.scroll_into_view_if_needed()

    try:

        await button.click(
            timeout=DEFAULT_TIMEOUT,
            force=True,
        )

        print(
            "Clicked Izračunaj."
        )

        return True

    except Exception as exc:

        print(
            f"Normal calculate click failed: "
            f"{exc}"
        )

        try:

            await button.evaluate(
                "(el) => el.click()"
            )

            print(
                "JavaScript clicked Izračunaj."
            )

            return True

        except Exception as js_exc:

            print(
                "JavaScript calculate click "
                f"failed: {js_exc}"
            )

            return False

except Exception as exc:

    print(
        f"Could not find/click calculate "
        f"button: {exc}"
    )

    return False
```

async def wait_for_postback_result(
frame,
before_text,
timeout_ms=PER_COUNTRY_TIMEOUT,
):
"""
ASP.NET WebForms may update the page asynchronously.

```
We wait for either:
  - the exact unavailable message, or
  - a meaningful change to the body.

The exact unavailable message is the ONLY thing that places
a country into List 2.
"""

deadline = (
    asyncio.get_running_loop().time()
    + timeout_ms / 1000
)

last_text = before_text

while (
    asyncio.get_running_loop().time()
    < deadline
):

    await frame.page.wait_for_timeout(
        350
    )

    last_text = await get_body_text(
        frame
    )

    if (
        UNAVAILABLE_MESSAGE
        in last_text
    ):
        return (
            "UNAVAILABLE",
            last_text,
        )

    # Any meaningful body change is enough to stop waiting.
    if last_text != before_text:
        return (
            "CHANGED",
            last_text,
        )

return (
    "TIMEOUT",
    last_text,
)
```

async def test_country(
frame,
dropdown,
country,
):
"""
Test one country.

```
LIST 2 is populated ONLY when the exact requested message
appears after Izračunaj is clicked.
"""

name = country["name"]
value = country["value"]

print()
print(
    f"Testing: {name}"
)

print(
    f"Value: {value}"
)

try:

    # ------------------------------------------------------------
    # Select country.
    # ------------------------------------------------------------

    if value:

        print(
            f"Selecting value={value}"
        )

        await dropdown.select_option(
            value=value
        )

    else:

        print(
            f"Selecting label={name}"
        )

        await dropdown.select_option(
            label=name
        )

    # The dropdown has onchange=__doPostBack(...)
    # so selecting it causes the ASP.NET page to update.
    await frame.page.wait_for_timeout(
        600
    )

    # ------------------------------------------------------------
    # Make sure the weight is present.
    # ------------------------------------------------------------

    await select_weight(frame)

    # ------------------------------------------------------------
    # Record the current page before clicking.
    # ------------------------------------------------------------

    before_text = await get_body_text(
        frame
    )

    before_message_count = (
        before_text.count(
            UNAVAILABLE_MESSAGE
        )
    )

    print(
        "Unavailable message count "
        f"before click: {before_message_count}"
    )

    # ------------------------------------------------------------
    # Click Izračunaj.
    # ------------------------------------------------------------

    clicked = await click_calculate(
        frame
    )

    if not clicked:

        return {
            "name": name,
            "value": value,
            "unavailable": False,
            "reason": "Could not click Izračunaj",
        }

    # ------------------------------------------------------------
    # Wait for result.
    # ------------------------------------------------------------

    result_type, result_text = (
        await wait_for_postback_result(
            frame,
            before_text,
        )
    )

    # ------------------------------------------------------------
    # EXACT TEST FOR LIST 2.
    # ------------------------------------------------------------

    if (
        UNAVAILABLE_MESSAGE
        in result_text
    ):

        print(
            ">>> EXACT UNAVAILABLE MESSAGE FOUND"
        )

        print(
            f">>> ADDING TO LIST 2: {name}"
        )

        return {
            "name": name,
            "value": value,
            "unavailable": True,
            "reason": (
                UNAVAILABLE_MESSAGE
            ),
        }

    print(
        f"No unavailable message for {name}."
    )

    print(
        f"Result state: {result_type}"
    )

    return {
        "name": name,
        "value": value,
        "unavailable": False,
        "reason": result_type,
    }

except Exception as exc:

    print(
        f"ERROR testing {name}: {exc}"
    )

    return {
        "name": name,
        "value": value,
        "unavailable": False,
        "reason": (
            f"Exception: {type(exc).__name__}: "
            f"{exc}"
        ),
    }
```

def write_output(
list_1,
list_2,
status="COMPLETE",
):
"""
Create posta-countries.txt.

```
LIST 1:
    Exact dropdown contents, original order.

LIST 2:
    Only countries for which the exact unavailable message
    appeared after Izračunaj was clicked.
"""

lines = []

lines.append(
    "JP BH POŠTA COUNTRY MONITOR"
)

lines.append(
    "=" * 70
)

lines.append(
    f"STATUS: {status}"
)

lines.append("")

lines.append(
    "LIST 1"
)

lines.append(
    "Original country dropdown contents"
)

lines.append(
    "-" * 70
)

# IMPORTANT:
# No filtering, deduplication, sorting, or removal.
for country in list_1:

    lines.append(
        country["name"]
    )

lines.append("")

lines.append(
    "LIST 2"
)

lines.append(
    "Countries showing:"
)

lines.append(
    UNAVAILABLE_MESSAGE
)

lines.append(
    "-" * 70
)

for country in list_2:

    lines.append(
        country["name"]
    )

lines.append("")

save_text(
    OUTPUT_FILE,
    "\n".join(lines) + "\n",
)
```

async def create_diagnostics(
page,
frame,
error,
):
section("CREATING DIAGNOSTICS")

```
try:

    save_text(
        Path("page.html"),
        await safe_page_content(page),
    )

except Exception:
    pass

try:

    if frame is not None:

        save_text(
            Path("iframe.html"),
            await frame_content(frame),
        )

        save_text(
            Path("iframe.txt"),
            await get_body_text(frame),
        )

except Exception:
    pass

try:

    save_text(
        Path("diagnostic.txt"),
        (
            "JP BH POŠTA MONITOR DIAGNOSTIC\n\n"
            f"URL: {URL}\n"
            f"PAGE URL: {page.url}\n"
            f"FRAME COUNT: {len(page.frames)}\n\n"
            f"ERROR: {type(error).__name__}: "
            f"{error}\n"
        ),
    )

except Exception:
    pass

try:

    await page.screenshot(
        path="diagnostic.png",
        full_page=True,
    )

    print(
        "Saved diagnostic.png"
    )

except Exception as exc:

    print(
        f"Could not save screenshot: {exc}"
    )
```

async def main():

```
section(
    "JP BH POŠTA COUNTRY MONITOR"
)

print(
    f"URL: {URL}"
)

print(
    f"Output: {OUTPUT_FILE}"
)

# ------------------------------------------------------------
# ALWAYS CREATE THE OUTPUT FILE FIRST.
# ------------------------------------------------------------

write_output(
    [],
    [],
    status="STARTING",
)

async with async_playwright() as playwright:

    browser = await playwright.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
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
        DEFAULT_TIMEOUT
    )

    page.set_default_navigation_timeout(
        NAVIGATION_TIMEOUT
    )

    frame = None

    try:

        # ========================================================
        # OPEN MAIN PAGE
        # ========================================================

        section("OPENING CALCULATOR PAGE")

        try:

            response = await page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=NAVIGATION_TIMEOUT,
            )

            if response is not None:

                try:

                    print(
                        f"HTTP status: "
                        f"{response.status}"
                    )

                except Exception:
                    pass

        except PlaywrightTimeoutError as exc:

            print(
                "WARNING: navigation timed out."
            )

            print(
                "Continuing because the page may "
                "already be usable."
            )

            print(
                str(exc)
            )

        print(
            f"Final page URL: {page.url}"
        )

        await page.wait_for_timeout(
            2_000
        )

        # ========================================================
        # FIND IFRAME
        # ========================================================

        frame = await find_calculator_frame(
            page
        )

        if frame is None:

            raise RuntimeError(
                "Could not locate calculator iframe."
            )

        print()
        print(
            f"Calculator frame URL: {frame.url}"
        )

        # ========================================================
        # SELECT INTERNATIONAL TAB
        # ========================================================

        activated = (
            await select_international_tab(
                frame
            )
        )

        if not activated:

            raise RuntimeError(
                "Could not select "
                "Međunarodni promet."
            )

        # ========================================================
        # FIND COUNTRY DROPDOWN
        # ========================================================

        section(
            "WAITING FOR INTERNATIONAL CALCULATOR"
        )

        dropdown = (
            await wait_for_country_dropdown(
                frame,
                FRAME_WAIT_TIMEOUT,
            )
        )

        if dropdown is None:

            raise RuntimeError(
                "International calculator was selected, "
                "but #ddlMeDoOdrediste was not found."
            )

        print()
        print(
            "International country dropdown found."
        )

        # ========================================================
        # LIST 1
        # ========================================================

        list_1 = await read_list_1(
            dropdown
        )

        if not list_1:

            raise RuntimeError(
                "Country dropdown is empty."
            )

        # Write List 1 immediately.
        # This means the file exists even if testing later fails.
        write_output(
            list_1,
            [],
            status="LIST_1_READ",
        )

        # ========================================================
        # TEST COUNTRIES
        # ========================================================

        section(
            "TESTING COUNTRIES FOR LIST 2"
        )

        list_2 = []

        for index, country in enumerate(
            list_1,
            1,
        ):

            print()
            print(
                "=" * 70
            )

            print(
                f"COUNTRY {index}"
            )

            print(
                "=" * 70
            )

            result = await test_country(
                frame,
                dropdown,
                country,
            )

            if result["unavailable"]:

                list_2.append(
                    country
                )

            # ----------------------------------------------------
            # Save after EVERY country.
            # ----------------------------------------------------

            write_output(
                list_1,
                list_2,
                status="RUNNING",
            )

            await page.wait_for_timeout(
                BETWEEN_COUNTRIES_MS
            )

        # ========================================================
        # FINAL OUTPUT
        # ========================================================

        write_output(
            list_1,
            list_2,
            status="COMPLETE",
        )

        section("MONITOR COMPLETE")

        print(
            f"Output file created: "
            f"{OUTPUT_FILE}"
        )

        print()
        print(
            "LIST 1:"
        )

        for country in list_1:

            print(
                country["name"]
            )

        print()
        print(
            "LIST 2:"
        )

        for country in list_2:

            print(
                country["name"]
            )

        print()
        print(
            "The monitor completed successfully."
        )

    except Exception as exc:

        section("MONITOR FAILED")

        print(
            f"{type(exc).__name__}: {exc}"
        )

        # Preserve whatever List 1/List 2 data we have.
        try:

            # If list_1 exists in local scope, preserve it.
            existing_list_1 = locals().get(
                "list_1",
                [],
            )

            existing_list_2 = locals().get(
                "list_2",
                [],
            )

            write_output(
                existing_list_1,
                existing_list_2,
                status="FAILED",
            )

        except Exception as output_error:

            print(
                "Could not preserve output:"
                f" {output_error}"
            )

        try:

            await create_diagnostics(
                page,
                frame,
                exc,
            )

        except Exception as diagnostic_error:

            print(
                "Diagnostic creation failed:"
                f" {diagnostic_error}"
            )

        raise

    finally:

        try:
            await context.close()
        except Exception:
            pass

        try:
            await browser.close()
        except Exception:
            pass
```

if **name** == "**main**":

```
try:

    asyncio.run(
        main()
    )

except KeyboardInterrupt:

    print(
        "Interrupted."
    )

    sys.exit(130)
