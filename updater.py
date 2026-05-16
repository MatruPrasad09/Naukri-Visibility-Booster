import asyncio
import json
import subprocess
import sys
import os
import time
import random
import sqlite3
import argparse
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from io import BytesIO
from loguru import logger

from playwright.async_api import async_playwright, Page
from reportlab.pdfgen import canvas
from pypdf import PdfReader, PdfWriter

# --- Configuration ---
WORKSPACE_DIR = "/Users/matruprasadmohanty/Naukri_CareerGuard"
DB_PATH = os.path.join(WORKSPACE_DIR, "state.db")
LOCK_FILE = os.path.join(WORKSPACE_DIR, "lock.txt")
MASTER_RESUME = os.path.join(WORKSPACE_DIR, "master_resume.pdf")
UPLOAD_RESUME = os.path.join(WORKSPACE_DIR, "upload_ready.pdf")
LOG_FILE = os.path.join(WORKSPACE_DIR, "logs/naukri_bot.log")

KEYCHAIN_ACCOUNT = "naukri_bot"
KEYCHAIN_SERVICE_SESSION = "naukri_session"
KEYCHAIN_SERVICE_TELEGRAM_TOKEN = "telegram_token"
KEYCHAIN_SERVICE_TELEGRAM_CHAT_ID = "telegram_chat_id"

# --- Setup Logging ---
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
logger.add(LOG_FILE, rotation="10 MB", retention="7 days")

# --- Database & Circuit Breaker ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value INTEGER)''')
    c.execute('''INSERT OR IGNORE INTO state (key, value) VALUES ('consecutive_failures', 0)''')
    conn.commit()
    conn.close()

def get_failures():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT value FROM state WHERE key="consecutive_failures"')
    val = c.fetchone()[0]
    conn.close()
    return val

def set_failures(count):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE state SET value=? WHERE key="consecutive_failures"', (count,))
    conn.commit()
    conn.close()

# --- Utilities ---
def get_keychain_secret(service):
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-a", KEYCHAIN_ACCOUNT, "-s", service, "-w"],
            capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except Exception as e:
        logger.error(f"Failed to get {service} from keychain: {e}")
        return None

def send_telegram_message(message, is_alert=False, photo_path=None):
    icon = "🚨 " if is_alert else "✅ "
    text = f"{icon}{message}"
    logger.info(f"Sending Telegram notification: {text}")
    print(text)
    
    token = get_keychain_secret(KEYCHAIN_SERVICE_TELEGRAM_TOKEN)
    chat_id = get_keychain_secret(KEYCHAIN_SERVICE_TELEGRAM_CHAT_ID)
    
    if token and chat_id:
        if photo_path and os.path.exists(photo_path):
            url = f"https://api.telegram.org/bot{token}/sendPhoto"
            try:
                subprocess.run([
                    "curl", "-s", "-X", "POST", url,
                    "-F", f"chat_id={chat_id}",
                    "-F", f"caption={text}",
                    "-F", f"photo=@{photo_path}"
                ], capture_output=True, check=True)
            except Exception as e:
                logger.error(f"Failed to send Telegram photo: {e}")
        else:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
            try:
                req = urllib.request.Request(url, data=data)
                with urllib.request.urlopen(req) as response:
                    pass
            except Exception as e:
                logger.error(f"Failed to send Telegram message: {e}")

def check_circuit_breaker():
    if os.path.exists(LOCK_FILE):
        logger.error("Circuit breaker tripped. lock.txt exists. Halting.")
        sys.exit(1)
    if get_failures() >= 3:
        logger.error("Consecutive failures reached 3. Tripping circuit breaker.")
        with open(LOCK_FILE, 'w') as f:
            f.write(f"Tripped at {datetime.now()}")
        send_telegram_message("CareerGuard Circuit Breaker Tripped! 3 consecutive failures. Check logs and remove lock.txt to resume.", is_alert=True)
        sys.exit(1)

def get_session_from_keychain():
    session_raw = get_keychain_secret(KEYCHAIN_SERVICE_SESSION)
    if not session_raw:
        send_telegram_message("Failed to retrieve session from Keychain. Did you run auth_setup.py?", is_alert=True)
        sys.exit(1)
    return json.loads(session_raw)

def get_dynamic_filename():
    month_year_str = datetime.now().strftime("%B%Y") # e.g., May2026
    return os.path.join(WORKSPACE_DIR, f"MatruPrasadMohanty_Resume_{month_year_str}.pdf")

def inject_invisible_text():
    logger.info("Injecting invisible text to PDF...")
    try:
        packet = BytesIO()
        can = canvas.Canvas(packet)
        can.setFillColorRGB(1, 1, 1) # White text
        can.drawString(10, 10, f"HashBuster: {datetime.now().isoformat()}")
        can.save()
        packet.seek(0)
        new_pdf = PdfReader(packet)
        
        existing_pdf = PdfReader(open(MASTER_RESUME, "rb"))
        output = PdfWriter()
        
        page = existing_pdf.pages[0]
        page.merge_page(new_pdf.pages[0])
        output.add_page(page)
        
        for i in range(1, len(existing_pdf.pages)):
            output.add_page(existing_pdf.pages[i])
            
        dynamic_path = get_dynamic_filename()
        with open(dynamic_path, "wb") as outputStream:
            output.write(outputStream)
            
        logger.info(f"Successfully generated {dynamic_path}")
        return dynamic_path
    except Exception as e:
        logger.error(f"Failed to manipulate PDF: {e}")
        raise e

def schedule_next_wake(dry_run=False):
    if dry_run:
        logger.info("DRY RUN: Skipping pmset wake schedule.")
        return

    now = datetime.now()
    
    # Schedule logic for 10:30 AM and 3:30 PM (15:30)
    # Wake up 5 minutes prior: 10:25 AM and 15:25
    
    # Check if we are before 10:25 AM
    if now.hour < 10 or (now.hour == 10 and now.minute < 25):
        next_wake = now.replace(hour=10, minute=25, second=0)
    # Check if we are before 15:25
    elif now.hour < 15 or (now.hour == 15 and now.minute < 25):
        next_wake = now.replace(hour=15, minute=25, second=0)
    # Otherwise schedule for 10:25 AM next day
    else:
        next_wake = (now + timedelta(days=1)).replace(hour=10, minute=25, second=0)
    
    wake_str = next_wake.strftime("%m/%d/%Y %H:%M:%S")
    logger.info(f"Scheduling next pmset wake for: {wake_str}")
    try:
        subprocess.run(["sudo", "pmset", "schedule", "wakeorpoweron", wake_str])
    except Exception as e:
        logger.error(f"Failed to schedule next wake: {e}")

# --- Page Objects ---
class ProfilePage:
    def __init__(self, page: Page):
        self.page = page

    async def pre_flight_check(self):
        logger.info("Running pre-flight check...")
        response = await self.page.goto("https://www.naukri.com/mnjuser/profile", timeout=60000)
        
        if response and response.status >= 500:
            send_telegram_message("NAUKRI_DOWN: Transient error, will retry next run", is_alert=True)
            sys.exit(0)
            
        if "nlogin" in self.page.url or "login" in self.page.url:
            send_telegram_message("SESSION_EXPIRED: Run auth_setup.py to renew session", is_alert=True)
            raise Exception("Session Expired")
            
        logger.info("Pre-flight check passed. On Profile Page.")

    async def upload_resume(self, upload_path, dry_run=False):
        logger.info("Attempting to upload resume...")
        try:
            # Scroll down to ensure React renders the DOM element
            await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await self.page.wait_for_timeout(2000)
            
            # Explicitly target the resume input, not the profile picture input
            file_input = self.page.locator('#resume')
            
            if dry_run:
                logger.info("DRY RUN: Skipping actual file upload and verification.")
                return True

            await file_input.set_input_files(upload_path)
            logger.info("File selected. Waiting for verification signals...")
            
            try:
                # Top Tier UI says "Uploaded today" right under the file name
                updated_text = self.page.locator("text='Uploaded today'")
                await updated_text.wait_for(state="visible", timeout=15000)
                logger.info("Verification Signal Passed: 'Uploaded today' text detected.")
                return True
            except Exception:
                logger.error("Verification signal failed. 'Uploaded today' not found.")
                raise Exception("Upload Verification Failed.")
                
        except Exception as e:
            logger.error(f"Error during upload: {e}")
            raise e

# --- Main Flow ---
async def run_updater(args):
    init_db()
    check_circuit_breaker()
    
    # 1. Jitter
    if not args.no_jitter:
        jitter_sec = random.randint(60, 900)
        logger.info(f"Applying jitter: Sleeping for {jitter_sec} seconds before execution...")
        time.sleep(jitter_sec)
    else:
        logger.info("Skipping jitter due to --no-jitter flag.")
    
    # 2. PDF Preparation
    upload_path = inject_invisible_text()
    
    # 3. Playwright Execution
    session_data = get_session_from_keychain()
    
    logger.info("Launching Playwright...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--window-position=-2000,0"] # Off-screen
        )
        context = await browser.new_context(storage_state=session_data)
        
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        page = await context.new_page()
        profile_page = ProfilePage(page)
        
        try:
            await profile_page.pre_flight_check()
            await profile_page.upload_resume(upload_path, dry_run=args.dry_run)
            
            logger.info("Profile update completed successfully.")
            
            # Take success screenshot
            screenshot_path = os.path.join(WORKSPACE_DIR, f"audit/success_trace_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
            await page.screenshot(path=screenshot_path, full_page=True)
            logger.info(f"Saved success screenshot to {screenshot_path}")
            
            if not args.dry_run:
                set_failures(0)
                send_telegram_message(f"CareerGuard: Profile successfully updated at {datetime.now().strftime('%I:%M %p')}!", photo_path=screenshot_path)
            
        except Exception as e:
            logger.error(f"Execution failed: {e}")
            
            screenshot_path = os.path.join(WORKSPACE_DIR, f"audit/error_trace_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
            await page.screenshot(path=screenshot_path, full_page=True)
            logger.info(f"Saved error screenshot to {screenshot_path}")
            
            if not args.dry_run:
                fails = get_failures() + 1
                set_failures(fails)
                send_telegram_message(f"CareerGuard Error: Profile update failed (Failure #{fails}/3). Check logs.", is_alert=True, photo_path=screenshot_path)
            
        finally:
            await browser.close()
            
            if os.path.exists(upload_path):
                os.remove(upload_path)
                logger.info(f"Cleaned up {upload_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CareerGuard Profile Updater")
    parser.add_argument("--dry-run", action="store_true", help="Navigate the site and prepare files, but skip the actual upload and DB updates.")
    parser.add_argument("--no-jitter", action="store_true", help="Skip the 1-15 minute random startup delay (ideal for testing).")
    args = parser.parse_args()

    try:
        asyncio.run(run_updater(args))
        schedule_next_wake(dry_run=args.dry_run)
    except Exception as e:
        logger.error(f"Fatal error in main loop: {e}")
        sys.exit(1)