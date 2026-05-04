import requests
import json

try:
    response = requests.get("http://localhost:8000/api/v1/momentum-hits?timeframe=1D")
    if response.status_code == 200:
        data = response.json()
        if isinstance(data, list) and len(data) > 0:
            first_hit = data[0]
            print(f"Symbol: {first_hit.get('symbol')}")
            print(f"Grade: {first_hit.get('grade')}")
            print(f"Confidence: {first_hit.get('confidence')}")
            print(f"Action: {first_hit.get('action')}")
            
            decision = first_hit.get('decision')
            if decision:
                print("\nV5 Decision Object Found:")
                print(f"Meta Score: {decision.get('meta_score', {}).get('meta_score')}")
                print(f"Final Decision: {decision.get('meta_score', {}).get('final_decision')}")
            else:
                print("\nERROR: No V5 Decision Object found in hit data.")
        else:
            print(f"No hits found. Data: {data}")
    else:
        print(f"Error: Status Code {response.status_code}")
except Exception as e:
    print(f"Exception: {e}")
