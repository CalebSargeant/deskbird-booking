import os
import time
import subprocess
import logging
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

# Configure logging
log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

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
    signin_button = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Sign in')]"))
    )
    signin_button.click()
    logger.debug("Sign in button clicked")
    
    # Wait for the Microsoft SSO button to appear
    time.sleep(2)
    logger.debug(f"Current URL: {driver.current_url}")
    
    # Step 2b: Click "Sign in with Microsoft" button
    logger.info("Step 2b: Clicking 'Sign in with Microsoft' button")
    microsoft_button = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Sign in with Microsoft')]"))
    )
    microsoft_button.click()
    logger.debug("Microsoft SSO button clicked")
    
    # Wait for popup window and switch to it
    time.sleep(3)
    logger.debug(f"Number of windows: {len(driver.window_handles)}")
    if len(driver.window_handles) > 1:
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
                EC.presence_of_element_located((By.XPATH, "//input[@type='submit' and @value='Yes']")
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
        lambda d: "login" not in d.current_url and "deskbird.com" in d.current_url
    )
    logger.info(f"Authentication successful! Current URL: {driver.current_url}")
    
    # Step 6: Calculate next week's booking date
    logger.info("Step 6: Calculating booking date")
    today = datetime.now()
    booking_date = today + timedelta(days=7)  # Book for this day next week (7 days ahead from today)
    logger.info(f"Booking for date: {booking_date.strftime('%Y-%m-%d %A')}")
    
    # Convert to epoch milliseconds for full day (7am to 7pm)
    start_of_day = booking_date.replace(hour=6, minute=0, second=0, microsecond=0)
    end_of_day = booking_date.replace(hour=18, minute=0, second=0, microsecond=0)
    start_time = int(start_of_day.timestamp() * 1000)
    end_time = int(end_of_day.timestamp() * 1000)
    logger.debug(f"Booking time range: {start_of_day} to {end_of_day}")
    
    # First navigate to the main booking dashboard to ensure sidebar loads
    logger.info("Step 6a: Navigating to main booking dashboard")
    logger.debug(f"Office ID: {OFFICE_ID}")
    driver.get(f"https://app.deskbird.com/office/{OFFICE_ID}/bookings/dashboard")
    time.sleep(5)  # Wait for initial load
    logger.debug("Main dashboard loaded")
    
    # Now navigate to the specific date
    booking_url = f"https://app.deskbird.com/office/{OFFICE_ID}/bookings/dashboard?floorId={FLOOR_ID}&viewType=card&areaType=flexDesk&startTime={start_time}&endTime={end_time}&isFullDay=true"
    
    logger.info(f"Step 6b: Navigating to booking page for {booking_date.strftime('%Y-%m-%d')}")
    logger.debug(f"Floor ID: {FLOOR_ID}")
    logger.debug(f"Booking URL: {booking_url}")
    driver.get(booking_url)
    
    # Wait for page to fully load - wait for desk cards to appear
    logger.info("Waiting for desk availability to load")
    time.sleep(10)  # Give the Angular app time to fully render
    
    # Wait for the main content area to load
    try:
        WebDriverWait(driver, 20).until(
            lambda d: len(d.page_source) > 10000  # Wait for substantial page content
        )
        logger.debug("Page content loaded")
    except:
        logger.warning("Page may not be fully loaded")
    
    # Wait for My Spaces widget to load (contains the Quick book button)
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, "//db-my-spaces"))
        )
        logger.debug("My Spaces widget loaded")
    except:
        logger.warning("My Spaces widget may not be loaded")
    
    driver.save_screenshot("/tmp/deskbird_booking_page.png")
    logger.debug("Screenshot saved: /tmp/deskbird_booking_page.png")
    
    # Step 6c: Check if already booked
    logger.info("Step 6c: Checking if already booked for this date")
    try:
        # Look for specific booking indicator - check if "No bookings" message exists
        no_bookings = driver.find_element(By.XPATH, "//div[contains(text(), 'No bookings for the selected day')]")
        logger.debug("Found 'No bookings' message, proceeding with booking attempt")
    except:
        # If "No bookings" message doesn't exist, there might be an existing booking
        try:
            # Look for actual booking cards/items in My bookings section
            existing_booking = driver.find_element(By.XPATH, "//div[contains(@class, 'booking-card') or contains(@class, 'booked-desk')]")
            if existing_booking:
                logger.info("✓ Desk already booked for this date - no action needed")
                driver.quit()
                exit(0)
        except:
            logger.debug("Could not determine booking status clearly, proceeding with booking attempt")
    
    # Step 7: Click the first available "Quick book" button
    logger.info("Step 7: Looking for booking button")
    
    # Scroll down to make sure all desk cards are visible (especially bottom ones)
    logger.debug("Scrolling to reveal all desk cards")
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(2)
    driver.save_screenshot("/tmp/deskbird_after_scroll.png")
    logger.debug("Screenshot after scroll saved")
    
    button_found = False
    booked_desk = None
    
    # If preferred desk is specified, try to book it first
    if PREFERRED_DESK:
        logger.info(f"Looking for preferred desk: {PREFERRED_DESK}")
        try:
            # Parse preferred desk: expect format like "D" or "5.09 D" or "Desk 5.09 D"
            # Extract the letter (A, B, C, D) and desk number if provided
            desk_parts = PREFERRED_DESK.strip().split()
            desk_letter = None
            desk_number = None
            
            # Try to identify desk letter and number
            for part in desk_parts:
                if part in ['A', 'B', 'C', 'D']:  # Single letter labels
                    desk_letter = part
                elif '5.' in part or part.replace('.', '').isdigit():  # Desk number like "5.09" or "509"
                    desk_number = part.replace('Desk', '').strip()
                    # Normalize format to "5.XX"
                    if '.' not in desk_number:
                        desk_number = f"5.{desk_number.lstrip('5')}"
            
            # If only single letter provided and no number, default to 5.09 for backward compatibility
            if not desk_number and desk_letter and len(PREFERRED_DESK.strip()) <= 3:
                desk_number = "5.09"
                logger.info(f"Preferred desk letter '{desk_letter}' only - defaulting to Desk {desk_number}")
            elif desk_letter and desk_number:
                logger.info(f"Preferred desk: {desk_number} {desk_letter}")
            
            # Build selector that looks for the desk letter near the desk number
            if desk_letter and desk_number:
                # Look for a container that has both the desk letter and desk number
                preferred_desk_selectors = [
                    # Find desk letter that's in a card also containing the desk number
                    f"//div[contains(., 'Desk {desk_number}')]//preceding::*[contains(text(), '{desk_letter}') and not(contains(text(), '{desk_letter} '))][1]/ancestor::div[contains(@class, 'space') or contains(@class, 'card')][.//div[contains(., 'Desk {desk_number}')]]//a[contains(., 'Quick book')]",
                    # Alternative: find the letter, then check if same container has desk number
                    f"//*[text()='{desk_letter}' or text()='{desk_letter} ♥']/ancestor::*[.//div[contains(., 'Desk {desk_number}')] and .//a[contains(., 'Quick book')]][1]//a[contains(., 'Quick book')]",
                    # Try finding the container with both letter and number visible
                    f"//div[contains(., '{desk_letter}') and contains(., 'Desk {desk_number}')]//a[contains(., 'Quick book')]",
                ]
                
                # Try to find and scroll the desk into view
                logger.debug(f"Looking for desk {desk_letter} near Desk {desk_number}")
                desk_element = None
                try:
                    # Try to find element containing both identifiers
                    desk_element = driver.find_element(By.XPATH, f"//div[contains(., '{desk_letter}') and contains(., 'Desk {desk_number}')]")
                    if desk_element:
                        logger.debug(f"Found desk element, scrolling into view")
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", desk_element)
                        time.sleep(1)
                        driver.save_screenshot("/tmp/deskbird_preferred_desk_view.png")
                except:
                    logger.debug("Could not scroll to preferred desk, will try to find button anyway")
            else:
                # Fallback to original logic if we can't parse
                preferred_desk_selectors = [
                    f"//div[contains(., '{PREFERRED_DESK}')]//following-sibling::*//a[contains(., 'Quick book')]",
                    f"//div[contains(., '{PREFERRED_DESK}')]//ancestor::div[contains(@class, 'space') or contains(@class, 'card')]//a[contains(., 'Quick book')]",
                ]
            
            # Skip XPath selectors for now - go straight to manual filtering
            # for selector in preferred_desk_selectors:
            #     try:
            #         logger.debug(f"Trying preferred desk selector: {selector[:80]}...")
            #         preferred_button = WebDriverWait(driver, 3).until(
            #             EC.element_to_be_clickable((By.XPATH, selector))
            #         )
            #         preferred_button.click()
            #         logger.info(f"✓ Successfully booked preferred desk: {PREFERRED_DESK}")
            #         booked_desk = PREFERRED_DESK
            #         button_found = True
            #         break
            #     except:
            #         continue
            
            # Use manual filtering approach (more reliable)
            if not button_found and desk_letter and desk_number:
                logger.debug(f"Manual filtering for My spaces: letter {desk_letter} + Desk {desk_number}")
                try:
                    # Limit search to the 'My spaces' widget to avoid matching 'Desk' from elsewhere
                    my_spaces = driver.find_element(By.XPATH, "//db-my-spaces | //div[contains(., 'My spaces')]")
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", my_spaces)
                    time.sleep(1)
                    
                    # Find all Quick book buttons inside My spaces
                    all_buttons = my_spaces.find_elements(By.XPATH, ".//a[contains(., 'Quick book')]")
                    logger.debug(f"My spaces has {len(all_buttons)} Quick book buttons")
                    
                    for button in all_buttons:
                        try:
                            # Get the card container for this entry
                            parent = button.find_element(By.XPATH, "./ancestor::div[contains(@class, 'space') or contains(@class, 'card') or contains(@class, 'ion-card')][1]")
                            parent_text = parent.text.strip()
                            lines = [ln.strip() for ln in parent_text.splitlines() if ln.strip()]
                            first_token = lines[0].split()[0] if lines else ""
                            contains_number = (f"Desk {desk_number}" in parent_text)
                            logger.debug(f"Entry first token='{first_token}', contains Desk {desk_number}={contains_number}")
                            
                            if first_token == desk_letter and contains_number:
                                logger.info(f"Found preferred entry: {desk_letter} + Desk {desk_number}")
                                # Scroll into view and click
                                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                                time.sleep(0.5)
                                button.click()
                                logger.info(f"✓ Successfully booked preferred desk: {desk_number} {desk_letter}")
                                booked_desk = f"{desk_number} {desk_letter}"
                                button_found = True
                                break
                        except Exception as e:
                            logger.debug(f"Skipping entry: {str(e)[:80]}")
                            continue
                except Exception as e:
                    logger.debug(f"Manual filtering in My spaces failed: {str(e)[:120]}")
            
            if not button_found:
                logger.warning(f"Preferred desk '{PREFERRED_DESK}' not available, will book any other desk")
        except Exception as e:
            logger.warning(f"Could not find preferred desk: {str(e)[:100]}")
    
    # If preferred desk wasn't booked, try to book any available desk
    if not button_found:
        logger.info("Looking for any available desk")
        # Try different selectors in order of preference
        selectors = [
            (By.CSS_SELECTOR, "a[data-testid='common--user-spaces-cards-quick-book']"),
            (By.XPATH, "//a[@data-testid='common--user-spaces-cards-quick-book']"),
            (By.XPATH, "//a[contains(text(), 'Quick book')]"),
            (By.XPATH, "//a[contains(., 'Quick book')]"),
            (By.XPATH, "//button[contains(text(), 'Book')]"),
            (By.XPATH, "//button[contains(., 'Book')]"),
            (By.XPATH, "//a[contains(@class, 'book-cta')]"),
            (By.CSS_SELECTOR, "button[class*='book']"),
            (By.CSS_SELECTOR, "a[class*='book']"),
        ]
        
        for by_method, selector in selectors:
            try:
                logger.debug(f"Trying {by_method} selector: {selector[:60]}...")
                quick_book_button = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((by_method, selector))
                )
                logger.info(f"Found button with {by_method} selector")
                quick_book_button.click()
                logger.info("✓ Clicked 'Quick book' button - booked any available desk")
                button_found = True
                break
            except Exception as e:
                logger.debug(f"Failed with {by_method}: {str(e)[:100]}")
                continue
    
    if not button_found:
        logger.error("Could not find booking button with any selector")
        try:
            logger.error(f"Current URL: {driver.current_url}")
            logger.error(f"Page source length: {len(driver.page_source)} characters")
            driver.save_screenshot("/tmp/deskbird_no_button_found.png")
            logger.debug("Screenshot saved: /tmp/deskbird_no_button_found.png")
            
            # Search for "book" in page source
            page_lower = driver.page_source.lower()
            if "book" in page_lower:
                logger.info("Found 'book' in page source. Contexts:")
                import re
                matches = re.finditer(r'.{0,100}book.{0,100}', page_lower, re.IGNORECASE)
                for i, match in enumerate(matches):
                    if i < 10:  # Show first 10 matches
                        logger.info(f"  Match {i+1}: ...{match.group()}...")
            else:
                logger.error("'book' not found anywhere in page source")
            
            logger.info("Page source (first 5000 chars):")
            logger.info(driver.page_source[:5000])
        except Exception as e:
            logger.error(f"Could not get debug info (driver may have crashed): {str(e)[:100]}")
        raise Exception("Could not find Quick book button")
    
    # Step 8: Enable "Full day" toggle if it exists and is disabled
    logger.info("Step 8: Checking for 'Full day' toggle")
    time.sleep(2)  # Wait for booking modal/dialog to appear
    driver.save_screenshot("/tmp/deskbird_booking_modal.png")
    logger.debug("Screenshot saved: /tmp/deskbird_booking_modal.png")
    
    try:
        # Look for the Full day toggle switch
        # Try different possible selectors for the toggle
        toggle_selectors = [
            (By.XPATH, "//label[contains(text(), 'Full day')]/..//input[@type='checkbox']"),
            (By.XPATH, "//label[contains(., 'Full day')]/..//input[@type='checkbox']"),
            (By.XPATH, "//input[@type='checkbox' and contains(@id, 'fullday')]"),
            (By.XPATH, "//input[@type='checkbox' and contains(@id, 'fullDay')]"),
            (By.XPATH, "//input[@type='checkbox' and contains(@name, 'fullday')]"),
            (By.XPATH, "//input[@type='checkbox' and contains(@name, 'fullDay')]"),
            (By.CSS_SELECTOR, "input[type='checkbox'][id*='fullday'], input[type='checkbox'][id*='full-day']"),
            (By.CSS_SELECTOR, "input[type='checkbox'][name*='fullday'], input[type='checkbox'][name*='full-day']"),
        ]
        
        toggle_found = False
        for by_method, selector in toggle_selectors:
            try:
                logger.debug(f"Trying toggle selector: {selector[:80]}...")
                full_day_toggle = WebDriverWait(driver, 3).until(
                    EC.presence_of_element_located((by_method, selector))
                )
                
                # Check if the toggle is already enabled
                is_checked = full_day_toggle.is_selected()
                logger.info(f"Full day toggle found! Currently {'enabled' if is_checked else 'disabled'}")
                
                if not is_checked:
                    logger.info("Enabling 'Full day' toggle")
                    # Click the toggle to enable it
                    full_day_toggle.click()
                    time.sleep(1)
                    logger.info("'Full day' toggle enabled")
                    driver.save_screenshot("/tmp/deskbird_fullday_enabled.png")
                    logger.debug("Screenshot saved: /tmp/deskbird_fullday_enabled.png")
                else:
                    logger.debug("'Full day' toggle is already enabled")
                
                toggle_found = True
                break
            except Exception as e:
                logger.debug(f"Failed with {by_method}: {str(e)[:100]}")
                continue
        
        if not toggle_found:
            logger.warning("Could not find 'Full day' toggle - it may already be enabled by URL parameter or not present")
    except Exception as e:
        logger.warning(f"Error while looking for Full day toggle: {str(e)[:200]}")
        logger.info("Continuing with booking...")
    
    # Wait a moment to ensure booking completes
    time.sleep(3)
    driver.save_screenshot("/tmp/deskbird_after_booking.png")
    logger.debug("Screenshot saved: /tmp/deskbird_after_booking.png")
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
