import sys
from io import StringIO

import pytest

if __name__ == "__main__":
    out = StringIO()
    pytest.main(["tests/unit/test_data_integrity.py", "-v", "--tb=short"], stdout=out)
    result = out.getvalue()
    with open("pytest_exact_err.txt", "w", encoding="utf-8") as f:
        f.write(result)
    print("DONE WRITING")
