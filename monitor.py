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
print(
f"Saved {path} "
f"({len(text or ''):,} bytes)"
)
except Exception as exc:
print(
f"Could not save {path}: {exc}"
)

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

        if (
            CALCULATOR_IFRAME_URL_PART.casefold()
            in frame_url.casefold()
        ):
            print(
                f"Calculator iframe found: frame {index}"
            )
            print(
                f"URL: {frame_url}"
            )
            return frame

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
The actual HTML supplied by the user contains:

```
    <li id="ASPxTabControl1_T1">
        <a id="ASPxTabControl1_T1T">
            <span class="dx-vam">
                Međunarodni promet
            </span>
        </a>
    </li>

Use the actual DevExpress tab IDs.
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
            f"Selector {selector}: "
            f"{count} match(es)"
        )

        if count == 0:
            continue

        element = locator.first

        try:
            print(
                "HTML:",
                (
                    await element.evaluate(
                        "(el) => el.outerHTML"
                    )
                )[:2000],
            )
        except Exception:
            pass

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

        try:
            await element.evaluate(
                "(el) => el.click()"
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

# Fallback using the exact span.
try:
    spans = frame.locator(
        "span.dx-vam"
    )

    count = await spans.count()

    print(
        f"dx-vam spans found: {count}"
    )

    for i in range(count):
        span = spans.nth(i)

        try:
            text = (
                await span.inner_text()
            ).strip()

            if text != "Međunarodni promet":
                continue

            parent_li = span.locator(
                "xpath=ancestor::li[1]"
            )

            if await parent_li.count() == 0:
                continue

            print(
                "Found exact international "
                "tab through span."
            )

            try:
                await parent_li.click(
                    timeout=DEFAULT_TIMEOUT,
                    force=True,
                )

                print(
                    "Clicked international tab "
                    "parent <li>."
                )

                await frame.page.wait_for_timeout(
                    1_500
                )

                return True

            except Exception as exc:
                print(
                    f"Parent <li> click failed: "
                    f"{exc}"
                )

            try:
                await parent_li.evaluate(
                    "(el) => el.click()"
                )

                print(
                    "JavaScript clicked "
                    "international tab <li>."
                )

                await frame.page.wait_for_timeout(
                    1_500
                )

                return True

            except Exception as exc:
                print(
                    f"JavaScript parent click "
                    f"failed: {exc}"
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
        f"Could not locate country dropdown: "
        f"{exc}"
    )
    return None
```

async def wait_for_country_dropdown(
frame,
timeout_ms=FRAME_WAIT_TIMEOUT,
):
deadline = (
asyncio.get_running_loop().time()
+ timeout_ms / 1000
)

```
while (
    asyncio.get_running_loop().time()
    < deadline
):
    dropdown = await find_country_dropdown(
        frame
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
LIST 1 is the actual dropdown contents.

```
Nothing is filtered.
Nothing is deduplicated.
Nothing is sorted.

Original website order is preserved.
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

        countries.append(
            {
                "index": index,
                "name": name,
                "value": value or "",
            }
        )

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

print(
    f"LIST 1 OPTIONS READ: "
    f"{len(countries)}"
)

return countries
```

async def get_body_text(frame):
try:
return await frame.locator(
"body"
).inner_text(
timeout=5_000
)
except Exception:
return ""

async def select_weight(frame):
"""
Actual weight field:

```
    #tbxMeDoAvioTezina

The supplied HTML shows value="10".
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

    current = await weight.input_value()

    print(
        f"Weight field value: {current}"
    )

    if not current.strip():
        await weight.fill("10")

        print(
            "Weight field set to 10 grams."
        )

    return True

except Exception as exc:
    print(
        f"Could not prepare weight field: "
        f"{exc}"
    )
    return False
```

async def click_calculate(frame):
"""
Actual calculate button:

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

    try:
        print(
            "Calculate button value:",
            await button.get_attribute(
                "value"
            ),
        )
    except Exception:
        pass

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

    except Exception as exc:
        print(
            f"JavaScript calculate click "
            f"failed: {exc}"
        )

        return False

except Exception as exc:
    print(
        f"Could not find/click calculate "
        f"button: {exc}"
    )
    return False
```

async def wait_for_unavailable_message(
frame,
timeout_ms=PER_COUNTRY_TIMEOUT,
):
"""
Wait specifically for the exact unavailable message.

```
The message is the ONLY criterion for List 2.
"""

deadline = (
    asyncio.get_running_loop().time()
    + timeout_ms / 1000
)

while (
    asyncio.get_running_loop().time()
    < deadline
):
    text = await get_body_text(frame)

    if UNAVAILABLE_MESSAGE in text:
        return True

    await frame.page.wait_for_timeout(
        350
    )

return False
```

async def test_country(
frame,
dropdown,
country,
):
"""
Test one country.

```
A country enters List 2 ONLY if the exact requested
message appears after Izračunaj is clicked.
"""

name = country["name"]
value = country["value"]

print()
print(
    f"TESTING: {name}"
)

try:
    # Select country.
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

    # The select has:
    #
    # onchange="javascript:setTimeout(
    # '__doPostBack(...)', 0)"
    #
    # Give the ASP.NET postback time to finish.
    await frame.page.wait_for_timeout(
        800
    )

    # Keep/set the supplied 10g weight.
    await select_weight(frame)

    # Click the actual button.
    clicked = await click_calculate(
        frame
    )

    if not clicked:
        print(
            "Could not click Izračunaj."
        )

        return False

    # Now wait for the exact message.
    found = await wait_for_unavailable_message(
        frame
    )

    if found:
        print()
        print(
            "!!! EXACT UNAVAILABLE MESSAGE FOUND !!!"
        )
        print(
            f"LIST 2 ADD: {name}"
        )
        print()
        return True

    print(
        f"No unavailable message for {name}."
    )

    return False

except Exception as exc:
    print(
        f"Exception testing {name}: "
        f"{type(exc).__name__}: {exc}"
    )

    return False
```

def write_output(
list_1,
list_2,
status,
):
"""
Write posta-countries.txt.

```
List 1:
    exact dropdown contents in original order.

List 2:
    only countries producing the exact unavailable message.
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
    "Actual country dropdown contents"
)

lines.append(
    "-" * 70
)

for country in list_1:
    lines.append(
        country["name"]
    )

lines.append("")

lines.append(
    "LIST 2"
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

if frame is not None:
    try:
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
section(
"JP BH POŠTA COUNTRY MONITOR"
)

```
print(
    f"URL: {URL}"
)

print(
    f"Output: {OUTPUT_FILE}"
)

# Create the required file immediately.
write_output(
    [],
    [],
    "STARTING",
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
    list_1 = []
    list_2 = []

    try:
        # --------------------------------------------------------
        # Open calculator
        # --------------------------------------------------------

        section(
            "OPENING CALCULATOR PAGE"
        )

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
                "WARNING: page.goto timed out."
            )
            print(
                "Continuing because the page may "
                "already be usable."
            )
            print(exc)

        print(
            f"Final page URL: {page.url}"
        )

        await page.wait_for_timeout(
            2_000
        )

        # --------------------------------------------------------
        # Find iframe
        # --------------------------------------------------------

        frame = await find_calculator_frame(
            page
        )

        if frame is None:
            raise RuntimeError(
                "Could not locate calculator iframe."
            )

        print(
            f"Calculator frame URL: {frame.url}"
        )

        # --------------------------------------------------------
        # Select international tab
        # --------------------------------------------------------

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

        # --------------------------------------------------------
        # Find country dropdown
        # --------------------------------------------------------

        dropdown = (
            await wait_for_country_dropdown(
                frame
            )
        )

        if dropdown is None:
            raise RuntimeError(
                "International calculator selected, "
                "but #ddlMeDoOdrediste was not found."
            )

        print(
            "International country dropdown found."
        )

        # --------------------------------------------------------
        # Read List 1
        # --------------------------------------------------------

        list_1 = await read_list_1(
            dropdown
        )

        if not list_1:
            raise RuntimeError(
                "Country dropdown is empty."
            )

        # Save List 1 immediately.
        write_output(
            list_1,
            list_2,
            "LIST_1_READ",
        )

        # --------------------------------------------------------
        # Test every dropdown entry
        # --------------------------------------------------------

        section(
            "TESTING COUNTRIES FOR LIST 2"
        )

        for index, country in enumerate(
            list_1,
            1,
        ):
            print()
            print(
                "=" * 70
            )
            print(
                f"[{index}/{len(list_1)}] "
                f"{country['name']}"
            )
            print(
                "=" * 70
            )

            unavailable = await test_country(
                frame,
                dropdown,
                country,
            )

            if unavailable:
                list_2.append(
                    country
                )

            # Save after every country.
            write_output(
                list_1,
                list_2,
                "RUNNING",
            )

            await page.wait_for_timeout(
                BETWEEN_COUNTRIES_MS
            )

        # --------------------------------------------------------
        # Final output
        # --------------------------------------------------------

        write_output(
            list_1,
            list_2,
            "COMPLETE",
        )

        section(
            "MONITOR COMPLETE"
        )

        print(
            f"Output: {OUTPUT_FILE}"
        )

        print()
        print(
            "LIST 2:"
        )

        for country in list_2:
            print(
                country["name"]
            )

    except Exception as exc:
        section(
            "MONITOR FAILED"
        )

        print(
            f"{type(exc).__name__}: {exc}"
        )

        # Preserve the output file even on failure.
        try:
            write_output(
                list_1,
                list_2,
                "FAILED",
            )
        except Exception as output_error:
            print(
                "Could not write failure output: "
                f"{output_error}"
            )

        try:
            await create_diagnostics(
                page,
                frame,
                exc,
            )
        except Exception as diagnostic_error:
            print(
                "Could not create diagnostics: "
                f"{diagnostic_error}"
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
try:
asyncio.run(main())
except KeyboardInterrupt:
print("Interrupted.")
sys.exit(130)
