import os


def normalize_redirect_url(url: str) -> str:
    """Strip whitespace and trailing slash so env/Fyers-console URLs match."""
    if not url:
        return url
    u = url.strip()
    if len(u) > 1 and u.endswith("/"):
        u = u.rstrip("/")
    return u


# Fyers API Credentials
app_id = os.environ.get("FYERS_APP_ID", "XAST342P8T-100")
secret_id = os.environ.get("FYERS_SECRET_ID", "Q5G3DG890Y")

# Auto-detect redirect URL based on environment
# Set FYERS_REDIRECT_URL env var on Render to your production URL
redirect_url = normalize_redirect_url(
    os.environ.get(
        "FYERS_REDIRECT_URL",
        "http://127.0.0.1:8000/api/v1/fyers/callback",
    )
)

# Token storage path (set FYERS_TOKEN_FILE on Render to a persistent disk path, e.g. /var/data/fyers_token.txt)
_default_token_dir = os.path.join(os.path.dirname(__file__), "..", "data")
token_file = os.path.abspath(
    os.environ.get("FYERS_TOKEN_FILE", os.path.join(_default_token_dir, "fyers_token.txt"))
)
