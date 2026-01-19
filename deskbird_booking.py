import os
import time
import subprocess
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

# Get credentials from 1Password CLI
def get_1password_field(item_name, field_name, vault="Private"):
    """Fetch a field from 1Password using the CLI"""
    import json
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
                return field.get("value", "")
        
        raise ValueError(f"Field '{field_name}' not found in item '{item_name}'")
    except subprocess.CalledProcessError as e:
        raise ValueError(f"Failed to fetch {field_name} from 1Password: {e.stderr}")

def get_1password_otp(item_name, vault="Private"):
    """Fetch TOTP code from 1Password using the CLI"""
    try:
        result = subprocess.run(
            ["op", "item", "get", item_name, "--vault", vault, "--otp"],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise ValueError(f"Failed to fetch OTP from 1Password: {e.stderr}")

# 1Password item name and vault (configurable via env vars)
OP_ITEM_NAME = os.environ.get("OP_ITEM_NAME", "Deskbird")
OP_VAULT = os.environ.get("OP_VAULT", "Private")

# Deskbird office and floor IDs
OFFICE_ID = os.environ.get("OFFICE_ID")
FLOOR_ID = os.environ.get("FLOOR_ID")

if not OFFICE_ID or not FLOOR_ID:
    raise ValueError("OFFICE_ID and FLOOR_ID environment variables must be set")

print(f"Fetching credentials from 1Password item: {OP_ITEM_NAME} in vault: {OP_VAULT}")
EMAIL = get_1password_field(OP_ITEM_NAME, "username", OP_VAULT)
PASSWORD = get_1password_field(OP_ITEM_NAME, "password", OP_VAULT)
print(f"Email: {EMAIL}")
print("Password and OTP will be fetched as needed")

# Set up Chrome options for headless mode
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
service = Service("/usr/bin/chromedriver")
driver = webdriver.Chrome(service=service, options=chrome_options)

try:
    # Step 1: Go to login page and enter email
    print("Step 1: Navigating to login page...")
    driver.get("https://app.deskbird.com/login/check-in")
    
    email_input = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.NAME, "email"))
    )
    email_input.send_keys(EMAIL)
    print(f"Entered email: {EMAIL}")
    time.sleep(2)  # Wait for page to react
    driver.save_screenshot("/tmp/deskbird_after_email.png")
    
    # Step 2: Click "Sign in" button
    print("Step 2: Clicking 'Sign in' button...")
    signin_button = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Sign in')]"))
    )
    signin_button.click()
    print("Clicked Sign in button")
    
    # Wait for the Microsoft SSO button to appear
    time.sleep(2)
    print(f"Current URL: {driver.current_url}")
    
    # Step 2b: Click "Sign in with Microsoft" button
    print("Step 2b: Clicking 'Sign in with Microsoft' button...")
    microsoft_button = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Sign in with Microsoft')]"))
    )
    microsoft_button.click()
    print("Clicked Microsoft button")
    
    # Wait for popup window and switch to it
    time.sleep(3)
    print(f"Number of windows: {len(driver.window_handles)}")
    if len(driver.window_handles) > 1:
        print("Switching to popup window...")
        driver.switch_to.window(driver.window_handles[-1])
    
    time.sleep(2)
    print(f"Current URL after popup: {driver.current_url}")
    driver.save_screenshot("/tmp/deskbird_ms_popup.png")
    
    # Step 3: Enter email in Microsoft login popup
    print("Step 3: Entering email in Microsoft login...")
    
    ms_email_input = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='email'], input[name='loginfmt']"))
    )
    ms_email_input.clear()
    ms_email_input.send_keys(EMAIL)
    
    # Click Next button
    next_button = WebDriverWait(driver, 5).until(
        EC.element_to_be_clickable((By.XPATH, "//input[@type='submit' and @value='Next']"))
    )
    next_button.click()
    
    # Step 4: Enter password
    print("Step 4: Entering password...")
    print(f"Password length: {len(PASSWORD)} characters")
    time.sleep(1)  # Wait for page to fully load
    ms_password_input = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='password'], input[name='passwd']"))
    )
    # Just send keys directly without clearing
    ms_password_input.send_keys(PASSWORD)
    time.sleep(1)  # Brief pause after entering
    print("Password entered")
    driver.save_screenshot("/tmp/deskbird_password_entered.png")
    
    # Click Sign in button
    print("Clicking Sign in button...")
    signin_button = WebDriverWait(driver, 5).until(
        EC.element_to_be_clickable((By.XPATH, "//input[@type='submit' and @value='Sign in']"))
    )
    signin_button.click()
    print("Sign in button clicked")
    
    # Step 5: Handle post-password page (OTP or Stay signed in)
    print("Step 5: Waiting for next page after password...")
    time.sleep(3)  # Wait for next page to load
    print(f"Current URL: {driver.current_url}")
    driver.save_screenshot("/tmp/deskbird_after_password.png")
    
    # Check if OTP is required
    try:
        otp_input = driver.find_element(By.CSS_SELECTOR, "input[type='tel'], input[name='otc']")
        print("OTP page detected, fetching code from 1Password...")
        otp_code = get_1password_otp(OP_ITEM_NAME, OP_VAULT)
        print(f"OTP fetched: {otp_code[:3]}...")
        otp_input.clear()
        otp_input.send_keys(otp_code)
        
        # Click Verify button
        verify_button = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//input[@type='submit' and @value='Verify']"))
        )
        verify_button.click()
        print("OTP submitted")
    except:
        print("No OTP page found, checking for other prompts...")
        # Check for "Stay signed in?" prompt
        try:
            yes_button = driver.find_element(By.XPATH, "//input[@type='submit' and @value='Yes']")
            print("Found 'Stay signed in?' prompt, clicking Yes...")
            yes_button.click()
        except:
            print("No 'Stay signed in' prompt found either")
            pass
    
    # Wait for authentication to complete - popup should close automatically
    print("Waiting for popup to close after authentication...")
    WebDriverWait(driver, 30).until(
        lambda d: len(d.window_handles) == 1
    )
    print("Popup closed, switching to main window...")
    
    # Switch back to main window
    driver.switch_to.window(driver.window_handles[0])
    
    # Wait for redirect to complete on main window  
    WebDriverWait(driver, 30).until(
        lambda d: "login" not in d.current_url and "deskbird.com" in d.current_url
    )
    print(f"Authentication successful! Current URL: {driver.current_url}")
    
    # Step 6: Calculate next week's booking date
    today = datetime.now()
    days_ahead = 7 + (today.weekday() - today.weekday())  # Same day next week
    if days_ahead <= 0:
        days_ahead += 7
    booking_date = today + timedelta(days=7)  # Always book exactly 7 days ahead
    
    # Convert to epoch milliseconds for full day (7am to 7pm)
    start_of_day = booking_date.replace(hour=6, minute=0, second=0, microsecond=0)
    end_of_day = booking_date.replace(hour=18, minute=0, second=0, microsecond=0)
    start_time = int(start_of_day.timestamp() * 1000)
    end_time = int(end_of_day.timestamp() * 1000)
    
    # First navigate to the main booking dashboard to ensure sidebar loads
    print("Step 6a: Navigating to main booking dashboard...")
    driver.get(f"https://app.deskbird.com/office/{OFFICE_ID}/bookings/dashboard")
    time.sleep(5)  # Wait for initial load
    
    # Now navigate to the specific date
    booking_url = f"https://app.deskbird.com/office/{OFFICE_ID}/bookings/dashboard?floorId={FLOOR_ID}&viewType=card&areaType=flexDesk&startTime={start_time}&endTime={end_time}&isFullDay=true"
    
    print(f"Step 6b: Navigating to booking page for {booking_date.strftime('%Y-%m-%d')}...")
    driver.get(booking_url)
    
    # Wait for page to fully load - wait for desk cards to appear
    print("Waiting for desk availability to load...")
    time.sleep(10)  # Give the Angular app time to fully render
    
    # Wait for the main content area to load
    try:
        WebDriverWait(driver, 20).until(
            lambda d: len(d.page_source) > 10000  # Wait for substantial page content
        )
        print("Page content loaded")
    except:
        print("Warning: Page may not be fully loaded")
    
    # Wait for My Spaces widget to load (contains the Quick book button)
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, "//db-my-spaces"))
        )
        print("My Spaces widget loaded")
    except:
        print("Warning: My Spaces widget may not be loaded")
    
    driver.save_screenshot("/tmp/deskbird_booking_page.png")
    
    # Step 7: Click the first available "Quick book" button
    print("Step 7: Looking for booking button...")
    
    # Try different selectors in order of preference
    button_found = False
    selectors = [
        (By.CSS_SELECTOR, "a[data-testid='common--user-spaces-cards-quick-book']"),
        (By.XPATH, "//a[@data-testid='common--user-spaces-cards-quick-book']"),
        (By.XPATH, "//a[contains(text(), 'Quick book')]"),
        (By.XPATH, "//a[contains(., 'Quick book')]"),
        (By.XPATH, "//a[contains(@class, 'book-cta')]"),
    ]
    
    for by_method, selector in selectors:
        try:
            print(f"Trying {by_method} selector: {selector[:60]}...")
            quick_book_button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((by_method, selector))
            )
            print(f"Found button with {by_method} selector!")
            quick_book_button.click()
            print("Clicked 'Quick book' button!")
            button_found = True
            break
        except Exception as e:
            print(f"  Failed: {str(e)[:100]}")
            continue
    
    if not button_found:
        print("ERROR: Could not find booking button with any selector")
        print(f"Current URL: {driver.current_url}")
        print(f"Page source length: {len(driver.page_source)} characters")
        driver.save_screenshot("/tmp/deskbird_no_button_found.png")
        
        # Search for "book" in page source
        page_lower = driver.page_source.lower()
        if "book" in page_lower:
            print("\nFound 'book' in page source. Contexts:")
            import re
            matches = re.finditer(r'.{0,100}book.{0,100}', page_lower, re.IGNORECASE)
            for i, match in enumerate(matches):
                if i < 10:  # Show first 10 matches
                    print(f"  Match {i+1}: ...{match.group()}...")
        else:
            print("\n'book' not found anywhere in page source")
        
        print("\nPage source (first 5000 chars):")
        print(driver.page_source[:5000])
        raise Exception("Could not find Quick book button")
    
    # Step 8: Enable "Full day" toggle if it exists and is disabled
    print("Step 8: Checking for 'Full day' toggle...")
    time.sleep(2)  # Wait for booking modal/dialog to appear
    driver.save_screenshot("/tmp/deskbird_booking_modal.png")
    
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
                print(f"Trying toggle selector: {selector[:80]}...")
                full_day_toggle = WebDriverWait(driver, 3).until(
                    EC.presence_of_element_located((by_method, selector))
                )
                
                # Check if the toggle is already enabled
                is_checked = full_day_toggle.is_selected()
                print(f"Full day toggle found! Currently {'enabled' if is_checked else 'disabled'}")
                
                if not is_checked:
                    print("Enabling 'Full day' toggle...")
                    # Click the toggle to enable it
                    full_day_toggle.click()
                    time.sleep(1)
                    print("'Full day' toggle enabled!")
                    driver.save_screenshot("/tmp/deskbird_fullday_enabled.png")
                else:
                    print("'Full day' toggle is already enabled")
                
                toggle_found = True
                break
            except Exception as e:
                print(f"  Failed: {str(e)[:100]}")
                continue
        
        if not toggle_found:
            print("Warning: Could not find 'Full day' toggle - it may already be enabled by URL parameter or not present")
    except Exception as e:
        print(f"Warning: Error while looking for Full day toggle: {str(e)[:200]}")
        print("Continuing with booking...")
    
    # Wait a moment to ensure booking completes
    time.sleep(3)
    driver.save_screenshot("/tmp/deskbird_after_booking.png")
    print("Booking completed successfully!")
    
except Exception as e:
    print(f"Error occurred: {str(e)}")
    # Take a screenshot for debugging
    driver.save_screenshot("/tmp/deskbird_error.png")
    raise
finally:
    driver.quit()
