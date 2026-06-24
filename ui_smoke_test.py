"""End-to-end UI smoke test against the running portal at localhost:8000."""
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8000"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

    page.goto(BASE)
    page.wait_for_load_state("networkidle")

    # AI status pill should resolve to local mode (no key configured)
    pill = page.locator("#ai-status").inner_text()
    print("AI status pill:", pill)

    # --- AI assist pre-fill ---
    page.fill("#ai-prompt",
              "A weekly warranty claims dashboard from SAP, owned by Sam Lee "
              "sam.lee@example.com, confidential, contains PII.")
    page.click("#ai-fill")
    page.wait_for_function("document.querySelector('#name').value.length > 0", timeout=10000)
    print("After assist -> name:", page.input_value("#name"))
    print("After assist -> classification:", page.input_value("#classification"))
    print("After assist -> pii checked:", page.is_checked("#contains_pii"))

    # --- Manual edit + save ---
    page.fill("#name", "Warranty Claims Weekly")
    page.fill("#owner_name", "Sam Lee")
    page.click("#dp-form button[type=submit]")

    # Should switch to catalog view and show the new product
    page.wait_for_selector(".dp-title", timeout=10000)
    titles = page.locator(".dp-title").all_inner_texts()
    print("Catalog titles:", titles)
    count = page.locator("#catalog-count").inner_text()
    print("Catalog count badge:", count)

    # --- Edit flow ---
    page.click("[data-edit]")
    page.wait_for_selector("#view-register:not(.hidden)")
    form_title = page.locator("#form-title").inner_text()
    print("Edit form title:", form_title)

    # --- Search ---
    page.click('.tab[data-view="catalog"]')
    page.fill("#search", "warranty")
    page.wait_for_timeout(300)
    print("Search results:", page.locator(".dp-title").count())

    # --- Contract flow ---
    page.fill("#search", "")
    page.wait_for_timeout(200)
    page.click("[data-contract]")  # open contract editor for the product
    page.wait_for_selector("#view-contract:not(.hidden)")
    page.fill("#ai-prompt-c",
              "id,order_date,customer_email,amount\n"
              "1,2026-06-01,jane@example.com,42.5\n"
              "Refreshed by 6am, 99.9% availability.")
    page.click("#ai-fill-c")
    page.wait_for_selector(".schema-row", timeout=10000)
    field_count = page.locator(".schema-row").count()
    print("Inferred schema rows:", field_count)
    # the email column should be flagged PII by the inference
    pii_checks = page.locator(".schema-row .f-pii:checked").count()
    print("PII-flagged fields:", pii_checks)
    page.select_option("#c-status", "active")
    page.click("#contract-form button[type=submit]")

    # back on catalog, the product should now show the contract chip
    page.wait_for_selector(".chip.contract", timeout=10000)
    has_contract_chip = page.locator(".chip.contract").count()
    print("Products with contract chip:", has_contract_chip)

    # re-open to confirm it loads the saved contract
    page.click("[data-contract]")
    page.wait_for_selector("#view-contract:not(.hidden)")
    page.wait_for_selector(".schema-row")
    print("Reloaded contract status:", page.input_value("#c-status"))
    print("Reloaded schema rows:", page.locator(".schema-row").count())

    print("Console errors:", errors)
    assert "Warranty Claims Weekly" in titles, "product not in catalog"
    assert field_count >= 4, "schema inference produced too few fields"
    assert pii_checks >= 1, "email field not flagged as PII"
    assert has_contract_chip >= 1, "contract chip not shown after save"
    assert not errors, f"console errors: {errors}"
    print("\nALL UI CHECKS PASSED")
    browser.close()
