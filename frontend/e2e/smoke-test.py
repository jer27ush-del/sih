# End-to-end smoke test. Needs the app running (BASE_URL, default http://localhost:8000) and demo data (python manage.py seed_demo).
# Run: pip install playwright && python -m playwright install chromium && python frontend/e2e/smoke-test.py
import re, sys
from playwright.sync_api import sync_playwright, expect

import os
BASE = os.environ.get("BASE_URL", "http://localhost:8000")
errors = []
PDF = b"%PDF-1.4\n% e2e test document\n"

def login(page, email):
    page.goto(f"{BASE}/login")
    page.fill("#email", email)
    page.fill("#password", "demo123")
    page.get_by_role("button", name=re.compile("Sign in")).click()
    expect(page).to_have_url(re.compile(".*/dashboard"), timeout=15000)

def logout(page):
    page.get_by_label("Sign out").click()
    expect(page).to_have_url(re.compile(".*/login"), timeout=10000)

def step(name):
    print(f"\n== {name}")

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    page.on("pageerror", lambda e: errors.append(f"PAGEERROR: {e}"))
    page.on("console", lambda m: errors.append(f"CONSOLE: {m.text}") if m.type == "error" else None)

    step("1. Institution user signs in and sees own FDRs only")
    login(page, "institution@demo.test")
    expect(page.get_by_role("heading", name="Dashboard")).to_be_visible()
    page.goto(f"{BASE}/fdrs")
    expect(page.get_by_text("DEMO-FDR-1001")).to_be_visible(timeout=10000)
    expect(page.get_by_text("DEMO-FDR-1002")).to_have_count(0)
    print("   ok: sees DEMO-FDR-1001, not DEMO-FDR-1002")

    step("2. Institution registers an FDR with a document")
    page.goto(f"{BASE}/register")
    page.fill("#fdrNumber", "UI-FDR-7001")
    page.select_option("#bank", "Sample National Bank")
    page.fill("#branch", "E2E Branch")
    page.fill("#amount", "250000.50")
    page.fill("#issue", "2026-02-01")
    page.fill("#maturity", "2027-02-01")
    page.fill("#rate", "6.5")
    page.select_option("#category", "Security Deposit")
    page.set_input_files("#file", files=[{"name": "fdr.pdf", "mimeType": "application/pdf", "buffer": PDF}])
    page.get_by_role("button", name="Submit FDR").click()
    expect(page.get_by_text("submitted (reference")).to_be_visible(timeout=15000)
    print("   ok: submission confirmed")
    logout(page)

    step("3. Officer checks the record and verifies it after bank confirmation")
    login(page, "officer@demo.test")
    page.goto(f"{BASE}/verification")
    expect(page.get_by_text("UI-FDR-7001")).to_be_visible(timeout=10000)
    # DEMO-FDR-1002 has no document: verifying it must be refused with a clear message.
    page.get_by_text("DEMO-FDR-1002").click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible()
    page.fill("#bank-ref", "BANK-E2E-1")
    dialog.get_by_role("button", name="Record confirmation").click()
    expect(dialog.get_by_text("Bank confirmation recorded.")).to_be_visible(timeout=10000)
    page.fill("#decision-reason", "Confirmed with bank")
    dialog.get_by_role("button", name="Verify", exact=True).click()
    expect(dialog.get_by_text("usable supporting document")).to_be_visible(timeout=10000)
    print("   ok: 1002 refused without a document (error shown)")
    page.screenshot(path="e2e-output/verification-refused.png")
    page.keyboard.press("Escape")
    page.get_by_role("button", name="Close").first.click()

    page.get_by_text("UI-FDR-7001").click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible()
    page.fill("#bank-ref", "BANK-E2E-2")
    dialog.get_by_role("button", name="Record confirmation").click()
    expect(dialog.get_by_text("Bank confirmation recorded.")).to_be_visible(timeout=10000)
    page.fill("#decision-reason", "Confirmed with bank")
    dialog.get_by_role("button", name="Verify", exact=True).click()
    expect(dialog.get_by_text("Record verified and activated.")).to_be_visible(timeout=10000)
    expect(dialog.get_by_text("Active", exact=True).first).to_be_visible()
    print("   ok: UI-FDR-7001 verified and now Active")
    page.get_by_role("button", name="Close").first.click()
    logout(page)

    step("4. Administrator runs a report and reads the audit trail")
    login(page, "admin@demo.test")
    page.goto(f"{BASE}/reports")
    page.get_by_role("button", name="Run report").click()
    expect(page.get_by_text("UI-FDR-7001").first).to_be_visible(timeout=10000)
    print("   ok: report lists UI-FDR-7001")
    page.goto(f"{BASE}/audit")
    expect(page.get_by_text("fdr.status_changed").first).to_be_visible(timeout=10000)
    expect(page.get_by_text("bank.confirmed").first).to_be_visible()
    print("   ok: audit shows status change and bank confirmation")
    page.goto(f"{BASE}/institutions")
    expect(page.get_by_text("DEMO001").first).to_be_visible(timeout=10000)
    print("   ok: institutions page loads for administrator")
    page.screenshot(path="e2e-output/audit.png")
    logout(page)

    step("5. Institution user confirms the new FDR is Active")
    login(page, "institution@demo.test")
    page.goto(f"{BASE}/fdrs")
    page.get_by_role("searchbox").fill("UI-FDR-7001")
    row = page.locator("tr", has_text="UI-FDR-7001")
    expect(row.get_by_text("Active", exact=True)).to_be_visible(timeout=10000)
    print("   ok: status visible to the institution")
    page.screenshot(path="e2e-output/institution-fdrs.png")
    browser.close()

print("\nConsole/page errors collected:", len(errors))
for e in errors[:15]:
    print("  ", e[:220])
print("\nE2E COMPLETE")
