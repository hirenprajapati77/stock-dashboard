import requests

BASE_URL = "http://localhost:8000/api/v1"

# A larger list of stocks to find edge cases (lagging sectors, low ADX)
TEST_WATCHLIST = [
    "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "ITC", "HUL",
    "AXISBANK", "LT", "SUNPHARMA", "TATAMOTORS", "BHARTIARTL", "KOTAKBANK",
    "ONGC", "WIPRO", "NTPC", "JSWSTEEL", "COALINDIA", "ADANIENT"
]

def test_full_validation():
    print("=== STARTING FULL API VALIDATION ===")
    
    # 1. Strategy Separation & Confidence Variation
    print("\n[1] Testing Strategy Separation (RELIANCE)...")
    confidences = {}
    for s in ["SR", "SWING", "DEMAND_SUPPLY"]:
        r = requests.get(f"{BASE_URL}/dashboard?symbol=RELIANCE&strategy={s}")
        data = r.json()
        conf = data["summary"]["confidence"]
        confidences[s] = conf
        print(f"    Mode: {s} | Confidence: {conf} | Signal: {data['summary']['trade_signal']}")

    if len(set(confidences.values())) > 1:
        print("    [PASS] Confidence variation detected.")
    else:
        print("    [FAIL] Confidence scores are identical.")

    # 2. Sector Guardrail & ADX Rule
    print("\n[2] Scanning Watchlist for Guardrail Enforcement...")
    lagging_found = False
    low_adx_found = False
    
    for symbol in TEST_WATCHLIST:
        # Check SR Mode
        r = requests.get(f"{BASE_URL}/dashboard?symbol={symbol}&strategy=SR")
        data = r.json()
        summary = data["summary"]
        sector_state = data.get("sector_info", {}).get("state", "NEUTRAL")
        adx = data.get("insights", {}).get("adx", 100)
        signal = summary["trade_signal"]
        
        # Test Sector Guard
        if sector_state == "LAGGING":
            lagging_found = True
            if signal == "ENTRY_READY":
                print(f"    [FAIL] {symbol} is LAGGING but shows ENTRY_READY!")
            else:
                print(f"    [PASS] {symbol} is LAGGING: Signal blocked to {signal}.")

        # Test ADX Guard in SR Mode
        if adx < 18:
            low_adx_found = True
            if signal == "ENTRY_READY":
                print(f"    [FAIL] {symbol} has low ADX ({adx}) but shows ENTRY_READY!")
            else:
                print(f"    [PASS] {symbol} has low ADX ({adx}): Signal blocked to {signal}.")

        if lagging_found and low_adx_found:
            break

    if not lagging_found:
        print("    [INFO] No LAGGING stocks found in current watchlist subset.")
    if not low_adx_found:
        print("    [INFO] No low ADX stocks found in current watchlist subset.")

    print("\n=== VALIDATION COMPLETE ===")

if __name__ == "__main__":
    test_full_validation()
