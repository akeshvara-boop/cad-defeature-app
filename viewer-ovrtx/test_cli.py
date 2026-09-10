"""CPU-only checks: do not substitute for the GPU first-frame test."""
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).parent

class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "server.py"), *args],
                              capture_output=True, text=True, timeout=10)

    def test_help_without_gpu_imports(self):
        result = self.run_cli("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("--stage", result.stdout)

    def test_missing_stage_fails_before_runtime(self):
        result = self.run_cli("--stage", str(ROOT / "does-not-exist.usdc"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("existing prepared USD", result.stderr)

    def test_invalid_port_fails_before_runtime(self):
        result = self.run_cli("--stage", str(ROOT / "smoke.usda"), "--signal-port", "70000")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Invalid port", result.stderr)

if __name__ == "__main__":
    unittest.main()
