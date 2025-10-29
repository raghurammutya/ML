# run_kitesession.py
import logging
from pathlib import Path

from dotenv import load_dotenv

from session import KiteSession

def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    env_path = Path(__file__).resolve().parents[3] / "Kite_FOdata_scripts" / ".env"
    if env_path.exists():
        load_dotenv(env_path)

    # Option A: read credentials from environment variables:
    #   KITE_API_KEY, KITE_API_SECRET, KITE_USERNAME, KITE_PASSWORD, KITE_TOTP_KEY
    ks = KiteSession(account_id="default")

    # Option B: pass them directly (uncomment & fill, overrides env vars)
    # ks = KiteSession(credentials={
    #     "api_key": "your_api_key",
    #     "api_secret": "your_api_secret",
    #     "username": "your_user_id",
    #     "password": "your_password",
    #     "totp_key": "base32_totp_secret",
    # }, account_id="default")

    # If a valid cached token exists, it’ll be used; else it will auto-login.
    profile = ks.kite.profile()
    print(f"Logged in as: {profile.get('user_name')} ({profile.get('user_id')})")

    # Example: check available funds
    margins = ks.kite.margins()
    print("Net equity balance:", margins["equity"]["net"])

if __name__ == "__main__":
    main()
