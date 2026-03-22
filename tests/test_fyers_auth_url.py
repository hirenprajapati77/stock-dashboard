from urllib.parse import parse_qs, urlparse

from app.config import fyers_config
from app.services.fyers_service import FyersService


def test_get_login_url_uses_official_fyers_auth_endpoint():
    redirect_url = "https://stock-dashboard.example.com/api/v1/fyers/callback"

    auth_url = FyersService.get_login_url(redirect_url)
    parsed = urlparse(auth_url)
    query = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.netloc == "api-t1.fyers.in"
    assert parsed.path == "/api/v3/generate-authcode"
    assert query["response_type"] == ["code"]
    assert query["redirect_uri"] == [redirect_url]
    assert query["state"] == ["fyers_auth"]


def test_build_auth_url_preserves_client_id():
    redirect_url = "https://example.com/callback"

    auth_url = FyersService._build_auth_url(redirect_url)
    query = parse_qs(urlparse(auth_url).query)

    assert query["client_id"] == [fyers_config.app_id]
