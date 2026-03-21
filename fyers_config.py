import os

# Fyers API Credentials
app_id = "XAST342P8T-100"
secret_id = "Q5G3DG890Y"
redirect_url = "http://127.0.0.1:8000/api/v1/fyers/callback"

# Token storage path
token_file = os.path.join(os.path.dirname(__file__), "..", "data", "fyers_token.txt")
