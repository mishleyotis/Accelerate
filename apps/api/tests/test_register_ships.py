"""The enrichment register must be IN the image, and say so when it is not.

THE DEFECT, measured 2026-08-14 against the deployed API — not against a
fixture, against production.

`enrichment_status` was computed at read for five declared surfaces, carried by
the adapter, and rendered by the frontend. Every layer worked. It served on
none of them, because `packages/shared/enrichment_register.json` was not in the
api image — the Dockerfile copied `dma_api` and nothing else — and the loader
swallowed FileNotFoundError into an empty dict. An empty register declares no
surfaces, so every lookup missed and every section returned without its status.

The whole suite passed the entire time. In the repo the file is there.

Two things had to change and both are pinned below: the loader RAISES rather
than answering "nothing is declared" to a question it could not read, and Gate D
fails CI if a shared file the code reads is not staged into the image that reads
it. The gate is the durable half; this file is the one that fails fast and local
when someone deletes the staging step.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from dma_api import computed


@pytest.fixture(autouse=True)
def _fresh_register():
    """The register memoises, so every case starts from unread."""
    computed._ENRICHMENT_REGISTER = None
    yield
    computed._ENRICHMENT_REGISTER = None


def test_the_register_is_readable_from_the_repo_layout():
    reg = computed._enrichment_register()
    assert reg, "the register read as empty from the repo tree"
    assert "overview.firmographics" in reg
    assert "techstack.techstack" in reg


def test_a_missing_register_raises_rather_than_reading_as_empty():
    """The whole defect in one assertion. An unreadable contract is a
    DEPLOYMENT fault; answering it as "no surfaces are declared" converts it
    into a content answer, and a serving path must never make that
    translation."""
    computed._ENRICHMENT_REGISTER = None
    real = computed._register_paths
    computed._register_paths = lambda: [Path("/nonexistent/enrichment_register.json")]
    try:
        with pytest.raises(FileNotFoundError) as e:
            computed._enrichment_register()
        assert "not in this image" in str(e.value)
        assert "deploy.sh" in str(e.value), "the error must name the fix"
    finally:
        computed._register_paths = real


def test_the_failure_surfaces_as_computed_error_not_as_silence():
    """`apply` catches, so a broken register must show up on the section as a
    named computation failure — visible to the audit script on its first run —
    rather than as a section that quietly has no status."""
    computed._ENRICHMENT_REGISTER = None
    real = computed._register_paths
    computed._register_paths = lambda: [Path("/nonexistent/x.json")]

    class _Cur:
        def execute(self, *a, **k):
            pass

    data = {"fields": []}
    try:
        computed.apply(_Cur(), "overview", "firmographics", data,
                       {"run_id": "r", "entity_domain": None}, "e")
        assert "computed_error" in data
        assert "firmographics" in data["computed_error"]
        assert "enrichment_status" not in data
    finally:
        computed._register_paths = real


def test_the_image_path_is_looked_for_first():
    """deploy.sh stages the file beside the package as `shared/`. That path has
    to be tried BEFORE the repo layout, because in the image the repo layout
    resolves to `/` and would silently miss."""
    paths = [str(p) for p in computed._register_paths()]
    assert len(paths) >= 2
    assert paths[0].endswith("dma_api/../shared/enrichment_register.json") or \
        "/shared/enrichment_register.json" in paths[0], paths[0]
    assert "packages/shared" in paths[1], paths[1]


def test_the_dockerfile_copies_the_staging_directory():
    """Read the Dockerfile itself. The unit tests above all pass against the
    repo tree, which is precisely why none of them caught the original defect —
    only the build definition knows what ships."""
    df = (ROOT / "apps" / "api" / "Dockerfile").read_text()
    copies = [l.strip() for l in df.splitlines()
              if l.strip().upper().startswith("COPY ")]
    assert any("shared" in c for c in copies), (
        "apps/api/Dockerfile does not COPY the shared staging directory; the "
        f"image would not carry the register. COPY lines: {copies}")


def test_deploy_stages_the_register_into_the_api_context():
    deploy = (ROOT / "infra" / "deploy.sh").read_text()
    staged = [l.strip() for l in deploy.splitlines()
              if "cp " in l and "enrichment_register.json" in l
              and not l.strip().startswith("#")]
    assert staged, ("infra/deploy.sh never copies enrichment_register.json "
                    "into the api build context")


def test_every_surface_in_the_register_is_a_real_page_and_section():
    """A register key naming a section that does not exist would declare a
    surface nothing can ever satisfy, and the audit would report a permanent
    blocker nobody could close."""
    sys.path.insert(0, str(ROOT / "apps" / "mcp"))
    from dma_mcp.contracts import sections
    reg = json.loads(
        (ROOT / "packages" / "shared" / "enrichment_register.json").read_text())
    for key in (reg.get("surfaces") or reg):
        page, _, section = key.partition(".")
        assert section in sections(page), f"{key} is not a real section"


def test_register_paths_survive_a_shallow_image_layout():
    """In the image the module is /app/dma_api/computed.py — three parents.
    The first deploy built `here.parents[3]` EAGERLY and raised IndexError
    while constructing the list, before checking the image path that existed
    beside the package. Measured in production: every computed section carried
    `computed_error: ...IndexError` and enrichment_status served nowhere,
    while this suite passed — because in the repo the module is deep enough.
    The path list must be buildable from ANY depth."""
    import types
    real_file = computed.__file__
    try:
        computed.__file__ = "/app/dma_api/computed.py"
        paths = computed._register_paths()
        assert paths, "no candidate paths at image depth"
        assert str(paths[0]) == "/app/shared/enrichment_register.json", paths[0]
    finally:
        computed.__file__ = real_file
