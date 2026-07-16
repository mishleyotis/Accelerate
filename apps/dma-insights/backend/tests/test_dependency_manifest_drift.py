"""Dependency manifest drift regression.

The 2026-05-28 audit found that pytesseract/pdf2image/Pillow were
installed directly via `pip install` in both Dockerfiles but were
NOT declared in `pyproject.toml`. That meant:

  - `pip install .` in dev/CI didn't pull them
  - `pip-audit` / dependency scanners didn't see them
  - any test exercising the OCR ladder skipped silently with
    ModuleNotFoundError or returned ("", 0) without surfacing the gap

Fix: declared them as `[ocr]` optional extras. This file pins both
sides of the contract:
  1. The `[ocr]` extras group exists with the three packages
     pinned to exactly the versions the Dockerfiles install.
  2. The Dockerfile versions and the extras versions don't drift
     (re-run this test after bumping either).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]  # backend/
APP_ROOT = BACKEND_ROOT.parent                       # dma-insights/
PYPROJECT = BACKEND_ROOT / "pyproject.toml"
BACKEND_DOCKERFILE = APP_ROOT / "infra" / "docker" / "backend.Dockerfile"
WORKER_DOCKERFILE = APP_ROOT / "infra" / "docker" / "worker.Dockerfile"


def _parse_ocr_extras() -> dict[str, str]:
    """Parse `[project.optional-dependencies].ocr = [...]` from
    pyproject.toml into {package_name: pinned_version}.

    Avoids a full TOML parser dependency by matching the literal
    bracketed list under the `ocr = [` heading -- the file lives in
    THIS repo, so format drift is detectable via test failure not via
    parser robustness.
    """
    text = PYPROJECT.read_text(encoding="utf-8")
    m = re.search(r'^ocr\s*=\s*\[(.*?)\]', text, re.MULTILINE | re.DOTALL)
    assert m, "ocr extras group not found in pyproject.toml"
    block = m.group(1)
    pkgs: dict[str, str] = {}
    for line in block.splitlines():
        line = line.strip().strip(',').strip('"').strip("'")
        if not line:
            continue
        if "==" in line:
            name, ver = line.split("==", 1)
            pkgs[name.strip()] = ver.strip().strip('"').strip("'")
    return pkgs


def _parse_dockerfile_pip_pins(path: Path) -> dict[str, str]:
    """Find all `"name==version"` pip arguments anywhere in a
    Dockerfile and return as {name: version}. Both Dockerfiles
    install the OCR trio with this shape."""
    text = path.read_text(encoding="utf-8")
    pkgs: dict[str, str] = {}
    for name, ver in re.findall(r'"([A-Za-z0-9_\-]+)==([0-9.]+)"', text):
        pkgs[name] = ver
    return pkgs


def test_ocr_extras_group_exists_and_pins_three_packages():
    extras = _parse_ocr_extras()
    assert set(extras) == {"pytesseract", "pdf2image", "Pillow"}, (
        f"ocr extras must contain exactly the OCR trio, got {set(extras)}"
    )


def test_backend_dockerfile_ocr_versions_match_extras():
    extras = _parse_ocr_extras()
    docker_pins = _parse_dockerfile_pip_pins(BACKEND_DOCKERFILE)
    for name, ver in extras.items():
        assert name in docker_pins, (
            f"backend.Dockerfile does not pin {name}; either remove from "
            f"the ocr extras group OR add the pin back to the Dockerfile."
        )
        assert docker_pins[name] == ver, (
            f"version drift for {name}: pyproject[ocr]={ver}, "
            f"backend.Dockerfile={docker_pins[name]}"
        )


def test_worker_dockerfile_ocr_versions_match_extras():
    extras = _parse_ocr_extras()
    docker_pins = _parse_dockerfile_pip_pins(WORKER_DOCKERFILE)
    for name, ver in extras.items():
        assert name in docker_pins, (
            f"worker.Dockerfile does not pin {name}; the OCR ladder in "
            f"app/services/parsers/deep_extract.py imports this package."
        )
        assert docker_pins[name] == ver, (
            f"version drift for {name}: pyproject[ocr]={ver}, "
            f"worker.Dockerfile={docker_pins[name]}"
        )


def test_backend_dockerfile_installs_tesseract_system_binary():
    text = BACKEND_DOCKERFILE.read_text(encoding="utf-8")
    assert "tesseract-ocr" in text, (
        "backend.Dockerfile must apt-install tesseract-ocr for the "
        "Python pytesseract package to call into the binary."
    )
    assert "poppler-utils" in text, (
        "backend.Dockerfile must apt-install poppler-utils for pdf2image."
    )


def test_worker_dockerfile_installs_tesseract_system_binary():
    text = WORKER_DOCKERFILE.read_text(encoding="utf-8")
    assert "tesseract-ocr" in text
    assert "poppler-utils" in text


def test_deep_extract_module_imports_only_optional_packages_at_call_time():
    """The OCR shim must import pytesseract/pdf2image LAZILY so a dev
    install without the [ocr] extra doesn't break unrelated imports
    of app.services.parsers.deep_extract."""
    deep_extract_path = (
        BACKEND_ROOT / "app" / "services" / "parsers" / "deep_extract.py"
    )
    if not deep_extract_path.exists():
        pytest.skip("deep_extract module not present in this branch")
    text = deep_extract_path.read_text(encoding="utf-8")
    # Top-level imports of OCR packages would crash on import in the
    # backend image without the [ocr] extra. They must be inside a
    # function/method body OR guarded by try/except.
    lines = text.splitlines()
    top_level_imports: list[str] = []
    for line in lines:
        stripped = line.lstrip()
        # Lines that are NOT indented and start with import/from.
        if line == stripped and (stripped.startswith("import ") or stripped.startswith("from ")):
            top_level_imports.append(stripped)
    forbidden = {"pytesseract", "pdf2image", "PIL"}
    for imp in top_level_imports:
        for f in forbidden:
            assert f not in imp, (
                f"deep_extract.py imports {f} at module top level: "
                f"`{imp}`. Move the import inside the OCR strategy "
                f"function so the module loads without the [ocr] extra."
            )
