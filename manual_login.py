"""
manual_login.py
Use this script ONCE to log in to Google Scholar and save session cookies.
The main scraper (FastAPI or CLI) will reuse these cookies automatically.
"""

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import pickle
import os

COOKIES_FILE = "scholar_cookies.pkl"

def manual_login():
    print("🔐 Opening browser for manual login...")
    print("➡️  Please log in to your Google account and navigate to Google Scholar.")
    print("➡️  Once logged in, close the browser window.")
    print("➡️  Cookies will be saved automatically.\n")

    # Use visible browser for login
    options = Options()
    options.add_argument("--start-maximized")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)

    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
    except Exception:
        driver = webdriver.Chrome(options=options)

    try:
        driver.get("https://scholar.google.com")
        input("✅ Press ENTER after you've logged in and are on Google Scholar...")

        # Save cookies
        cookies = driver.get_cookies()
        with open(COOKIES_FILE, "wb") as f:
            pickle.dump(cookies, f)
        print(f"✅ Cookies saved to '{COOKIES_FILE}'")
    except Exception as e:
        print(f"❌ Error during login: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    manual_login()