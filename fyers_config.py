import os


def normalize_redirect_url(url: str) -> str:
    """Strip whitespace and trailing slash so env/Fyers-console URLs match."""
    if not url:
        return url
    u = url.strip()
    if len(u) > 1 and u.endswith("/"):
        u = u.rstrip("/")
    return u


# Fyers API Credentials (prefer env; defaults for local dev only)
app_id = os.environ.get("FYERS_APP_ID", "XAST342P8T-100")
secret_id = os.environ.get("FYERS_SECRET_ID", "Q5G3DG890Y")
redirect_url = normalize_redirect_url(
    os.environ.get(
        "FYERS_REDIRECT_URL",
        "http://127.0.0.1:8000/api/v1/fyers/callback",
    )
)

# Token path — prefer FYERS_TOKEN_FILE for Render persistent disk
_default_token_dir = os.path.join(os.path.dirname(__file__), "backend", "app", "data")
token_file = os.path.abspath(
    os.environ.get(
        "FYERS_TOKEN_FILE",
        os.path.join(_default_token_dir, "fyers_token.txt"),
    )
)
