
import sys
import os

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from app.services.sector_service import SectorService

def test_logic():
    print("--- 1. Testing the METAL Case (SR < 0, RS > 0, RM > 0) ---")
    sr = -0.01  # Sector is down 1%
    br = -0.02  # Benchmark is down 2%
    prev_rs = 0 # Previous RS was 0
    # rs = sr - br = -0.01 - (-0.02) = 0.01 (Positive)
    # rm = rs - prev_rs = 0.01 - 0 = 0.01 (Positive)
    
    state = SectorService.calculate_state(sr, br, prev_rs)
    print(f"SR: {sr}, BR: {br}, RS: {0.01}, RM: {0.01} => State: {state}")
    assert state == "IMPROVING", f"Expected IMPROVING for Metal Case, got {state}"
    print("✅ Metal Case Success: Negative return with relative strength shows IMPROVING.")

    print("\n--- 2. Testing LEADING Guardrail (SR < 0, RS > 0, RM > 0) ---")
    # This specifically tests the guardrail logic
    state = SectorService.calculate_state(-0.005, -0.02, -0.015)
    # rs = -0.005 - (-0.02) = 0.015
    # rm = 0.015 - (-0.015) = 0.03
    # sector_return < 0
    print(f"SR: -0.005, RS: 0.015, RM: 0.03 => State: {state}")
    assert state == "IMPROVING", f"Guardrail FAILED: Expected IMPROVING, got {state}"
    print("✅ Guardrail Success: Sector cannot be LEADING if SR < 0.")

    print("\n--- 3. Testing LEADING (SR > 0, RS > 0, RM > 0) ---")
    state = SectorService.calculate_state(0.01, 0.005, 0.002)
    # rs = 0.01 - 0.005 = 0.005
    # rm = 0.005 - 0.002 = 0.003
    print(f"SR: 0.01, RS: 0.005, RM: 0.003 => State: {state}")
    assert state == "LEADING", f"Expected LEADING, got {state}"
    print("✅ LEADING Case Success: Positive return with momentum.")

    print("\n--- ALL BACKEND LOGIC VERIFIED ---")

if __name__ == "__main__":
    try:
        test_logic()
    except Exception as e:
        print(f"❌ VERIFICATION FAILED: {e}")
        sys.exit(1)
