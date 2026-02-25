import requests
import json

BASE_URL = "http://localhost:8000/api/v1"

def test_api_momentum_hits():
    print("\n--- Testing /momentum-hits ---")
    try:
        response = requests.get(f"{BASE_URL}/momentum-hits")
        if response.status_code == 200:
            data = response.json()
            hits = data.get("data", [])
            print(f"Found {len(hits)} hits.")
            if hits:
                # Sample the first hit
                hit = hits[0]
                print(f"Sample Hit ({hit.get('symbol')}):")
                print(f"  Confidence: {hit.get('confidence')}")
                print(f"  Forward 3D Return: {hit.get('forward3dReturn')}")
                print(f"  Quality Score: {hit.get('technical', {}).get('qualityScore')}")
                
                # Check for dynamic confidence
                grades = set(h.get("confidence") for h in hits if h.get("confidence"))
                print(f"Distinct grades found: {grades}")
                
                return hit
        else:
            print(f"Error: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Exception: {e}")
    return None

def test_api_market_summary():
    print("\n--- Testing /market-summary ---")
    try:
        response = requests.get(f"{BASE_URL}/market-summary")
        if response.status_code == 200:
            data = response.json().get("data", {})
            print("Summary Keys:", list(data.keys()))
            
            if "momentumLeaders" in data:
                print("Momentum Leaders:")
                print(json.dumps(data["momentumLeaders"], indent=2))
            else:
                print("✗ Missing momentumLeaders in summary.")
                
            return data
        else:
            print(f"Error: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Exception: {e}")
    return None

if __name__ == "__main__":
    hit_sample = test_api_momentum_hits()
    summary_sample = test_api_market_summary()
    
    # Save samples for final report if successful
    if hit_sample and summary_sample:
        with open("api_verification_results.json", "w") as f:
            json.dump({
                "momentum_hit_sample": hit_sample,
                "market_summary_sample": summary_sample
            }, f, indent=2)
        print("\nSamples saved to api_verification_results.json")
