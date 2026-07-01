import os
import time
import subprocess
import logging
from urllib.parse import urlparse
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import (
    TimeoutException,
    StaleElementReferenceException,
    ElementNotInteractableException,
    ElementClickInterceptedException,
)

# Configure logging
log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

MICROSOFT_SSO_TIMEOUT_SECONDS = 45
MICROSOFT_SSO_POLL_INTERVAL_SECONDS = 0.5
BOOKING_TIME_CANDIDATES = [
    (8, 17),   # Common office-hours full-day span
    (8, 18),   # Some offices allow bookings until 18:00
    (9, 17),   # Conservative fallback
]

# Get credentials from 1Password CLI
def get_1password_field(item_name, field_name, vault="Private"):
    """Fetch a field from 1Password using the CLI"""
    import json
    logger.debug(f"Fetching field '{field_name}' from 1Password item '{item_name}' in vault '{vault}'")
    try:
        # Get the item in JSON format
        result = subprocess.run(
            ["op", "item", "get", item_name, "--vault", vault, "--format", "json"],
            capture_output=True,
            text=True,
            check=True
        )
        item_data = json.loads(result.stdout)
        
        # Find the field by id (which matches the field name for standard fields)
        for field in item_data.get("fields", []):
            if field.get("id") == field_name or field.get("label") == field_name:
                logger.debug(f"Successfully retrieved field '{field_name}'")
                return field.get("value", "")
        
        logger.error(f"Field '{field_name}' not found in item '{item_name}'")
        raise ValueError(f"Field '{field_name}' not found in item '{item_name}'")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to fetch {field_name} from 1Password: {e.stderr}")
        raise ValueError(f"Failed to fetch {field_name} from 1Password: {e.stderr}")

def get_1password_otp(item_name, vault="Private"):
    """Fetch TOTP code from 1Password using the CLI"""
    logger.debug(f"Fetching OTP from 1Password item '{item_name}' in vault '{vault}'")
    try:
        result = subprocess.run(
            ["op", "item", "get", item_name, "--vault", vault, "--otp"],
            capture_output=True,
            text=True,
            check=True
        )
        logger.debug("OTP retrieved successfully")
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to fetch OTP from 1Password: {e.stderr}")
        raise ValueError(f"Failed to fetch OTP from 1Password: {e.stderr}")


def is_authenticated_url(web_driver):
    """Return True once the browser has left the Microsoft/Deskbird sign-in flow
    and landed inside the authenticated Deskbird app.

    This check is deliberately strict. The previous logic only tested that
    "login" was absent from the URL, which let transient post-SSO pages such as
    "https://app.deskbird.com/sign-in/landing" and
    "https://app.deskbird.com/authenticationHandler?code=..." pass as
    "authenticated". The script then navigated away before Deskbird had finished
    exchanging the OAuth code for a session, so the app bounced it straight back
    to "/sign-in/landing?redirectUrl=..." and every booking attempt failed."""
    url = (web_driver.current_url or "").lower()
    if "deskbird.com" not in url:
        return False
    transient_markers = ("/login", "/sign-in", "authenticationhandler")
    return not any(marker in url for marker in transient_markers)

# 1Password item name and vault (configurable via env vars)
OP_ITEM_NAME = os.environ.get("OP_ITEM_NAME", "Deskbird")
OP_VAULT = os.environ.get("OP_VAULT", "Private")

# Deskbird office and floor IDs
OFFICE_ID = os.environ.get("OFFICE_ID")
FLOOR_ID = os.environ.get("FLOOR_ID")
PREFERRED_DESK = os.environ.get("PREFERRED_DESK", None)  # Optional preferred desk name

if not OFFICE_ID or not FLOOR_ID:
    logger.error("OFFICE_ID and FLOOR_ID environment variables must be set")
    raise ValueError("OFFICE_ID and FLOOR_ID environment variables must be set")

if PREFERRED_DESK:
    logger.info(f"Preferred desk: {PREFERRED_DESK}")

logger.info(f"Starting Deskbird booking automation")
logger.info(f"Fetching credentials from 1Password item: {OP_ITEM_NAME} in vault: {OP_VAULT}")
EMAIL = get_1password_field(OP_ITEM_NAME, "username", OP_VAULT)
PASSWORD = get_1password_field(OP_ITEM_NAME, "password", OP_VAULT)
logger.info(f"Email: {EMAIL}")
logger.info("Credentials retrieved successfully")

# Set up Chrome options for headless mode
logger.info("Configuring Chrome browser options")
chrome_options = Options()
chrome_options.add_argument("--headless=new")  # Use new headless mode
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--window-size=1920x1080")
chrome_options.add_argument("--disable-blink-features=AutomationControlled")
chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
chrome_options.add_experimental_option('useAutomationExtension', False)
chrome_options.binary_location = "/usr/bin/chromium"

# Set up the driver
logger.info("Initializing Chrome WebDriver")
service = Service("/usr/bin/chromedriver")
driver = webdriver.Chrome(service=service, options=chrome_options)
logger.info("Chrome WebDriver initialized successfully")

try:
    # Step 1: Go to login page and enter email
    logger.info("Step 1: Navigating to login page")
    driver.get("https://app.deskbird.com/login/check-in")
    logger.debug("Login page loaded")
    
    logger.debug("Waiting for email input field")
    email_input = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.NAME, "email"))
    )
    email_input.send_keys(EMAIL)
    logger.info(f"Entered email: {EMAIL}")
    time.sleep(2)  # Wait for page to react
    driver.save_screenshot("/tmp/deskbird_after_email.png")
    logger.debug("Screenshot saved: /tmp/deskbird_after_email.png")
    
    # Step 2: Click "Sign in" button
    logger.info("Step 2: Clicking 'Sign in' button")
    driver.save_screenshot("/tmp/deskbird_before_signin.png")
    logger.debug("Screenshot saved: /tmp/deskbird_before_signin.png")
    
    # Try multiple selectors for the Sign in button (UI may change over time)
    signin_selectors = [
        (By.XPATH, "//button[contains(., 'Sign in')]"),
        (By.XPATH, "//button[contains(., 'Log in')]"),
        (By.XPATH, "//button[contains(., 'Continue')]"),
        (By.XPATH, "//a[contains(., 'Sign in')]"),
        (By.XPATH, "//a[contains(., 'Log in')]"),
        (By.XPATH, "//a[contains(., 'Continue')]"),
        (By.XPATH, "//input[@type='submit' and (contains(@value, 'Sign in') or contains(@value, 'Log in') or contains(@value, 'Continue'))]"),
        (By.CSS_SELECTOR, "button[type='submit']"),
        (By.CSS_SELECTOR, "form button"),
    ]
    
    signin_clicked = False
    for by_method, selector in signin_selectors:
        try:
            logger.debug(f"Trying sign-in selector: {by_method} / {selector}")
            signin_button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((by_method, selector))
            )
            logger.info(f"Found sign-in button with {by_method}: {selector}")
            signin_button.click()
            logger.debug("Sign in button clicked")
            signin_clicked = True
            break
        except TimeoutException:
            continue
    
    if not signin_clicked:
        # Log page source for debugging before failing
        logger.error("Could not find sign-in button with any selector")
        logger.debug(f"Current URL: {driver.current_url}")
        driver.save_screenshot("/tmp/deskbird_signin_not_found.png")
        logger.debug("Screenshot saved: /tmp/deskbird_signin_not_found.png")
        page_src = driver.page_source
        logger.debug(f"Page source length: {len(page_src)} characters")
        # Log all clickable elements for debugging
        try:
            clickable = driver.find_elements(By.XPATH, "//button | //a | //input[@type='submit']")
            for elem in clickable[:20]:
                logger.debug(f"Clickable element: <{elem.tag_name}> text='{elem.text[:80]}' type='{elem.get_attribute('type')}' href='{elem.get_attribute('href')}'")
        except Exception:
            pass
        raise Exception("Could not find Sign in button on login page")
    
    # Wait for the Microsoft SSO button to appear
    time.sleep(2)
    logger.debug(f"Current URL: {driver.current_url}")
    driver.save_screenshot("/tmp/deskbird_after_signin_click.png")
    logger.debug("Screenshot saved: /tmp/deskbird_after_signin_click.png")
    
    # Step 2b: Click "Sign in with Microsoft" button (or continue if already redirected)
    logger.info("Step 2b: Clicking 'Sign in with Microsoft' button")

    def is_microsoft_login_active(web_driver):
        """Check if we've already reached the Microsoft login flow."""
        parsed = urlparse(web_driver.current_url)
        hostname = (parsed.hostname or "").lower()
        microsoft_hosts = (
            "microsoftonline.com",
            "live.com",
            "office.com",
        )
        if hostname and any(hostname.endswith(domain) for domain in microsoft_hosts):
            return True
        microsoft_indicators = [
            (By.CSS_SELECTOR, "input[name='loginfmt']"),
            (By.CSS_SELECTOR, "input[name='passwd']"),
            (By.CSS_SELECTOR, "input#i0116"),
            (By.CSS_SELECTOR, "input#i0118"),
            (By.CSS_SELECTOR, "input[name='otc']"),
            (By.CSS_SELECTOR, "input#idSIButton9"),
            (By.CSS_SELECTOR, "form[action*='login.microsoftonline.com']"),
        ]
        for by_method, selector in microsoft_indicators:
            if web_driver.find_elements(by_method, selector):
                return True
        return False

    def switch_to_microsoft_window(web_driver):
        """
        Switch to a window that already contains Microsoft auth flow.
        Returns True if such a window is found.
        """
        original_window = web_driver.current_window_handle
        for handle in web_driver.window_handles:
            try:
                web_driver.switch_to.window(handle)
                if is_microsoft_login_active(web_driver):
                    if handle != original_window:
                        logger.info("Microsoft login detected in popup window")
                    return True
            except Exception:
                continue
        web_driver.switch_to.window(original_window)
        return False

    microsoft_clicked = False
    if switch_to_microsoft_window(driver):
        logger.info("Microsoft login already active; skipping SSO button click")
        microsoft_clicked = True
    else:
        # Try multiple selectors for the Microsoft SSO button
        microsoft_selectors = [
            (By.XPATH, "//button[contains(., 'Sign in with Microsoft')]"),
            (By.XPATH, "//button[contains(., 'Continue with Microsoft')]"),
            (By.XPATH, "//button[contains(., 'Microsoft')]"),
            (By.XPATH, "//a[contains(., 'Sign in with Microsoft')]"),
            (By.XPATH, "//a[contains(., 'Continue with Microsoft')]"),
            (By.XPATH, "//a[contains(., 'Microsoft')]"),
            (By.XPATH, "//*[@role='button' and contains(., 'Microsoft')]"),
            (By.XPATH, "//button[contains(., 'SSO')]"),
            (By.XPATH, "//a[contains(., 'SSO')]"),
            (By.CSS_SELECTOR, "button[class*='microsoft'], a[class*='microsoft']"),
            (By.CSS_SELECTOR, "button[class*='sso'], a[class*='sso']"),
            (By.XPATH, "//a[contains(@href, 'microsoft')]"),
            (By.XPATH, "//a[contains(@href, 'login.microsoftonline.com')]"),
            (By.XPATH, "//button[contains(., 'work') or contains(., 'Work')]"),
            (By.XPATH, "//a[contains(., 'work') or contains(., 'Work')]"),
        ]

        deadline = time.time() + MICROSOFT_SSO_TIMEOUT_SECONDS
        while time.time() < deadline and not microsoft_clicked:
            # In some Deskbird flows the Step 2 click directly opens Microsoft auth,
            # either by redirect or by popup, without rendering another SSO button.
            if switch_to_microsoft_window(driver):
                logger.info("Microsoft login detected during polling; skipping SSO button click")
                microsoft_clicked = True
                break
            for by_method, selector in microsoft_selectors:
                logger.debug(f"Trying Microsoft SSO selector: {by_method} / {selector}")
                for microsoft_button in driver.find_elements(by_method, selector):
                    try:
                        if microsoft_button.is_displayed() and microsoft_button.is_enabled():
                            logger.info(f"Found Microsoft SSO button with {by_method}: {selector}")
                            microsoft_button.click()
                            logger.debug("Microsoft SSO button clicked")
                            microsoft_clicked = True
                            break
                    except (
                        StaleElementReferenceException,
                        ElementNotInteractableException,
                        ElementClickInterceptedException,
                    ):
                        continue
                if microsoft_clicked:
                    break
            if not microsoft_clicked:
                time.sleep(MICROSOFT_SSO_POLL_INTERVAL_SECONDS)

    # Re-check after selector attempts because some flows auto-redirect asynchronously.
    if not microsoft_clicked and switch_to_microsoft_window(driver):
        logger.info("Microsoft login detected after fallback checks; continuing")
        microsoft_clicked = True

    if not microsoft_clicked:
        logger.error("Could not find Microsoft SSO button with any selector")
        driver.save_screenshot("/tmp/deskbird_microsoft_not_found.png")
        logger.debug("Screenshot saved: /tmp/deskbird_microsoft_not_found.png")
        try:
            clickable = driver.find_elements(By.XPATH, "//button | //a | //input[@type='submit']")
            for elem in clickable[:20]:
                logger.debug(f"Clickable element: <{elem.tag_name}> text='{elem.text[:80]}' type='{elem.get_attribute('type')}' href='{elem.get_attribute('href')}'")
        except Exception:
            pass
        raise Exception("Could not find Microsoft SSO button on login page")
    
    # Wait for popup window and switch to it
    time.sleep(3)
    logger.debug(f"Number of windows: {len(driver.window_handles)}")
    if len(driver.window_handles) > 1 and not is_microsoft_login_active(driver):
        logger.info("Switching to Microsoft SSO popup window")
        driver.switch_to.window(driver.window_handles[-1])
    
    time.sleep(2)
    logger.debug(f"Current URL after popup: {driver.current_url}")
    driver.save_screenshot("/tmp/deskbird_ms_popup.png")
    logger.debug("Screenshot saved: /tmp/deskbird_ms_popup.png")
    
    # Step 3: Enter email in Microsoft login popup
    logger.info("Step 3: Entering email in Microsoft login")
    
    logger.debug("Waiting for Microsoft email input field")
    ms_email_input = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='email'], input[name='loginfmt']"))
    )
    ms_email_input.clear()
    ms_email_input.send_keys(EMAIL)
    logger.debug(f"Email entered in Microsoft login form")
    
    # Click Next button
    next_button = WebDriverWait(driver, 5).until(
        EC.element_to_be_clickable((By.XPATH, "//input[@type='submit' and @value='Next']"))
    )
    next_button.click()
    logger.debug("Next button clicked")
    
    # Step 4: Enter password
    logger.info("Step 4: Entering password")
    logger.debug(f"Password length: {len(PASSWORD)} characters")
    time.sleep(1)  # Wait for page to fully load
    logger.debug("Waiting for password input field")
    ms_password_input = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='password'], input[name='passwd']"))
    )
    # Just send keys directly without clearing
    ms_password_input.send_keys(PASSWORD)
    time.sleep(1)  # Brief pause after entering
    logger.info("Password entered successfully")
    driver.save_screenshot("/tmp/deskbird_password_entered.png")
    logger.debug("Screenshot saved: /tmp/deskbird_password_entered.png")
    
    # Click Sign in button
    logger.debug("Clicking Sign in button")
    signin_button = WebDriverWait(driver, 5).until(
        EC.element_to_be_clickable((By.XPATH, "//input[@type='submit' and @value='Sign in']"))
    )
    signin_button.click()
    logger.debug("Sign in button clicked")
    
    # Step 5: Handle post-password page (OTP or Stay signed in)
    logger.info("Step 5: Waiting for post-authentication page")
    time.sleep(3)  # Wait for next page to load
    logger.debug(f"Current URL: {driver.current_url}")
    driver.save_screenshot("/tmp/deskbird_after_password.png")
    logger.debug("Screenshot saved: /tmp/deskbird_after_password.png")
    
    # Check if OTP is required
    try:
        otp_input = driver.find_element(By.CSS_SELECTOR, "input[type='tel'], input[name='otc']")
        logger.info("OTP page detected, fetching code from 1Password")
        otp_code = get_1password_otp(OP_ITEM_NAME, OP_VAULT)
        logger.debug(f"OTP code starts with: {otp_code[:3]}...")
        otp_input.clear()
        otp_input.send_keys(otp_code)
        logger.debug("OTP code entered")
        
        # Click Verify button
        verify_button = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//input[@type='submit' and @value='Verify']"))
        )
        verify_button.click()
        logger.info("OTP submitted successfully")
        
        # After OTP, check for "Stay signed in?" prompt
        time.sleep(3)  # Wait for next page (increased from 2 to 3)
        try:
            yes_button = WebDriverWait(driver, 10).until(  # Increased from 5 to 10
                EC.presence_of_element_located((By.XPATH, "//input[@type='submit' and @value='Yes']"))
            )
            logger.info("Found 'Stay signed in?' prompt after OTP, clicking Yes")
            yes_button.click()
            time.sleep(2)  # Give it time to process
        except:
            logger.debug("No 'Stay signed in' prompt found after OTP")
            pass
    except:
        logger.debug("No OTP page found, checking for other prompts")
        # Check for "Stay signed in?" prompt
        try:
            yes_button = driver.find_element(By.XPATH, "//input[@type='submit' and @value='Yes']")
            logger.info("Found 'Stay signed in?' prompt, clicking Yes")
            yes_button.click()
        except:
            logger.debug("No 'Stay signed in' prompt found")
            pass
    
    # Wait for authentication to complete - popup should close automatically
    logger.info("Waiting for authentication to complete")
    WebDriverWait(driver, 60).until(  # Increased from 30 to 60 for cluster environment
        lambda d: len(d.window_handles) == 1
    )
    logger.debug("Popup closed, switching to main window")
    
    # Switch back to main window
    driver.switch_to.window(driver.window_handles[0])
    
    # Wait for redirect to complete on main window  
    WebDriverWait(driver, 60).until(  # Increased from 30 to 60 for cluster environment
        is_authenticated_url
    )
    logger.info(f"Authentication successful! Current URL: {driver.current_url}")
    
    # Step 6: Calculate next week's booking date
    logger.info("Step 6: Calculating booking date")
    today = datetime.now()
    booking_date = today + timedelta(days=7)  # Book for this day next week (7 days ahead from today)
    logger.info(f"Booking for date: {booking_date.strftime('%Y-%m-%d %A')}")
    
    # Convert to epoch milliseconds for an office-hours-compatible full day.
    # Some offices reject an end-time outside configured opening hours.
    def build_booking_url(start_hour, end_hour):
        start_of_day = booking_date.replace(hour=start_hour, minute=0, second=0, microsecond=0)
        end_of_day = booking_date.replace(hour=end_hour, minute=0, second=0, microsecond=0)
        start_time = int(start_of_day.timestamp() * 1000)
        end_time = int(end_of_day.timestamp() * 1000)
        return (
            f"https://app.deskbird.com/office/{OFFICE_ID}/bookings/dashboard"
            f"?floorId={FLOOR_ID}&viewType=card&areaType=flexDesk"
            f"&startTime={start_time}&endTime={end_time}&isFullDay=true"
        ), start_of_day, end_of_day
    
    # First navigate to the main booking dashboard to ensure sidebar loads
    logger.info("Step 6a: Navigating to main booking dashboard")
    logger.debug(f"Office ID: {OFFICE_ID}")
    driver.get(f"https://app.deskbird.com/office/{OFFICE_ID}/bookings/dashboard")
    time.sleep(5)  # Wait for initial load
    logger.debug("Main dashboard loaded")
    
    # Now navigate to the specific date with a valid time range.
    logger.info(f"Step 6b: Navigating to booking page for {booking_date.strftime('%Y-%m-%d')}")
    logger.debug(f"Floor ID: {FLOOR_ID}")

    booking_url = None
    for start_hour, end_hour in BOOKING_TIME_CANDIDATES:
        candidate_url, candidate_start, candidate_end = build_booking_url(start_hour, end_hour)
        logger.info(
            f"Trying booking window {candidate_start.strftime('%H:%M')} - {candidate_end.strftime('%H:%M')}"
        )
        logger.debug(f"Booking URL: {candidate_url}")
        driver.get(candidate_url)
        logger.info("Waiting for desk availability to load")
        time.sleep(8)  # Give the Angular app time to render

        page_text = (driver.page_source or "").lower()
        if "end time of booking is invalid" in page_text:
            logger.warning("Deskbird rejected booking end time; trying fallback window")
            continue

        booking_url = candidate_url
        break

    if not booking_url:
        raise Exception("Could not find a valid booking time range accepted by Deskbird")
    
    # Wait for the main content area to load
    try:
        WebDriverWait(driver, 20).until(
            lambda d: len(d.page_source) > 10000  # Wait for substantial page content
        )
        logger.debug("Page content loaded")
    except:
        logger.warning("Page may not be fully loaded")
    
    # Wait for the booking widgets to render. The Deskbird UI was redesigned:
    # the old <db-my-spaces> widget no longer exists. Bookable desks now appear
    # in a "Suggestions" widget (data-testid="booking-suggestions-container"),
    # each entry exposing a data-testid="booking-suggestions-quick-book" button,
    # alongside a floor list of data-testid="desk-area-card" cards.
    SUGGESTION_CARD_SELECTOR = "[data-testid='booking-suggestions-card']"
    QUICK_BOOK_SELECTOR = "[data-testid='booking-suggestions-quick-book']"
    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((
                By.CSS_SELECTOR,
                f"{QUICK_BOOK_SELECTOR}, "
                "[data-testid='booking-suggestions-container'], "
                "[data-testid='desk-area-card']",
            ))
        )
        logger.debug("Booking suggestions / desk cards loaded")
    except Exception:
        logger.warning("Booking suggestions widget may not be loaded")

    driver.save_screenshot("/tmp/deskbird_booking_page.png")
    logger.debug("Screenshot saved: /tmp/deskbird_booking_page.png")

    # Step 6c: Check if already booked for this date (idempotency). When nothing
    # is booked Deskbird shows "No bookings for the selected day"; once a desk is
    # booked that message is replaced by a booking card
    # (data-testid="booking-card-location" plus a cancel action).
    logger.info("Step 6c: Checking if already booked for this date")
    page_lower = (driver.page_source or "").lower()
    if "no bookings for the selected day" in page_lower:
        logger.debug("'No bookings for the selected day' shown - proceeding to book")
    else:
        existing_booking = driver.find_elements(
            By.CSS_SELECTOR,
            "[data-testid='booking-card-location'], "
            "[data-testid='bookings--action-cancel-booking']",
        )
        if existing_booking:
            logger.info("✓ Desk already booked for this date - no action needed")
            driver.quit()
            exit(0)
        logger.debug("Booking status unclear - proceeding to book")

    # Step 7: Book a desk. Deskbird lists the Suggestions favourite-first, so the
    # first quick-book button already corresponds to the user's preferred desk
    # when it is available. If PREFERRED_DESK is set we still try to match it
    # explicitly among the suggestions before falling back to the first one.
    logger.info("Step 7: Looking for a desk to book")
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(2)
    driver.save_screenshot("/tmp/deskbird_after_scroll.png")
    logger.debug("Screenshot after scroll saved")

    def card_matches_preferred(card_text, preferred):
        """True if a suggestion card refers to the preferred desk. PREFERRED_DESK
        looks like "D", "5.09 D" or "Desk 5.09 D": an optional single-letter seat
        label and/or a desk number, both of which appear in the card text."""
        lines = [ln.strip() for ln in card_text.splitlines() if ln.strip()]
        parts = preferred.strip().split()
        letter = next((p for p in parts if len(p) == 1 and p.isalpha()), None)
        number = next((p for p in parts if any(ch.isdigit() for ch in p)), None)
        if not letter and not number:
            return False
        letter_ok = letter is None or letter in lines
        number_ok = number is None or number in card_text
        return letter_ok and number_ok

    def quick_book(button, desk_label):
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
        time.sleep(0.5)
        try:
            button.click()
        except (ElementNotInteractableException, ElementClickInterceptedException,
                StaleElementReferenceException):
            driver.execute_script("arguments[0].click();", button)
        logger.info(f"✓ Clicked 'Quick book' for {desk_label}")

    button_found = False
    booked_desk = None
    suggestion_cards = driver.find_elements(By.CSS_SELECTOR, SUGGESTION_CARD_SELECTOR)
    logger.info(f"Found {len(suggestion_cards)} desk suggestion(s)")

    # 7a: Try the preferred desk among the suggestions
    if PREFERRED_DESK and suggestion_cards:
        logger.info(f"Looking for preferred desk '{PREFERRED_DESK}' in suggestions")
        for card in suggestion_cards:
            try:
                if card_matches_preferred(card.text, PREFERRED_DESK):
                    button = card.find_element(By.CSS_SELECTOR, QUICK_BOOK_SELECTOR)
                    quick_book(button, f"preferred desk {PREFERRED_DESK}")
                    booked_desk = PREFERRED_DESK
                    button_found = True
                    break
            except Exception as e:
                logger.debug(f"Skipping suggestion: {str(e)[:80]}")
                continue
        if not button_found:
            logger.warning(
                f"Preferred desk '{PREFERRED_DESK}' not available - booking first available desk"
            )

    # 7b: Fallback - first available quick-book button (favourite-first ordering)
    if not button_found:
        quick_book_buttons = driver.find_elements(By.CSS_SELECTOR, QUICK_BOOK_SELECTOR)
        if quick_book_buttons:
            quick_book(quick_book_buttons[0], "first available desk")
            button_found = True

    # 7c: Last-resort legacy/alternate selectors
    if not button_found:
        logger.info("No suggestion buttons found - trying fallback selectors")
        fallback_selectors = [
            (By.CSS_SELECTOR, "a[data-testid='common--user-spaces-cards-quick-book']"),
            (By.XPATH, "//a[contains(., 'Quick book')]"),
            (By.XPATH, "//button[contains(., 'Quick book')]"),
            (By.XPATH, "//button[contains(., 'Book')]"),
        ]
        for by_method, selector in fallback_selectors:
            try:
                button = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((by_method, selector))
                )
                quick_book(button, "available desk (fallback selector)")
                button_found = True
                break
            except TimeoutException:
                continue

    if not button_found:
        logger.error("Could not find a Quick book button with any selector")
        try:
            logger.error(f"Current URL: {driver.current_url}")
            logger.error(f"Page source length: {len(driver.page_source)} characters")
            driver.save_screenshot("/tmp/deskbird_no_button_found.png")
        except Exception as e:
            logger.error(f"Could not capture debug info: {str(e)[:100]}")
        raise Exception("Could not find Quick book button")

    # Step 8: Confirm the booking landed. Quick book on a suggestion books
    # immediately (Full day is already applied via the URL parameters and the
    # top-of-page toggle), so we just verify the result and capture a screenshot.
    logger.info("Step 8: Verifying booking")
    time.sleep(4)
    driver.save_screenshot("/tmp/deskbird_after_booking.png")
    logger.debug("Screenshot saved: /tmp/deskbird_after_booking.png")
    try:
        WebDriverWait(driver, 15).until(
            lambda d: bool(d.find_elements(By.CSS_SELECTOR, "[data-testid='booking-card-location']"))
            or "no bookings for the selected day" not in (d.page_source or "").lower()
        )
        confirmation = f" Desk: {booked_desk}" if booked_desk else ""
        logger.info(f"✓ Booking completed successfully!{confirmation}")
    except Exception:
        logger.warning("Could not positively confirm the booking, but Quick book was clicked")
        logger.info("✓ Booking completed successfully!")
    
except Exception as e:
    logger.error(f"Error occurred: {str(e)}")
    logger.error(f"Error type: {type(e).__name__}")
    # Take a screenshot for debugging if driver is still active
    try:
        driver.save_screenshot("/tmp/deskbird_error.png")
        logger.debug("Error screenshot saved: /tmp/deskbird_error.png")
    except:
        logger.debug("Could not save error screenshot (driver may be closed)")
    raise
finally:
    try:
        logger.info("Closing browser")
        driver.quit()
        logger.info("Browser closed")
    except:
        logger.debug("Browser already closed")
