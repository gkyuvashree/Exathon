#!/usr/bin/env python3
"""
Environment doctor script for Exathon.
Checks Python version, imports every backend dependency,
and verifies node/npm presence; prints a clear PASS/FAIL table.
"""

import sys
import subprocess
import importlib
from pathlib import Path

# Ensure backend/.venv site-packages is in sys.path if invoked from an external Python interpreter
repo_root = Path(__file__).resolve().parent.parent
candidate_site_packages = [
    repo_root / "backend" / ".venv" / "Lib" / "site-packages",
    repo_root / "backend" / ".venv" / "lib" / "site-packages",
]
for p in (repo_root / "backend" / ".venv" / "lib").glob("python*/site-packages") if (repo_root / "backend" / ".venv" / "lib").exists() else []:
    candidate_site_packages.append(p)

for sp in candidate_site_packages:
    if sp.exists() and str(sp) not in sys.path:
        sys.path.insert(0, str(sp))

REQUIRED_BACKEND_MODULES = [
    ("fastapi", "FastAPI"),
    ("uvicorn", "Uvicorn"),
    ("pydantic", "Pydantic"),
    ("pytest", "Pytest"),
    ("httpx", "HTTPX"),
    ("duckdb", "DuckDB"),
    ("yaml", "PyYAML"),
    ("pandas", "Pandas"),
    ("numpy", "NumPy"),
    ("scipy", "SciPy"),
]

def check_python():
    version_info = sys.version_info
    ver_str = f"{version_info.major}.{version_info.minor}.{version_info.micro}"
    passed = (version_info.major == 3 and version_info.minor >= 10)
    return {
        "category": "Runtime",
        "check": "Python version >= 3.10",
        "detail": f"Python {ver_str}",
        "passed": passed,
    }

def check_module(mod_name, display_name):
    try:
        mod = importlib.import_module(mod_name)
        version = getattr(mod, "__version__", "installed")
        return {
            "category": "Backend Dep",
            "check": display_name,
            "detail": f"v{version}" if version != "installed" else "installed",
            "passed": True,
        }
    except Exception as e:
        return {
            "category": "Backend Dep",
            "check": display_name,
            "detail": f"ERROR: {str(e)[:35]}",
            "passed": False,
        }

def check_command(cmd, name):
    # On Windows, npm may be a .cmd file or powershell alias
    commands_to_try = [cmd]
    if sys.platform == "win32" and not cmd.endswith(".cmd") and not cmd.endswith(".exe"):
        commands_to_try.append(f"{cmd}.cmd")
        commands_to_try.append(f"{cmd}.exe")
    
    for c in commands_to_try:
        try:
            res = subprocess.run(
                [c, "--version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=(sys.platform == "win32"),
                check=False,
            )
            if res.returncode == 0:
                output = res.stdout.strip()
                if not output and res.stderr:
                    output = res.stderr.strip()
                return {
                    "category": "Tooling",
                    "check": name,
                    "detail": output.splitlines()[0] if output else "found",
                    "passed": True,
                }
        except FileNotFoundError:
            continue
        except Exception:
            continue

    return {
        "category": "Tooling",
        "check": name,
        "detail": "command not found",
        "passed": False,
    }

def main():
    results = []

    # 1. Python check
    results.append(check_python())

    # 2. Backend dependencies check
    for mod_name, display_name in REQUIRED_BACKEND_MODULES:
        results.append(check_module(mod_name, display_name))

    # 3. Node and npm checks
    results.append(check_command("node", "Node.js"))
    results.append(check_command("npm", "npm package manager"))

    # Print table
    col_w = {"cat": 14, "check": 24, "detail": 28, "status": 8}
    sep = "+" + "-" * (col_w["cat"] + 2) + "+" + "-" * (col_w["check"] + 2) + "+" + "-" * (col_w["detail"] + 2) + "+" + "-" * (col_w["status"] + 2) + "+"
    header = f"| {'Category':<{col_w['cat']}} | {'Check':<{col_w['check']}} | {'Details':<{col_w['detail']}} | {'Status':<{col_w['status']}} |"

    print("\n" + "=" * 80)
    print("                     EXATHON ENVIRONMENT DOCTOR REPORT")
    print("=" * 80)
    print(sep)
    print(header)
    print(sep)

    all_passed = True
    for r in results:
        status_str = "PASS" if r["passed"] else "FAIL"
        if not r["passed"]:
            all_passed = False
        cat_str = r["category"][:col_w["cat"]]
        chk_str = r["check"][:col_w["check"]]
        det_str = r["detail"][:col_w["detail"]]
        print(f"| {cat_str:<{col_w['cat']}} | {chk_str:<{col_w['check']}} | {det_str:<{col_w['detail']}} | {status_str:<{col_w['status']}} |")

    print(sep)
    pass_count = sum(1 for r in results if r["passed"])
    total_count = len(results)
    print(f"\nResult: {pass_count}/{total_count} checks passed.")
    if all_passed:
        print("ALL PASS: Environment is fully operational.\n")
        return 0
    else:
        print("FAIL: One or more checks failed. Please resolve above dependencies.\n")
        return 1

if __name__ == "__main__":
    sys.exit(main())
