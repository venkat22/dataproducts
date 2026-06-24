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

    print("Console errors:", errors)
    assert "Warranty Claims Weekly" in titles, "product not in catalog"
    assert not errors, f"console errors: {errors}"
    print("\nALL UI CHECKS PASSED")
    browser.close()
