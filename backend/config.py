"""
KOL Monitor Pro — Configuration Module (Cloud Edition)
Reads environment variables for Supabase, Railway, and Playwright.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# --- Supabase Database ---
DATABASE_URL = os.getenv("DATABASE_URL")

# --- Supabase Auth ---
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")

# --- API Server ---
API_PORT = int(os.getenv("PORT", os.getenv("API_PORT", "3001")))

# --- Playwright / Scraper ---
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"
SCRAPE_INTERVAL = 30 # Minutes (Hardcoded per user request)
SLOW_MO = 1000

# --- Frontend Origin (for CORS) ---
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
