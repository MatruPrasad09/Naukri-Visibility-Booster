import asyncio
import json
import subprocess
import sys
from playwright.async_api import async_playwright

KEYCHAIN_ACCOUNT = "naukri_bot"
KEYCHAIN_SERVICE_SESSION = "naukri_session"

def save_to_keychain(service, account, password):
    """Saves a string (password) to the macOS Keychain."""
    try:
        # Check if it already exists, if so, delete it first to avoid errors
        subprocess.run(
            ["security", "delete-generic-password", "-a", account, "-s", service],
            capture_output=True,
            text=True
        )
        # Add the new password
        result = subprocess.run(
            ["security", "add-generic-password", "-a", account, "-s", service, "-w", password],
            capture_output=True,
            text=True,
            check=True
        )
        print(f"✅ Successfully saved {service} to macOS Keychain.")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to save to Keychain. Error: {e.stderr}")
        sys.exit(1)

async def main():
    print("🚀 Launching browser for manual login...")
    async with async_playwright() as p:
        # Launch headed browser
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        print("Navigating to Naukri.com...")
        await page.goto("https://www.naukri.com/nlogin/login")

        print("\n" + "="*60)
        print("🛑 ACTION REQUIRED: Please log in to your Naukri account in the browser.")
        print("Solve any CAPTCHAs or OTPs.")
        print("Once you are fully logged in and on your profile/home page,")
        input("PRESS [ENTER] HERE IN THE TERMINAL TO SAVE YOUR SESSION...")
        print("="*60 + "\n")

        # Capture session state
        print("📸 Capturing session state...")
        state = await context.storage_state()
        state_json = json.dumps(state)

        # Save to Keychain
        print("🔐 Encrypting and saving session to Keychain...")
        save_to_keychain(KEYCHAIN_SERVICE_SESSION, KEYCHAIN_ACCOUNT, state_json)

        await browser.close()
        print("🎉 Setup complete! You do not need to run this again unless your session expires.")

if __name__ == "__main__":
    asyncio.run(main())
