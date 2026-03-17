import asyncio
import time
from fastapi.testclient import TestClient
from backend.main import app

def run_tests():
    client = TestClient(app)
    
    print("==== Test 1: PIN Bruteforce Freeze (M3.1) ====")
    # Send 6 bad requests to /api/v1/auth/pin/login
    count_429 = 0
    count_401 = 0
    for i in range(6):
        resp = client.post("/api/v1/auth/pin/login", json={"username": "admin", "pin": "0000"})
        if resp.status_code == 429:
            count_429 += 1
        elif resp.status_code == 401:
            count_401 += 1
            
    print(f"Got {count_401}x 401s, {count_429}x 429s.")
    if count_429 > 0 and count_401 == 5:
        print("[PASS] Test 1: PIN freeze lock engaged appropriately.")
    else:
        print("[FAIL] Test 1: PIN lock behavior incorrect.")

    print("\n==== Test 2: JWT Auto Rotation (M3.2) ====")
    # 1. Manually craft a JWT that is past 50% lifespan
    import backend.core.jwt as jwt_core
    from datetime import datetime, timezone
    
    # Fake token creation bypassing the usual time
    orig_now = jwt_core._now
    import datetime
    fixed_start = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=10)
    
    def fake_start(): return fixed_start
    jwt_core._now = fake_start
    
    token = jwt_core.create_access_token({"sub": "1", "username": "admin", "role": "admin"})
    
    # Restore now so decode_token thinks 10 minutes have passed (and total lifespan is 15 -> >50%)
    jwt_core._now = orig_now
    
    # Fake request to /sys/status just to pass thru decode_token dependency
    # But wait, sys/status does not use get_current_user. Let's use /api/v1/auth/users
    resp = client.get("/api/v1/auth/users", headers={"Authorization": f"Bearer {token}"})
    
    # if JWT rotate works, there should be an X-New-Token in response headers
    if "X-New-Token" in resp.headers:
        print("[PASS] Test 2: JWT 50% lifespan passed and X-New-Token was successfully injected.")
    else:
        print(f"[FAIL] Test 2: X-New-Token missing. Headers: {resp.headers}")

if __name__ == "__main__":
    run_tests()
