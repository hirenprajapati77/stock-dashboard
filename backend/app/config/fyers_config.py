import os


def normalize_redirect_url(url: str) -> str:
    """Only strip whitespace; trailing slashes are significant for Fyers."""
    if not url:
        return url
    return url.strip()


# Fyers API Credentials
app_id = os.environ.get("FYERS_APP_ID", "XAST342P8T-100")
secret_id = os.environ.get("FYERS_SECRET_ID", "U5RHOQ1292")


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

# Auth Proxy (to bypass IP blocks on Cloudflare/Fyers)
auth_proxy_url = os.environ.get("FYERS_AUTH_PROXY_URL", "").strip()

