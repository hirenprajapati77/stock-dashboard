import os

# Fyers API Credentials
app_id = os.environ.get("FYERS_APP_ID", "XAST342P8T-100")
secret_id = os.environ.get("FYERS_SECRET_ID", "Q5G3DG890Y")

# Auto-detect redirect URL based on environment
# Set FYERS_REDIRECT_URL env var on Render to your production URL
redirect_url = os.environ.get(
    "FYERS_REDIRECT_URL",
    "http://127.0.0.1:8000/api/v1/fyers/callback"  # fallback for local dev
)

# Token storage path
token_file = os.path.join(os.path.dirname(__file__), "..", "data", "fyers_token.txt")
