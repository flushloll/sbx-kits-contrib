"""Run: python3 -m unittest discover -s hermes-agent/tests -v"""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
WORKLOAD = ROOT / "hermes-agent/files/home/.local/bin/hermes-codex-proxy-env.py"
MIXIN = ROOT / "hermes-agent-mixin/files/home/.local/bin/hermes-codex-proxy-env.py"


class CodexProxyEnvironmentTest(unittest.TestCase):
    def invoke(self, script: Path, home: Path, *, upper: str = "", lower: str = "") -> None:
        env = os.environ.copy()
        env["NO_PROXY"] = upper
        env["no_proxy"] = lower
        subprocess.run([sys.executable, str(script), str(home)], env=env,
                       check=True, capture_output=True, text=True)

    def test_workload_and_mixin_helpers_match(self):
        self.assertEqual(WORKLOAD.read_bytes(), MIXIN.read_bytes())

    def test_default_adds_scoped_host_and_localhost(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            self.invoke(WORKLOAD, home)
            text = (home / ".env").read_text()
            for key in ("NO_PROXY", "no_proxy"):
                line = next(line for line in text.splitlines() if line.startswith(key + "="))
                values = line.partition("=")[2].split(",")
                for expected in ("localhost", "127.0.0.1", "::1", "chatgpt.com"):
                    self.assertIn(expected, values)
                self.assertNotIn("api.openai.com", values)
            self.assertEqual((home / ".env").stat().st_mode & 0o777, 0o600)

    def test_preserves_credentials_existing_exclusions_and_comments(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            path = home / ".env"
            path.write_text('OPENAI_API_KEY=a-placeholder\nNO_PROXY="foo.internal" # keep\n'
                            'no_proxy=bar.internal\n# my comment\n')
            self.invoke(MIXIN, home, upper="baz.internal", lower="qux.internal")
            text = path.read_text()
            for expected in ("OPENAI_API_KEY=a-placeholder", "# my comment", "# keep",
                             "foo.internal", "bar.internal", "baz.internal", "qux.internal"):
                self.assertIn(expected, text)
            self.assertEqual(text.count("chatgpt.com"), 2)

    def test_idempotent_on_subsequent_startups(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            self.invoke(WORKLOAD, home, upper="host.test,chatgpt.com")
            before = (home / ".env").read_bytes()
            self.invoke(WORKLOAD, home)
            self.assertEqual((home / ".env").read_bytes(), before)

    def test_preserves_preexisting_wildcard(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            self.invoke(WORKLOAD, home, upper="*")
            text = (home / ".env").read_text()
            self.assertEqual(text, "NO_PROXY=*\nno_proxy=*\n")


if __name__ == "__main__":
    unittest.main()
