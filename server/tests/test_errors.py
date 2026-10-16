import subprocess
import sys
import unittest

from moodsync.errors import describe_error


class FailureDetailsTests(unittest.TestCase):
    def test_real_subprocess_error_includes_stderr_before_command(self):
        with self.assertRaises(subprocess.CalledProcessError) as caught:
            subprocess.run(
                [sys.executable, "-c", "import sys; sys.stderr.write('ERROR: audio unavailable'); sys.exit(1)"],
                capture_output=True, check=True,
            )
        detail = describe_error(caught.exception)
        self.assertTrue(detail.startswith("ERROR: audio unavailable"))
        self.assertIn("CalledProcessError (exit 1)", detail)
        self.assertIn("Command:", detail)

    def test_text_output_and_ansi_cleanup(self):
        error = subprocess.CalledProcessError(2, ["tool"], stderr="\x1b[31mERROR: denied\x1b[0m\n")
        self.assertTrue(describe_error(error).startswith("ERROR: denied"))
        self.assertNotIn("\x1b", describe_error(error))

    def test_exception_type_and_cause(self):
        error = RuntimeError("Import failed")
        error.__cause__ = ValueError("Invalid metadata")
        detail = describe_error(error)
        self.assertIn("RuntimeError: Import failed", detail)
        self.assertIn("Caused by:\nValueError: Invalid metadata", detail)

    def test_missing_output_does_not_invent_a_reason(self):
        error = subprocess.CalledProcessError(1, ["tool"])
        self.assertIn("without captured error output", describe_error(error))

    def test_large_output_is_bounded(self):
        error = subprocess.CalledProcessError(1, ["tool"], stderr="noise\n" * 10000 + "ERROR: failed")
        detail = describe_error(error)
        self.assertTrue(detail.startswith("ERROR: failed"))
        self.assertLessEqual(len(detail), 24000)


if __name__ == "__main__":
    unittest.main()
