import subprocess
import os
import time

def run_tests():
    print("==== Test 1: release.sh Dirty Workspace Lockout (M4.3) ====")
    # The repository is currently dirty because we just modified ci.yml and release.sh natively.
    # Therefore, running release.sh should immediately fail.
    
    release_script = r"e:\ZEN70\scripts\release.sh"
    # Need to run it via bash
    result = subprocess.run(["git", "bash", release_script], capture_output=True, text=True, cwd=r"e:\ZEN70")
    # Actually just use bash directly
    result = subprocess.run(["bash", release_script], capture_output=True, text=True, cwd=r"e:\ZEN70")
    
    if "[FATAL] Workspace is dirty" in result.stdout or "[FATAL] Workspace is dirty" in result.stderr:
        print("[PASS] Test 1: Dirty workspace blocker triggered correctly.")
    else:
        print(f"[FAIL] Test 1: release.sh did not abort. Output:\n{result.stdout}\n{result.stderr}")

    print("\n==== Test 2: Bandit SAST Audit Trigger (M4.2) ====")
    # Temporarily inject a severe vulnerability into main.py (eval snippet)
    main_py_path = r"e:\ZEN70\backend\main.py"
    with open(main_py_path, "a", encoding="utf-8") as f:
        f.write('\n# TEST INJECTION\ndef test_vuln():\n    return eval("1+1")\n')
        
    try:
        bandit_run = subprocess.run(["bandit", "-r", r"e:\ZEN70\backend", "-ll"], capture_output=True, text=True)
        if "B307: evaluate" in bandit_run.stdout or "eval" in bandit_run.stdout:
             print("[PASS] Test 2: Bandit successfully detected the eval() injection.")
        else:
             print(f"[FAIL] Test 2: Bandit missed the injection. Output:\n{bandit_run.stdout}\n{bandit_run.stderr}")
    finally:
        # Revert the injection
        with open(main_py_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        with open(main_py_path, "w", encoding="utf-8") as f:
            f.writelines(lines[:-3]) # Remove the 3 lines we added
            
if __name__ == "__main__":
    run_tests()
