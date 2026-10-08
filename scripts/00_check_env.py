"""Phase 1: verify conda env and core dependencies."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

REQUIRED_PACKAGES = (
    "dotenv",
    "pydantic",
    "pydantic_settings",
    "httpx",
    "pypdf",
    "numpy",
    "jieba",
    "rank_bm25",
)
ENV_SITE_HINT = "sec-rag"


def check_python_version() -> tuple[bool, str]:
    major, minor = sys.version_info[:2]
    if major == 3 and minor == 11:
        return True, f"Python {major}.{minor}.{sys.version_info.micro}"
    return False, f"Python {major}.{minor} (recommended: 3.11.x)"


def check_package_in_env(module_name: str) -> tuple[bool, str]:
    try:
        module = importlib.import_module(module_name)
    except ImportError:
        return False, "not installed"
    path = Path(getattr(module, "__file__", "") or "")
    if not path.exists():
        return False, "installed but path unknown"
    if ENV_SITE_HINT.replace("-", "_") in str(path).lower() or "sec-rag" in str(path).lower():
        return True, str(path)
    if "site-packages" in str(path) and "Roaming" not in str(path):
        return True, str(path)
    return False, f"loaded from user site (not conda env): {path}"


def check_project_layout() -> list[str]:
    required_dirs = [
        ROOT / "src" / "sec_rag",
        ROOT / "scripts",
        ROOT / "configs",
        ROOT / "storage" / "datasets" / "raw",
        ROOT / "storage" / "knowledge_base" / "documents",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required_dirs if not path.exists()]
    return missing


def main() -> int:
    print("SEC-RAG Phase 1 environment check")
    print("=" * 40)
    print(f"Project root: {ROOT}")
    print(f"Python exe:   {sys.executable}")

    ok_version, version_msg = check_python_version()
    print(f"\n[{'OK' if ok_version else 'WARN'}] {version_msg}")

    print("\nPackages:")
    all_packages_ok = True
    for package in REQUIRED_PACKAGES:
        ok, detail = check_package_in_env(package)
        all_packages_ok = all_packages_ok and ok
        print(f"  [{'OK' if ok else 'FAIL'}] {package}: {detail}")

    missing_dirs = check_project_layout()
    if missing_dirs:
        print("\nMissing directories:")
        for item in missing_dirs:
            print(f"  - {item}")
    else:
        print("\n[OK] Project layout looks good.")

    env_file = ROOT / ".env"
    if env_file.exists():
        print("\n[OK] .env exists (API config ready for later phases).")
    else:
        print("\n[INFO] .env not found. Copy .env.example to .env when you need API calls.")

    package_ok = False
    try:
        import sec_rag  # noqa: F401

        package_ok = True
        print(f"\n[OK] import sec_rag (version {sec_rag.__version__})")
    except ImportError as exc:
        print(f"\n[FAIL] import sec_rag: {exc}")

    if ok_version and all_packages_ok and not missing_dirs and package_ok:
        print("\nPhase 1 environment check: PASSED")
        return 0

    print("\nPhase 1 environment check: NEEDS ATTENTION")
    if not all_packages_ok:
        print("Tip: run `set PYTHONNOUSERSITE=1` then reinstall requirements.txt")
    if not package_ok:
        print("Tip: run scripts from project root: python scripts/00_check_env.py")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
