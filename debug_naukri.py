import asyncio
import json
import subprocess
from playwright.async_api import async_playwright

KEYCHAIN_ACCOUNT = "naukri_bot"
KEYCHAIN_SERVICE_SESSION = "naukri_session"

def get_session():
    result = subprocess.run(
        ["security", "find-generic-password", "-a", KEYCHAIN_ACCOUNT, "-s", KEYCHAIN_SERVICE_SESSION, "-w"],
        capture_output=True, text=True, check=True
    )
    return json.loads(result.stdout.strip())

async def main():
    session_data = get_session()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(storage_state=session_data)
        page = await context.new_page()
        
        print("Navigating...")
        await page.goto("https://www.naukri.com/mnjuser/profile", timeout=60000)
        await page.wait_for_load_state("networkidle")
        
        # Dump all text nodes containing "Update" or "Resume"
        print("Looking for Update buttons...")
        update_buttons = await page.locator('text="Update"').all()
        for i, btn in enumerate(update_buttons):
            visible = await btn.is_visible()
            html = await btn.evaluate("el => el.outerHTML")
            print(f"Update button {i}: visible={visible}, html={html}")
            
        print("\nLooking for Resume heading...")
        resume_headings = await page.locator('text="Resume"').all()
        for i, heading in enumerate(resume_headings):
            visible = await heading.is_visible()
            html = await heading.evaluate("el => el.outerHTML")
            print(f"Resume heading {i}: visible={visible}, html={html}")
            
        print("\nLooking for file inputs...")
        file_inputs = await page.locator('input[type="file"]').all()
        for i, inp in enumerate(file_inputs):
            # visible is usually false for file inputs
            html = await inp.evaluate("el => el.outerHTML")
            print(f"File input {i}: html={html}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
