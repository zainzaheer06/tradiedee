from playwright.sync_api import sync_playwright
import json

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    # Capture console messages
    console_logs = []
    def log_console(msg):
        console_logs.append({
            'type': msg.type,
            'text': msg.text
        })

    page.on('console', log_console)

    # Navigate to clinic hub
    response = page.goto('http://localhost:5004/clinic/', wait_until='domcontentloaded')

    print(f"Response status: {response.status}")
    print(f"Response URL: {page.url}")

    # Wait a bit for any JavaScript to execute
    page.wait_for_timeout(2000)

    # Check page content
    content = page.content()

    # Take screenshot
    page.screenshot(path='/tmp/clinic_hub.png', full_page=True)
    print("Screenshot saved to /tmp/clinic_hub.png")

    # Print console logs
    if console_logs:
        print("\n=== Console Logs ===")
        for log in console_logs:
            print(f"[{log['type']}] {log['text']}")

    # Check for error messages in page
    if "error" in content.lower() or "undefined" in content.lower():
        print("\n=== Page contains error/undefined ===")
        # Extract relevant parts
        import re
        errors = re.findall(r'<h1[^>]*>.*?</h1>|<p[^>]*>.*?Error.*?</p>|undefined', content, re.IGNORECASE)
        for error in errors[:5]:
            print(error)

    browser.close()
    print("\nTest complete")
