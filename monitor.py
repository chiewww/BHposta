async def click_international_tab(frame):
    """
    Activate the DevExpress 'Međunarodni promet' tab.

    Exact HTML supplied by the user:

        <li id="ASPxTabControl1_T1">
            <a id="ASPxTabControl1_T1T" class="dxtc-link">
                <span class="dx-vam">Međunarodni promet</span>
            </a>
        </li>

    The actual clickable element is therefore:

        #ASPxTabControl1_T1T
    """

    print("Selecting Međunarodni promet...")

    tab = frame.locator(
        "#ASPxTabControl1_T1T"
    )

    count = await tab.count()

    print(
        f"International tab link count: {count}"
    )

    if count == 0:
        raise RuntimeError(
            "Could not find #ASPxTabControl1_T1T"
        )

    tab = tab.first

    try:
        print(
            "International tab HTML:"
        )

        print(
            (
                await tab.evaluate(
                    "(el) => el.outerHTML"
                )
            )[:2000]
        )

    except Exception:
        pass

    # ------------------------------------------------------------
    # Make sure it is visible.
    # ------------------------------------------------------------

    try:
        await tab.scroll_into_view_if_needed()
    except Exception:
        pass

    # ------------------------------------------------------------
    # Click the actual DevExpress tab link.
    # ------------------------------------------------------------

    try:
        print(
            "Clicking #ASPxTabControl1_T1T..."
        )

        await tab.click(
            timeout=DEFAULT_TIMEOUT,
            force=True,
        )

        print(
            "International tab link clicked."
        )

    except Exception as exc:
        print(
            f"Normal tab click failed: {exc}"
        )

        # --------------------------------------------------------
        # JavaScript fallback.
        # --------------------------------------------------------

        try:
            print(
                "Trying JavaScript click on "
                "#ASPxTabControl1_T1T..."
            )

            clicked = await frame.evaluate(
                """
                () => {
                    const el =
                        document.querySelector(
                            '#ASPxTabControl1_T1T'
                        );

                    if (!el) {
                        return false;
                    }

                    el.click();

                    return true;
                }
                """
            )

            print(
                f"JavaScript click result: {clicked}"
            )

            if not clicked:
                raise RuntimeError(
                    "JavaScript could not find "
                    "#ASPxTabControl1_T1T"
                )

        except Exception as js_exc:
            raise RuntimeError(
                "Could not click "
                "#ASPxTabControl1_T1T: "
                f"{js_exc}"
            )

    # ------------------------------------------------------------
    # Give ASP.NET/DevExpress time to switch the tab.
    # ------------------------------------------------------------

    await frame.page.wait_for_timeout(
        1_000
    )

    # ------------------------------------------------------------
    # Verify that the international country dropdown appeared.
    # ------------------------------------------------------------

    print(
        "Checking for international country dropdown..."
    )

    if await wait_for_international_selector(
        frame,
        timeout_ms=15_000,
    ):
        print(
            "International calculator activated."
        )
        return True

    # ------------------------------------------------------------
    # Diagnostic information if the tab click did not activate it.
    # ------------------------------------------------------------

    try:
        active_tab = frame.locator(
            "#ASPxTabControl1_T1"
        )

        if await active_tab.count() > 0:
            print(
                "International tab class after click:"
            )

            print(
                await active_tab.get_attribute(
                    "class"
                )
            )

    except Exception:
        pass

    try:
        country = frame.locator(
            "#ddlMeDoOdrediste"
        )

        print(
            "Country selector count after click:",
            await country.count(),
        )

    except Exception:
        pass

    return False
