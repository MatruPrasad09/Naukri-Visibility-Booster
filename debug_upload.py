import asyncio
import json
import subprocess
from playwright.async_api import async_playwright

KEYCHAIN_ACCOUNT = "naukri_bot"
KEYCHAIN_SERVICE_SESSION = "naukri_session"
WORKSPACE_DIR = "/Users/matruprasadmohanty/Documents/Job Prep/Naukri_CareerGuard"
MASTER_RESUME = f"{WORKSPACE_DIR}/master_resume.pdf"

def get_session():
    result = subprocess.run(
        ["security", "find-generic-password", "-a", KEYCHAIN_ACCOUNT, "-s", KEYCHAIN_SERVICE_SESSION, "-w"],
        capture_output=True, text=True, check=True
    )
    return json.loads(result.stdout.strip())

async def main():
    session_data = get_session()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, args=["--window-position=-2000,0"])
        context = await browser.new_context(storage_state=session_data)
        page = await context.new_page()
        
        print("Navigating to Profile...")
        await page.goto("https://www.naukri.com/mnjuser/profile", timeout=60000)
        await page.wait_for_timeout(5000)
        
        print("Finding Update button in Resume section...")
        # Scroll to bottom to ensure it's in view
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(2000)
        
        # In Top Tier UI, the Resume section has an "Update" button.
        # Let's use expect_file_chooser and click the file input directly
        print("Setting input files directly to #resume...")
        try:
            file_input = page.locator('#resume')
            await file_input.set_input_files(MASTER_RESUME)
            print("Files set. Waiting 10 seconds to see if upload triggers...")
            await page.wait_for_timeout(10000)
            
            # Dump any text containing "successfully" or "upload"
            all_text = await page.locator('body').inner_text()
            print("Checking page text for 'successfully'...")
            for line in all_text.split('\n'):
                if 'success' in line.lower() or 'upload' in line.lower():
                    print("Found relevant text:", line)
                    
            await page.screenshot(path='audit/upload_test.png')
            print("Saved screenshot to audit/upload_test.png")
            
        except Exception as e:
            print(f"Error during upload test: {e}")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())