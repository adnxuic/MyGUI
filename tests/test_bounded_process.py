import subprocess
import sys
import unittest

from mygui.bounded_process import (
    ProcessOutputLimitExceeded,
    run_bounded_process,
)


class BoundedProcessTests(unittest.TestCase):
    def test_successfully_captures_bounded_input_and_output(self):
        result = run_bounded_process(
            [
                sys.executable,
                "-c",
                "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())",
            ],
            input_bytes=b"hello",
            timeout=5,
            max_input_bytes=64,
            max_output_bytes=64,
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"hello")
        self.assertEqual(result.stderr, b"")

    def test_rejects_input_before_starting_process(self):
        with self.assertRaisesRegex(ValueError, "input exceeds"):
            run_bounded_process(
                [sys.executable, "-c", "pass"],
                input_bytes=b"too large",
                timeout=5,
                max_input_bytes=2,
                max_output_bytes=64,
            )

    def test_terminates_process_that_exceeds_output_budget(self):
        with self.assertRaises(ProcessOutputLimitExceeded):
            run_bounded_process(
                [
                    sys.executable,
                    "-c",
                    "import sys; sys.stdout.write('x' * 4096); sys.stdout.flush()",
                ],
                timeout=5,
                max_input_bytes=64,
                max_output_bytes=32,
            )

    def test_terminates_process_after_timeout(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            run_bounded_process(
                [sys.executable, "-c", "import time; time.sleep(10)"],
                timeout=0.05,
                max_input_bytes=64,
                max_output_bytes=64,
            )


if __name__ == "__main__":
    unittest.main()
