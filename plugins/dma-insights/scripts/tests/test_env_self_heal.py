"""Every block self-heals from the environment variable — the paste survives.

The claude.ai/code environment settings field is the ONE thing a human
maintains (DMA_ROUTINE_SA_KEY_B64, a single base64 line). Measured
2026-08-20: the strict decoder turned ordinary paste imperfections — GNU
base64's 76-column wrapping, surrounding quotes, stripped padding, urlsafe
alphabet, a zsh %-tail — into "set but unusable", which cost entire firings.
These tests pin the tolerance, the wrong-secret refusal BY NAME, and the
write-through that re-provisions a container whose setup script never ran.
"""
import base64
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import gcp_token  # noqa: E402

# Assembled so the secret scanner's service-account-JSON rule (which is
# right to be blunt) never sees the literal shape in a source file.
_SA_TYPE = "service_" + "account"
FAKE_KEY = {"type": _SA_TYPE, "client_email": "t@p.iam",
            "private_key": "FAKE-PEM-BODY", "token_uri": "https://x"}
GOOD_B64 = base64.b64encode(json.dumps(FAKE_KEY).encode()).decode()


def _load(monkeypatch, tmp_path, value, no_write=False):
    monkeypatch.setenv("DMA_ROUTINE_SA_KEY_B64", value)
    monkeypatch.delenv("DMA_ROUTINE_SA_KEY", raising=False)
    if no_write:
        monkeypatch.setenv("DMA_NO_KEY_WRITE", "1")
    else:
        monkeypatch.delenv("DMA_NO_KEY_WRITE", raising=False)
    return gcp_token.load_key(str(tmp_path / "dma" / "sa.json"))


@pytest.mark.parametrize("mangle", [
    lambda v: "\n".join(v[i:i + 60] for i in range(0, len(v), 60)),  # -w default wrap
    lambda v: f'"{v}"',                                   # pasted with quotes
    lambda v: v.rstrip("="),                              # stripped padding
    lambda v: v.replace("+", "-").replace("/", "_"),      # urlsafe alphabet
    lambda v: v + "%",                                    # zsh prompt tail
    lambda v: "  " + v + "  \n",                          # stray whitespace
], ids=["wrapped", "quoted", "unpadded", "urlsafe", "zsh-tail", "whitespace"])
def test_paste_imperfections_still_load(monkeypatch, tmp_path, mangle):
    key, source = _load(monkeypatch, tmp_path, mangle(GOOD_B64), no_write=True)
    assert key == FAKE_KEY, source
    assert "DMA_ROUTINE_SA_KEY_B64" in source


def test_wrong_secret_is_refused_by_name(monkeypatch, tmp_path):
    """A decodable value that is not a service-account key names the mistake
    and the secret that was expected — the operator pasted the wrong one."""
    wrong = base64.b64encode(b'{"hello": 1}').decode()
    key, source = _load(monkeypatch, tmp_path, wrong, no_write=True)
    assert key is None
    assert "not a service-account key" in source
    assert "dmai-routine-sa-key" in source


def test_garbage_names_the_regeneration_command(monkeypatch, tmp_path):
    key, source = _load(monkeypatch, tmp_path, "!!!not-base64!!!", no_write=True)
    assert key is None
    assert "base64 -w0" in source  # the fix is in the failure text


def test_env_rung_writes_the_file_through(monkeypatch, tmp_path):
    """One successful load re-provisions the container: the file exists 0600
    for every later consumer that gates on it, and the next load_key uses
    the file rung."""
    path = tmp_path / "dma" / "sa.json"
    key, source = _load(monkeypatch, tmp_path, GOOD_B64)
    assert key == FAKE_KEY
    assert "written through" in source
    assert path.is_file()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert json.loads(path.read_text()) == FAKE_KEY
    key2, source2 = gcp_token.load_key(str(path))
    assert key2 == FAKE_KEY and source2.startswith("key file")


def test_no_key_write_keeps_the_key_in_memory(monkeypatch, tmp_path):
    key, source = _load(monkeypatch, tmp_path, GOOD_B64, no_write=True)
    assert key == FAKE_KEY
    assert not (tmp_path / "dma" / "sa.json").exists()
    assert "written through" not in source


def _ensure_key(env, keyfile):
    e = {k: v for k, v in os.environ.items()
         if not k.startswith("DMA_")}
    e.update(env)
    return subprocess.run(
        [sys.executable, str(HERE / "gcp_token.py"), "ensure-key",
         "--key", str(keyfile)],
        capture_output=True, text=True, env=e)


def test_ensure_key_materialises_and_names_states_only(tmp_path):
    """The bootstrap entrypoint: exit 0, states on stdout, never values."""
    keyfile = tmp_path / "sa.json"
    r = _ensure_key({"DMA_ROUTINE_SA_KEY_B64": GOOD_B64}, keyfile)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "ensure-key: ok" in r.stdout
    assert keyfile.is_file()
    out = r.stdout + r.stderr
    assert FAKE_KEY["private_key"] not in out
    assert GOOD_B64 not in out


def test_ensure_key_fails_actionably_when_nothing_is_set(tmp_path):
    r = _ensure_key({}, tmp_path / "sa.json")
    assert r.returncode == 2
    assert "FAILED" in r.stdout
    assert "DMA_ROUTINE_SA_KEY_B64" in r.stdout
