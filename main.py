"""
Google Scholar Email Scraper - ADVANCED EMAIL EXTRACTION
Enhanced with: OCR for images, Chrome PDF viewer parsing, multiple extraction methods
"""
import time
import re
import random
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import pandas as pd
import requests
from io import BytesIO
import PyPDF2
import socket
import dns.resolver
from difflib import SequenceMatcher
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import pickle
import os
import asyncio
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from fastapi.middleware.cors import CORSMiddleware

# Lock for thread-safe printing and file writing
print_lock = threading.Lock()



try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except:
    PDFPLUMBER_AVAILABLE = False
    print("⚠️  pdfplumber not available. Install: pip install pdfplumber")


class EmailValidator:
    """Validate email addresses"""

    @staticmethod
    def is_valid_format(email):
        """Check if email has valid format"""
        pattern = r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}$'
        return re.match(pattern, email) is not None

    @staticmethod
    def verify_domain(email):
        """Verify if email domain has MX records"""
        try:
            domain = email.split('@')[1]
            dns.resolver.resolve(domain, 'MX')
            return True
        except:
            return False

    @staticmethod
    def verify_smtp(email, timeout=10):
        """Verify email via SMTP (basic check)"""
        try:
            domain = email.split('@')[1]
            mx_records = dns.resolver.resolve(domain, 'MX')
            mx_host = str(mx_records[0].exchange)
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.settimeout(timeout)
            server.connect((mx_host, 25))
            server.recv(1024)
            server.send(b'HELO example.com\r\n')
            server.recv(1024)
            server.send(b'MAIL FROM: <test@example.com>\r\n')
            server.recv(1024)
            server.send(f'RCPT TO: <{email}>\r\n'.encode())
            response = server.recv(1024).decode()
            server.send(b'QUIT\r\n')
            server.close()
            return '250' in response or '251' in response
        except:
            return False

    @classmethod
    def validate_email(cls, email, check_smtp=False):
        """Full email validation"""
        result = {
            'email': email,
            'valid_format': False,
            'domain_valid': False,
            'smtp_valid': None,
            'overall_valid': False
        }
        result['valid_format'] = cls.is_valid_format(email)
        if not result['valid_format']:
            return result
        result['domain_valid'] = cls.verify_domain(email)
        if check_smtp and result['domain_valid']:
            result['smtp_valid'] = cls.verify_smtp(email)
        result['overall_valid'] = result['valid_format'] and result['domain_valid']
        if check_smtp:
            result['overall_valid'] = result['overall_valid'] and result['smtp_valid']
        return result


class AdvancedEmailExtractor:
    """Advanced email extraction using multiple methods"""

    @staticmethod
    def extract_from_text(text):
        """Extract emails from plain text with multiple patterns"""
        if not text:
            return []
        emails = set()
        # Pattern 1: Standard email
        pattern1 = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        emails.update(re.findall(pattern1, text, re.IGNORECASE))

        # Pattern 2: Email with spaces (e.g., "user @ domain.com")
        pattern2 = r'\b([A-Za-z0-9._%+-]+)\s*@\s*([A-Za-z0-9.-]+\.[A-Z|a-z]{2,})\b'
        for match in re.finditer(pattern2, text, re.IGNORECASE):
            emails.add(f"{match.group(1)}@{match.group(2)}")

        # Pattern 3: Email with [at] or (at)
        pattern3 = r'\b([A-Za-z0-9._%+-]+)\s*[\[\(]?\s*at\s*[\]\)]?\s*([A-Za-z0-9.-]+\.[A-Z|a-z]{2,})\b'
        for match in re.finditer(pattern3, text, re.IGNORECASE):
            emails.add(f"{match.group(1)}@{match.group(2)}")

        # Pattern 4: Email with [dot] or (dot)
        pattern4 = r'\b([A-Za-z0-9._%-]+)\s*@\s*([A-Za-z0-9-]+)\s*[\[\(]?\s*dot\s*[\]\)]?\s*([A-Za-z]{2,})\b'
        for match in re.finditer(pattern4, text, re.IGNORECASE):
            emails.add(f"{match.group(1)}@{match.group(2)}.{match.group(3)}")

        # Pattern 5: Contact sections
        contact_patterns = [
            r'(?:email|contact|correspondence)[\s:]+([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,})',
            r'([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,})[\s,;]*(?:corresponding author)',
        ]
        for pattern in contact_patterns:
            emails.update(re.findall(pattern, text, re.IGNORECASE))
        return list(emails)

    @staticmethod
    def extract_from_pdf_pdfplumber(pdf_bytes):
        """Extract text using pdfplumber (better for complex PDFs)"""
        if not PDFPLUMBER_AVAILABLE:
            return []
        try:
            pdf_file = BytesIO(pdf_bytes)
            emails = set()
            with pdfplumber.open(pdf_file) as pdf:
                for page in pdf.pages[:3]:
                    text = page.extract_text()
                    if text:
                        found = AdvancedEmailExtractor.extract_from_text(text)
                        emails.update(found)
            return list(emails)
        except Exception as e:
            print(f"        pdfplumber error: {str(e)[:50]}")
            return []

    @staticmethod
    def extract_from_pdf_pypdf2(pdf_bytes):
        """Extract text using PyPDF2 (fallback)"""
        try:
            pdf_file = BytesIO(pdf_bytes)
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            text = ""
            for page_num in range(min(3, len(pdf_reader.pages))):
                text += pdf_reader.pages[page_num].extract_text()
            return AdvancedEmailExtractor.extract_from_text(text)
        except Exception as e:
            print(f"        PyPDF2 error: {str(e)[:50]}")
            return []



    @staticmethod
    def filter_emails(emails):
        """Filter out false positives and system emails"""
        if not emails:
            return []
        exclude_domains = [
            'example.com', 'doi.org', 'ieee.org', 'acm.org',
            'springer.com', 'elsevier.com', 'wiley.com', 'arxiv.org',
            'researchgate.net', 'scholar.google.com', 'orcid.org',
            'crossref.org', 'nature.com', 'science.org', 'cell.com',
            'plos.org', 'frontiersin.org', 'mdpi.com', 'copyright',
            'permissions', 'reprint', 'editor', 'review', 'placeholder',
            'n@ure.com'  # Common OCR error
        ]
        exclude_prefixes = [
            'noreply', 'no-reply', 'donotreply', 'support', 'info',
            'admin', 'webmaster', 'postmaster', 'sales', 'marketing',
            'copyright', 'permissions', 'editorial', 'editor', 'review'
        ]
        valid_emails = []
        for email in emails:
            email_lower = email.lower()
            # Additional invalid checks
            if 'n@ure.com' in email_lower:
                continue
            if any(d in email_lower for d in exclude_domains):
                continue
            if any(email_lower.startswith(p) for p in exclude_prefixes):
                continue
            if email.count('_') > 2 or email.count('.') > 4:
                continue
            valid_emails.append(email)
        return list(dict.fromkeys(valid_emails))

    @staticmethod
    def calculate_similarity(name, email, threshold=0.5):
        """Calculate similarity between author name and email username"""
        if not name or not email:
            return False, 0.0
        try:
            name_lower = name.lower()
            email_user = email.split('@')[0].lower()
            # Normalized versions for ratio calculation (only letters)
            name_norm = re.sub(r'[^a-z]', '', name_lower)
            email_norm = re.sub(r'[^a-z]', '', email_user)
        except:
            return False, 0.0
        if not name_norm or not email_norm:
            return False, 0.0
        # 1. Direct containment of full normalized strings
        if name_norm in email_norm or email_norm in name_norm:
            return True, 1.0
        # 2. Check name parts (e.g. "Karthik" in "nkarthik")
        # Split original name by spaces or dots to get parts
        name_parts = re.split(r'[\s\.\-_]+', name_lower)
        for part in name_parts:
            # Clean part to just letters
            part_clean = re.sub(r'[^a-z]', '', part)
            # Only consider parts with significant length to avoid matching initials too aggressively
            if len(part_clean) < 3:
                continue
            if part_clean in email_norm:
                # Found a significant name part in the email
                return True, 0.90
        # 3. Fuzzy matching ratio
        ratio = SequenceMatcher(None, name_norm, email_norm).ratio()
        return ratio >= threshold, ratio


class GoogleScholarScraper:
    """Google Scholar scraper with advanced email extraction"""

    def __init__(self, topic, max_profiles=10, max_citations=20000, max_articles=4,
                 target_years=None, verify_emails=True, check_smtp=False, login_wait_time=150):
        self.topic = topic
        self.max_profiles = max_profiles
        self.max_citations = max_citations
        self.max_articles = max_articles
        self.target_years = target_years
        self.verify_emails = verify_emails
        self.check_smtp = check_smtp
        self.login_wait_time = login_wait_time
        self.results = []
        self.extractor = AdvancedEmailExtractor()
        # Optimize for speed
        chrome_options = Options()
        chrome_options.add_argument('--headless=new')  # Run in background
        chrome_options.add_argument('--blink-settings=imagesEnabled=false')  # Disable images
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_experimental_option('prefs', {
            'plugins.always_open_pdf_externally': False,
            'profile.default_content_setting_values.notifications': 2,
            'profile.managed_default_content_settings.images': 2  # Block images
        })
        chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        self.chrome_options = chrome_options
        self.driver = None  # Initialize lazily or for main search
        self.cookies_file = "scholar_cookies.pkl"
        # Single output file for the entire run
        self.output_file = f"scholar_emails_{self.topic.replace(' ', '_')}_{int(time.time())}.xlsx"

    def auto_login_with_timeout(self):
        """Automatically open browser for login with 150s timeout (no input() prompt)"""
        print("\n" + "=" * 70)
        print("🔐 AUTO LOGIN MODE")
        print("=" * 70)
        print(f"   A visible Chrome window will open.")
        print(f"   ⏳ You have {self.login_wait_time} seconds to log in to Google Scholar.")
        print("   Script will resume automatically once login is detected.")
        print("=" * 70)

        # Use visible browser for login
        login_options = Options()
        login_options.add_argument('--start-maximized')
        login_options.add_argument('--disable-blink-features=AutomationControlled')
        try:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=login_options)
        except:
            driver = webdriver.Chrome(options=login_options)

        try:
            driver.get("https://scholar.google.com")
            start_time = time.time()
            logged_in = False

            while time.time() - start_time < self.login_wait_time:
                try:
                    current_url = driver.current_url
                    page_source = driver.page_source
                    
                    # Check if we are back on scholar and NOT on a sign-in page
                    if "scholar.google" in current_url and "Sign in" not in page_source and "accounts.google.com" not in current_url:
                        print("\n✅ Login detected! Resuming scraper deeply...")
                        # self.human_delay(2, 4) # logic from reference, but function not available on 'self' here
                        time.sleep(random.uniform(2, 4))
                        logged_in = True
                        break
                    
                    # Also check if we see profile elements (sure sign of success)
                    if driver.find_elements(By.CLASS_NAME, "gs_ai_chpr") or driver.find_elements(By.CLASS_NAME, "gsc_1usr"):
                        print("\n✅ Login detected (profiles visible)! Resuming...")
                        logged_in = True
                        break
                    
                    time.sleep(1)
                except Exception as e:
                    time.sleep(1)
                time.sleep(2)

            if logged_in:
                cookies = driver.get_cookies()
                with open(self.cookies_file, "wb") as f:
                    pickle.dump(cookies, f)
                print(f"✅ Login successful! Cookies saved to {self.cookies_file}")
            else:
                print("❌ Login timeout! Exiting to avoid CAPTCHA traps.")
                return False
        except Exception as e:
            print(f"❌ Login setup failed: {e}")
            return False
        finally:
            driver.quit()
        return True

    def get_new_driver(self):
        """Create a new driver instance for a thread"""

        # REQUIRED FOR DOCKER / RENDER
        self.chrome_options.binary_location = os.environ.get(
            "CHROME_BIN", "/usr/bin/chromium"
        )

        # REQUIRED FLAGS
        self.chrome_options.add_argument("--no-sandbox")
        self.chrome_options.add_argument("--disable-dev-shm-usage")
        self.chrome_options.add_argument("--disable-gpu")
        self.chrome_options.add_argument("--window-size=1920,1080")
        #self.chrome_options.add_argument("--headless=new")

        try:
            service = Service(
                os.environ.get("CHROMEDRIVER_BIN", "/usr/bin/chromedriver")
            )
            driver = webdriver.Chrome(service=service, options=self.chrome_options)
        except Exception as e:
            raise RuntimeError(f"Chrome failed to start: {e}")

        # 🔒 Anti-detection tweaks (SAFE)
        driver.execute_cdp_cmd(
            "Network.setUserAgentOverride",
            {
                "userAgent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                )
            },
        )

        driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        # 🍪 Load cookies if available
        if os.path.exists(self.cookies_file):
            try:
                driver.get("https://scholar.google.com")
                with open(self.cookies_file, "rb") as f:
                    cookies = pickle.load(f)
                for cookie in cookies:
                    driver.add_cookie(cookie)
                driver.refresh()
            except Exception:
                pass

        return driver


    def human_delay(self, min_sec=1.5, max_sec=3):
        """Reduced delay for speed"""
        delay = random.uniform(min_sec, max_sec)
        time.sleep(delay)

    def random_scroll(self, driver):
        """Fast scroll"""
        try:
            scroll_amount = random.randint(300, 800)
            driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
            time.sleep(random.uniform(0.2, 0.5))
        except:
            pass

    def validate_and_display_emails(self, emails):
        if not emails:
            return []
        print(f"      🔍 Validating {len(emails)} email(s)...")
        validated = []
        for email in emails:
            if self.verify_emails:
                result = EmailValidator.validate_email(email, check_smtp=self.check_smtp)
                status = "✅" if result['overall_valid'] else "❌"
                details = f"Format: {'✓' if result['valid_format'] else '✗'}, Domain: {'✓' if result['domain_valid'] else '✗'}"
                if self.check_smtp and result['smtp_valid'] is not None:
                    details += f", SMTP: {'✓' if result['smtp_valid'] else '✗'}"
                print(f"        {status} {email} ({details})")
                if result['overall_valid']:
                    validated.append({
                        'email': email,
                        'validation': result
                    })
            else:
                print(f"        ℹ️  {email} (no validation)")
                validated.append({
                    'email': email,
                    'validation': None
                })
        return validated

    def search_scholars(self):
        # === AUTO SESSION CHECK + LOGIN ===
        cookies_valid = False
        if os.path.exists(self.cookies_file):
            test_driver = self.get_new_driver()
            try:
                test_driver.get("https://scholar.google.com")
                time.sleep(2)
                src = test_driver.page_source
                if "Sign in" not in src and "accounts.google.com" not in test_driver.current_url:
                    cookies_valid = True
            finally:
                test_driver.quit()

        if not cookies_valid:
            success = self.auto_login_with_timeout()
            if not success:
                return []

        print(f"\n🔍 Searching Google Scholar for: {self.topic}")
        search_url = f"https://scholar.google.com/citations?hl=en&view_op=search_authors&mauthors={self.topic.replace(' ', '+')}"
        print(f"  URL: {search_url}")
        print("  📡 Loading page...")
        # Initialize driver for search if not exists
        if not self.driver:
            self.driver = self.get_new_driver()
        self.wait = WebDriverWait(self.driver, 20)
        self.driver.get(search_url)
        self.human_delay(3, 5)
        self.random_scroll(self.driver)
        self.human_delay(1, 2)
        page_source = self.driver.page_source
        with open("scholar_debug.html", "w", encoding="utf-8") as f:
            f.write(page_source)
        print("  💾 Saved debug HTML to: scholar_debug.html")

        # Check for unusual traffic
        if "unusual traffic" in page_source.lower():
            print("\n" + "=" * 70)
            print("❌ BLOCKED: Google detected bot traffic")
            print("=" * 70)
            return []

        profiles = []
        skipped_count = 0
        print("\n🔎 Looking for scholar profiles...")
        max_pages = 100
        page = 0
        while page < max_pages:
            page += 1
            print(f"\n📄 Scanning page {page}...")
            found_on_page = 0
            try:
                profile_cards = self.driver.find_elements(By.CLASS_NAME, "gs_ai_chpr")
                print(f"    Found {len(profile_cards)} profiles on this page")
                for card in profile_cards:
                    try:
                        name_link = card.find_element(By.CSS_SELECTOR, "h3.gs_ai_name a")
                        name = name_link.text.strip()
                        profile_url = name_link.get_attribute("href")
                        if not name or not profile_url:
                            continue
                        citations = 0
                        try:
                            cit_element = card.find_element(By.CLASS_NAME, "gs_ai_cby")
                            cit_text = cit_element.text
                            match = re.search(r'(\d[\d,]*)', cit_text)
                            if match:
                                citations = int(match.group(1).replace(',', ''))
                        except:
                            pass
                        affiliation = ""
                        try:
                            aff_element = card.find_element(By.CLASS_NAME, "gs_ai_aff")
                            affiliation = aff_element.text.strip()
                        except:
                            pass
                        print(f"    ✓ {name} - {citations:,} citations")
                        if citations < self.max_citations:
                            profiles.append({
                                'name': name,
                                'profile_url': profile_url,
                                'citations': citations,
                                'affiliation': affiliation
                            })
                            found_on_page += 1
                            print(f"      ✨ MATCH! Added to list.")
                        else:
                            skipped_count += 1
                            print(f"      ✗ Skipped (too many citations)")
                    except Exception as e:
                        continue
            except Exception as e:
                print(f"    Error reading profiles: {e}")

            # Check if we have enough profiles
            if len(profiles) >= self.max_profiles:
                print(f"\n✅ Found {len(profiles)} profiles matched criteria. Stopping search.")
                break

            # Try to go to next page
            try:
                print("    Trying to find 'Next' button...")
                next_button = None
                # Selector strategy names for debugging
                strategies = [
                    (By.CSS_SELECTOR, "button[aria-label='Next']"),
                    (By.CSS_SELECTOR, ".gs_btnPR"),
                    (By.XPATH, "//button[@aria-label='Next']"),
                    (By.XPATH, "//span[@class='gs_ico_nav_next']/parent::*"),
                    (By.XPATH, "//b[text()='Next']/parent::*")
                ]
                for by, selector in strategies:
                    try:
                        elements = self.driver.find_elements(by, selector)
                        for el in elements:
                            if el.is_displayed():
                                # Check if disabled
                                if el.get_attribute("disabled") or "gs_btn_dsbl" in el.get_attribute("class"):
                                    print("    Next button is disabled (end of results).")
                                    next_button = None  # Explicitly set to None to trigger break
                                    break
                                next_button = el
                                print(f"    ✓ Found 'Next' button using: {selector}")
                                break
                        if next_button:
                            break
                    except:
                        continue

                if next_button:
                    print("  ➡️  Navigating to next page...")
                    next_button.click()
                    self.human_delay(3, 5)
                else:
                    print("  ⏹️  No 'Next' button found or disabled. End of results.")
                    break
            except Exception as e:
                print(f"  ⚠️  Pagination failed: {e}")
                break

        if len(profiles) == 0:
            print("\n❌ NO PROFILES FOUND after scanning pages")
            if skipped_count > 0:
                print(f"💡 HINT: Found {skipped_count} profiles but all were skipped because they had > {self.max_citations} citations.")
                print(f"👉 Try increasing 'max_citations' in your request (e.g., to 50000).")
        else:
            print(f"\n✅ Total found: {len(profiles)} profiles")
        return profiles

    def get_articles(self, profile_url, driver):
        with print_lock:
            print(f"  📄 Fetching articles...")
        driver.get(profile_url)
        self.human_delay(2, 4)
        self.random_scroll(driver)
        self.human_delay(1, 2)
        candidates = []
        try:
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "gsc_a_b")))
            rows = driver.find_elements(By.CLASS_NAME, "gsc_a_tr")
            with print_lock:
                print(f"    Found {len(rows)} articles on profile")
            # 1. Collect ALL candidates matches first
            for i, row in enumerate(rows):
                try:
                    # Extract year first
                    year_text = ""
                    try:
                        year_elem = row.find_element(By.CLASS_NAME, "gsc_a_y")
                        year_text = year_elem.text.strip()
                    except:
                        pass
                    # Filter if target_years is set
                    if self.target_years:
                        if not year_text or (year_text not in self.target_years):
                            continue
                    title_elem = row.find_element(By.CLASS_NAME, "gsc_a_at")
                    title = title_elem.text.strip()
                    article_page_url = title_elem.get_attribute("href")
                    pdf_url = None
                    try:
                        pdf_container = row.find_element(By.CLASS_NAME, "gs_ggs")
                        pdf_link = pdf_container.find_element(By.TAG_NAME, "a")
                        pdf_url = pdf_link.get_attribute("href")
                    except:
                        pass
                    candidates.append({
                        'title': title,
                        'pdf_url': pdf_url,
                        'article_page_url': article_page_url,
                        'year': year_text,
                        'original_index': i
                    })
                except Exception as e:
                    continue
            # 2. Sort candidates
            # Priority: Year (Desc), then Original Index (Asc)
            # If target_years is set, we want to prioritize latest years (2025, 2024...)
            if self.target_years:
                candidates.sort(key=lambda x: (x['year'], -x['original_index']), reverse=True)
            # 3. Select top N
            selected = candidates[:self.max_articles]
            with print_lock:
                print(f"    🔍 Filtered down to {len(selected)} (target: {self.max_articles}) starting with year {selected[0]['year'] if selected else 'N/A'}")
            for article in selected:
                has_pdf = "(has PDF)" if article['pdf_url'] else "(will check page)"
                # print(f"    ✓ {article['title'][:60]}... (Year: {article['year']}) {has_pdf}")
            return selected
        except Exception as e:
            print(f"    ⚠️  Error loading articles: {e}")
            return []

    def extract_emails_from_pdf_advanced(self, pdf_url, driver):
        try:
            # print(f"      📥 Downloading PDF from: {pdf_url[:80]}...")
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(pdf_url, headers=headers, timeout=30, allow_redirects=True)
            if response.status_code != 200:
                # print(f"      ⚠️  HTTP {response.status_code}")
                return [], None
            pdf_bytes = response.content
            all_emails = set()
            # print(f"      📖 Method 1: pdfplumber extraction...")
            emails = self.extractor.extract_from_pdf_pdfplumber(pdf_bytes)
            if emails:
                # print(f"      ✓ Found {len(emails)} email(s) via pdfplumber")
                all_emails.update(emails)
            if not all_emails:
                # print(f"      📖 Method 2: PyPDF2 extraction...")
                emails = self.extractor.extract_from_pdf_pypdf2(pdf_bytes)
                if emails:
                    # print(f"      ✓ Found {len(emails)} email(s) via PyPDF2")
                    all_emails.update(emails)

            filtered = self.extractor.filter_emails(list(all_emails))
            if filtered:
                with print_lock:
                    print(f"      📧 TOTAL: {len(filtered)} valid email(s) from PDF")
                return filtered, pdf_url
            return [], None
        except Exception as e:
            print(f"      ⚠️  PDF Error: {str(e)[:80]}")
            return [], None

    def extract_emails_from_chrome_pdf(self, pdf_url, driver):
        try:
            # print(f"      🌐 Opening PDF in Chrome viewer...")
            driver.get(pdf_url)
            self.human_delay(3, 5)
            # print(f"      📄 Extracting text from Chrome PDF viewer...")
            try:
                page_text = driver.find_element(By.TAG_NAME, "body").text
                emails = self.extractor.extract_from_text(page_text)
                if emails:
                    filtered = self.extractor.filter_emails(emails)
                    if filtered:
                        with print_lock:
                            print(f"      📧 Found {len(filtered)} email(s) from Chrome PDF viewer")
                        return filtered, pdf_url
            except:
                pass
            try:
                js_text = driver.execute_script("""
                    let text = '';
                    let elements = document.querySelectorAll('*');
                    elements.forEach(el => {
                        if (el.textContent) text += el.textContent + ' ';
                    });
                    return text;
                """)
                emails = self.extractor.extract_from_text(js_text)
                if emails:
                    filtered = self.extractor.filter_emails(emails)
                    if filtered:
                        with print_lock:
                            print(f"      📧 Found {len(filtered)} email(s) via JavaScript extraction")
                        return filtered, pdf_url
            except:
                pass
            return [], None
        except Exception as e:
            # print(f"      ⚠️  Chrome PDF Error: {str(e)[:80]}")
            return [], None

    def extract_emails_from_article_page(self, article_page_url, driver):
        try:
            # print(f"      🌐 Opening article page...")
            driver.get(article_page_url)
            self.human_delay(1.5, 3)
            page_text = driver.find_element(By.TAG_NAME, "body").text
            emails = self.extractor.extract_from_text(page_text)
            if emails:
                filtered = self.extractor.filter_emails(emails)
                if filtered:
                    with print_lock:
                        print(f"      📧 Found {len(filtered)} email(s) on article page")
                    return filtered, article_page_url
            # print(f"      🔗 Checking external PDF/full-text links...")
            try:
                links = driver.find_elements(By.CSS_SELECTOR, "a[href*='pdf'], a[href*='full'], a.gsc_oci_title_link")
                for link in links[:3]:
                    try:
                        url = link.get_attribute("href")
                        if not url or 'scholar.google' in url:
                            continue
                        # print(f"        → Checking: {url[:70]}...")
                        if url.endswith('.pdf') or 'pdf' in url.lower():
                            emails, source = self.extract_emails_from_pdf_advanced(url, driver)
                            if emails:
                                return emails, source
                        else:
                            driver.get(url)
                            self.human_delay(1, 2)
                            page_text = driver.find_element(By.TAG_NAME, "body").text
                            emails = self.extractor.extract_from_text(page_text)
                            if emails:
                                filtered = self.extractor.filter_emails(emails)
                                if filtered:
                                    with print_lock:
                                        print(f"        📧 Found {len(filtered)} email(s)")
                                    return filtered, url
                    except:
                        continue
            except:
                pass
            return [], None
        except Exception as e:
            # print(f"      ⚠️  Page Error: {str(e)[:80]}")
            return [], None

    def process_scholar(self, profile):
        # Create a new driver for this thread
        driver = self.get_new_driver()
        try:
            with print_lock:
                print(f"\n{'=' * 70}")
                print(f"Start Processing: {profile['name']}")
                print(f"   Citations: {profile['citations']:,}")
                if profile['affiliation']:
                    print(f"   Affiliation: {profile['affiliation']}")
                print('=' * 70)
            articles = self.get_articles(profile['profile_url'], driver)
            if not articles:
                # print("  ❌ No articles found")
                driver.quit()
                return None
            # print(f"  ✅ Found {len(articles)} articles to check")
            all_emails = []
            email_sources = []
            for i, article in enumerate(articles):
                # print(f"\n[{i+1}/{len(articles)}] {article['title'][:60]}...")
                emails = []
                source_url = None
                if article['pdf_url']:
                    emails, source_url = self.extract_emails_from_pdf_advanced(article['pdf_url'], driver)
                if not emails:
                    emails, source_url = self.extract_emails_from_chrome_pdf(article['pdf_url'], driver)
                if not emails and article['article_page_url']:
                    emails, source_url = self.extract_emails_from_article_page(article['article_page_url'], driver)
                if emails:
                    validated = self.validate_and_display_emails(emails)
                    if validated:
                        for v in validated:
                            all_emails.append(v['email'])
                            email_sources.append({
                                'email': v['email'],
                                'article': article['title'],
                                'source_url': source_url or 'Unknown',
                                'validation': v['validation']
                            })
                time.sleep(random.uniform(0.5, 1.5))
            if not all_emails:
                # print("  ❌ No valid emails found in any article")
                driver.quit()
                return None
            unique_emails = list(dict.fromkeys(all_emails))
            with print_lock:
                print(f"\n✅ FOUND {profile['name']} : {len(unique_emails)} UNIQUE EMAIL(S):")
            similar_emails = []
            for email in unique_emails:
                source_info = next((s for s in email_sources if s['email'] == email), None)
                source_display = source_info['source_url'][:60] if source_info else "Unknown"
                # Check similarity
                is_similar, score = self.extractor.calculate_similarity(profile['name'], email)
                similarity_tag = f"🌟 (Score: {score:.2f})" if is_similar else ""
                if is_similar:
                    similar_emails.append(email)
                print(f"     📧 {email} {similarity_tag}")
                print(f"        └─ Source: {source_display}")
            result = {
                'Name': profile['name'],
                'Primary_Email': unique_emails[0],
                'All_Emails': ', '.join(unique_emails),
                'Similar_Emails': ', '.join(similar_emails) if similar_emails else "None",
                'Email_Count': len(unique_emails),
                'Citations': profile['citations'],
                'Affiliation': profile['affiliation'],
                'Profile_URL': profile['profile_url'],
                'Email_Sources': '\n'.join([f"{s['email']}: {s['source_url']}" for s in email_sources])
            }
            driver.quit()
            return result
        except Exception as e:
            with print_lock:
                print(f"❌ Error processing {profile['name']}: {e}")
            driver.quit()
            return None

    def save_results_to_excel(self):
        if self.results:
            try:
                df = pd.DataFrame(self.results)
                # Use the consistent single filename
                df.to_excel(self.output_file, index=False)
                with print_lock:
                    print("\n" + "=" * 70)
                    print(f"✅ COMPLETED! Found emails for {len(self.results)} scholar(s)")
                    print(f"📁 Saved to: {self.output_file}")
                    print("=" * 70)
                return self.output_file
            except Exception as e:
                with print_lock:
                    print(f"❌ Error saving Excel: {e}")
                return None
        else:
            return None

    def run(self):
        print("\n" + "=" * 70)
        print("🚀 Google Scholar Email Scraper - 4X FASTER TURBO MODE")
        print("=" * 70)

        # Auto-login flow replaces manual input
        print(f"⚙️  Email Verification: {'ON' if self.verify_emails else 'OFF'}")
        print(f"⚙️  SMTP Check: {'ON' if self.check_smtp else 'OFF'}")
        print(f"⚙️  Headless Mode: ON (Background Processing)")
        print(f"⚙️  Parallel Threads: 3")
        print("=" * 70)

        try:
            profiles = self.search_scholars()
            # Close the search driver to free resources
            if self.driver:
                self.driver.quit()
                self.driver = None

            if not profiles:
                print("\n❌ No profiles to process")
                return {"error": "No profiles found"}

            print(f"\n🚀 Starting Parallel Processing of {len(profiles)} profiles with 3 threads...")
            print("   This might take some CPU power. Please wait...")

            # Use ThreadPoolExecutor for parallel processing
            max_workers = 5
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all tasks
                future_to_profile = {executor.submit(self.process_scholar, profile): profile for profile in profiles}
                # Process as they complete
                for future in as_completed(future_to_profile):
                    profile = future_to_profile[future]
                    try:
                        result = future.result()
                        if result:
                            self.results.append(result)
                            # Data is collected in self.results, no need to save incrementally to file
                    except Exception as exc:
                        print(f"Profile {profile['name']} generated an exception: {exc}")

            # Save to Excel before returning
            #self.save_results_to_excel()
            
            # Final Summary
            print("\n" + "=" * 70)
            print("✅ ALL TASKS COMPLETED")
            print(f"Total Profiles With Mail Scraped: {len(self.results)}")
            # We return the list of data directly now
            return {"results": self.results, "total_profiles": len(self.results)}

        except KeyboardInterrupt:
            print("\n⚠️  Stopped by user")
            # Return whatever we have so far
            return {"results": self.results, "total_profiles": len(self.results)}
        except Exception as e:
            print(f"\n❌ IDK ERROR OCCURRED: {e}")
            return {"error": str(e)}
        finally:
            print("\n🔒 Process finished!")
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass
            print("✅ Done!")


# ========================
# FASTAPI INTEGRATION
# ========================

app = FastAPI(title="Google Scholar Email Scraper API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # allow all origins (safe for internal tools)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ScrapeRequest(BaseModel):
    topic: str
    max_profiles: int = 10
    max_citations: int = 20000
    max_articles: int = 4
    target_years: Optional[List[str]] = None
    verify_emails: bool = True
    check_smtp: bool = False


@app.post("/scrape")
async def scrape_scholars(request: ScrapeRequest):
    def run_scraper():
        scraper = GoogleScholarScraper(
            topic=request.topic,
            max_profiles=request.max_profiles,
            max_citations=request.max_citations,
            max_articles=request.max_articles,
            target_years=request.target_years,
            verify_emails=request.verify_emails,
            check_smtp=request.check_smtp,
            login_wait_time=150
        )
        return scraper.run()

    loop = asyncio.get_event_loop()
    # ✅ FIXED: Use ThreadPoolExecutor (imported at top)
    with ThreadPoolExecutor() as pool:
        result = await loop.run_in_executor(pool, run_scraper)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return {
        "message": "Scraping completed successfully",
        "data": result["results"],
        "total_profiles_with_emails": result["total_profiles"]
    }


@app.get("/health")
def health_check():
    return {
        "status": "OK",
        "cookies_available": os.path.exists("scholar_cookies.pkl")
    }