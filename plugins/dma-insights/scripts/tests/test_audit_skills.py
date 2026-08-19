#!/usr/bin/env python3
"""audit_skills.py argument handling.

`--help` used to be taken as a positional path and exit 1 with
"no skills directory at --help" — an auditor whose usage line was
unreachable. The positional default (the plugin's own skills/) and the
bad-path refusal are contract and must survive the argparse move.

    python3 test_audit_skills.py
    python3 -m pytest tests/
"""
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "audit_skills.py"


def _run(*args, timeout=60):
    return subprocess.run([sys.executable, str(SCRIPT), *args],
                          capture_output=True, text=True, timeout=timeout)


class HelpFlag(unittest.TestCase):
    def test_help_exits_zero_with_usage(self):
        proc = _run("--help")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("usage:", proc.stdout)
        self.assertIn("skills directory to audit", proc.stdout)

    def test_help_is_not_treated_as_a_path(self):
        proc = _run("--help")
        self.assertNotIn("no skills directory at --help",
                         proc.stdout + proc.stderr)


class PositionalRoot(unittest.TestCase):
    def test_bad_path_still_refuses_with_the_same_message(self):
        proc = _run("/no/such/dir")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("audit_skills: no skills directory at /no/such/dir",
                      proc.stderr)

    def test_empty_root_still_refuses_a_clean_audit_of_nothing(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            proc = _run(td)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("refusing", proc.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
