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
def get_1password_field(item_name, field_name):
    """Fetch a field from 1Password using the CLI"""
    try:
        result = subprocess.run(
            ["op", "item", "get", item_name, "--fields", f"label={field_name}"],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise ValueError(f"Failed to fetch {field_name} from 1Password: {e.stderr}")

def get_1password_otp(item_name):
    """Fetch TOTP code from 1Password using the CLI"""
    try:
        result = subprocess.run(
            ["op", "item", "get", item_name, "--otp"],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise ValueError(f"Failed to fetch OTP from 1Password: {e.stderr}")

# 1Password item name (configurable via env var)
OP_ITEM_NAME = os.environ.get("OP_ITEM_NAME", "Deskbird")

print(f"Fetching credentials from 1Password item: {OP_ITEM_NAME}")
EMAIL = get_1password_field(OP_ITEM_NAME, "username")
PASSWORD = get_1password_field(OP_ITEM_NAME, "password")
print(f"Email: {EMAIL}")
print("Password and OTP will be fetched as needed")

# Set up Chrome options for headless mode
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--window-size=1920x1080")
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
    
    # Step 2: Click "Sign in with Microsoft"
    print("Step 2: Clicking 'Sign in with Microsoft'...")
    microsoft_button = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Sign in with Microsoft')]"))
    )
    microsoft_button.click()
    
    # Step 3: Enter email in Microsoft login popup
    print("Step 3: Entering email in Microsoft login...")
    time.sleep(2)  # Wait for popup/redirect
    
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
    ms_password_input = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password'], input[name='passwd']"))
    )
    ms_password_input.send_keys(PASSWORD)
    
    # Click Sign in button
    signin_button = WebDriverWait(driver, 5).until(
        EC.element_to_be_clickable((By.XPATH, "//input[@type='submit' and @value='Sign in']"))
    )
    signin_button.click()
    
    # Step 5: Enter OTP
    print("Step 5: Fetching and entering OTP from 1Password...")
    time.sleep(2)  # Wait for OTP page to load
    
    # Fetch fresh OTP from 1Password
    otp_code = get_1password_otp(OP_ITEM_NAME)
    print(f"OTP fetched: {otp_code[:3]}...")
    
    otp_input = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='tel'], input[name='otc']"))
    )
    otp_input.clear()
    otp_input.send_keys(otp_code)
    
    # Click Verify button
    verify_button = WebDriverWait(driver, 5).until(
        EC.element_to_be_clickable((By.XPATH, "//input[@type='submit' and @value='Verify']"))
    )
    verify_button.click()
    
    # Wait for authentication to complete
    print("Waiting for authentication to complete...")
    WebDriverWait(driver, 30).until(
        EC.url_contains("app.deskbird.com")
    )
    print("Authentication successful!")
    
    # Step 6: Calculate next week's booking date
    today = datetime.now()
    days_ahead = 7 + (today.weekday() - today.weekday())  # Same day next week
    if days_ahead <= 0:
        days_ahead += 7
    booking_date = today + timedelta(days=7)  # Always book exactly 7 days ahead
    
    # Convert to epoch milliseconds for full day booking
    start_of_day = booking_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = booking_date.replace(hour=23, minute=59, second=59, microsecond=999999)
    start_time = int(start_of_day.timestamp() * 1000)
    end_time = int(end_of_day.timestamp() * 1000)
    
    booking_url = f"https://app.deskbird.com/office/14205/bookings/dashboard?floorId=41424&viewType=card&areaType=all&startTime={start_time}&endTime={end_time}&isFullDay=true"
    
    print(f"Step 6: Navigating to booking page for {booking_date.strftime('%Y-%m-%d')}...")
    driver.get(booking_url)
    
    # Step 7: Click the first "Quick book" button
    print("Step 7: Looking for 'Quick book' button...")
    quick_book_button = WebDriverWait(driver, 15).until(
        EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Quick book')]"))
    )
    quick_book_button.click()
    print("Clicked 'Quick book' button!")
    
    # Wait a moment to ensure booking completes
    time.sleep(3)
    print("Booking completed successfully!")
    
except Exception as e:
    print(f"Error occurred: {str(e)}")
    # Take a screenshot for debugging
    driver.save_screenshot("/tmp/deskbird_error.png")
    raise
finally:
    driver.quit()
