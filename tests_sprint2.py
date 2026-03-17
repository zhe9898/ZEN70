import asyncio
import subprocess
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from backend.main import app
from backend.ai_router import MULTIMODAL_TIMEOUT_SECONDS
from backend.sentinel.topology_sentinel import TopologySentinel
from pathlib import Path

print("==== Test 1: AI Router 206 Downgrade ====")
client = TestClient(app)

# We want to mock _forward_request in ai_router to hang so it triggers timeout.
# We also temporarily override MULTIMODAL_TIMEOUT_SECONDS inside the router.
import backend.ai_router as ai_r
ai_r.MULTIMODAL_TIMEOUT_SECONDS = 0.01

# We need to mock httpx.AsyncClient.send to sleep longer than 0.01s
async def mock_send(*args, **kwargs):
    await asyncio.sleep(0.5)
    return MagicMock()

with patch("backend.ai_router.http_client.send", side_effect=mock_send):
    # send a request to the universal proxy
    resp = client.post("/api/v1/ai/chat/completions", headers={"X-Capability-Target": "test_cap"})
    print(f"Status Code: {resp.status_code}")
    print(f"Response Content: {resp.text}")
    if resp.status_code == 206 and "热熔断" in resp.text:
        print("[PASS] Test 1: AI Router downgraded 504 -> 206 successfully.")
    else:
        print("[FAIL] Test 1.")

print("\n==== Test 2: D-State Docker Kill ====")
import backend.sentinel.topology_sentinel as topo
topo.logger = MagicMock()
sentinel = TopologySentinel()
sentinel.is_zombie = False
topo.CONTAINER_MAP["/mnt/fake"] = "zen70-fake"

def mock_run_hanging(*args, **kwargs):
    cmd = args[0]
    if "pause" in cmd:
        # Simulate hang by raising TimeoutExpired
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=3)
    elif "kill" in cmd:
        print(f"Mocking subprocess.run: Executing docker kill on {cmd[2]}")
        return MagicMock()
    return MagicMock()

with patch("subprocess.run", side_effect=mock_run_hanging) as mock_run:
    result = sentinel._docker_pause(Path("/mnt/fake"))
    if not result:
        # verify kill was called
        calls = mock_run.call_args_list
        kill_called = any(["kill" in call[0][0] for call in calls])
        if kill_called:
            print("[PASS] Test 2: D-state hang triggered docker kill escalation.")
        else:
            print("[FAIL] Test 2: Kill escalation not triggered.")
    else:
         print("[FAIL] Test 2: _docker_pause returned True unexpectedly.")
