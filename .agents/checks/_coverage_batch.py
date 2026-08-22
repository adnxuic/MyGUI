"""Collect and execute exact unittest batches for parallel coverage runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
import traceback as traceback_module
import unittest


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _tests_in(suite: unittest.TestSuite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _tests_in(item)
        else:
            yield item


def _normalized_test_id(test_id: str) -> str:
    value = str(test_id)
    return value if value.startswith("tests.") else f"tests.{value}"


def collect_test_ids() -> list[str]:
    """Discover the complete package-less tests directory deterministically."""

    suite = unittest.defaultTestLoader.discover(
        str(ROOT / "tests"),
        pattern="test_*.py",
    )
    tests = list(_tests_in(suite))
    failed_loads = [
        test.id()
        for test in tests
        if type(test).__name__ == "_FailedTest"
    ]
    if failed_loads:
        raise RuntimeError(
            "unittest discovery produced failed imports: "
            + ", ".join(sorted(failed_loads))
        )
    test_ids = sorted(_normalized_test_id(test.id()) for test in tests)
    if not test_ids:
        raise RuntimeError("unittest discovery found no application tests.")
    if len(test_ids) != len(set(test_ids)):
        duplicates = sorted(
            test_id for test_id in set(test_ids) if test_ids.count(test_id) > 1
        )
        raise RuntimeError(
            "unittest discovery produced duplicate test IDs: "
            + ", ".join(duplicates)
        )
    return test_ids


class TimedTextTestResult(unittest.TextTestResult):
    """Record one duration and final status for every executed test."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.test_timings: list[dict[str, object]] = []
        self.failure_details: list[dict[str, str]] = []
        self.error_details: list[dict[str, str]] = []
        self._test_started = 0.0
        self._test_status = "passed"

    @staticmethod
    def _issue(test, err) -> dict[str, str]:
        exception_type, exception, _traceback = err
        return {
            "testId": _normalized_test_id(test.id()),
            "exceptionType": exception_type.__name__,
            "message": str(exception),
            "traceback": "".join(traceback_module.format_exception(*err)),
        }

    def startTest(self, test):
        self._test_started = time.perf_counter()
        self._test_status = "passed"
        super().startTest(test)

    def stopTest(self, test):
        self.test_timings.append({
            "id": _normalized_test_id(test.id()),
            "status": self._test_status,
            "durationMs": round(
                (time.perf_counter() - self._test_started) * 1000,
                3,
            ),
        })
        super().stopTest(test)

    def addError(self, test, err):
        self._test_status = "error"
        self.error_details.append(self._issue(test, err))
        super().addError(test, err)

    def addFailure(self, test, err):
        self._test_status = "failed"
        self.failure_details.append(self._issue(test, err))
        super().addFailure(test, err)

    def addSkip(self, test, reason):
        self._test_status = "skipped"
        super().addSkip(test, reason)

    def addExpectedFailure(self, test, err):
        self._test_status = "expected_failure"
        super().addExpectedFailure(test, err)

    def addUnexpectedSuccess(self, test):
        self._test_status = "unexpected_success"
        self.failure_details.append({
            "testId": _normalized_test_id(test.id()),
            "exceptionType": "UnexpectedSuccess",
            "message": "Test unexpectedly succeeded.",
            "traceback": "",
        })
        super().addUnexpectedSuccess(test)

    def addSubTest(self, test, subtest, err):
        if err is not None:
            if issubclass(err[0], test.failureException):
                self._test_status = "failed"
                self.failure_details.append(self._issue(subtest, err))
            else:
                self._test_status = "error"
                self.error_details.append(self._issue(subtest, err))
        super().addSubTest(test, subtest, err)


def _load_error(test) -> dict[str, str]:
    exception = getattr(test, "_exception", None)
    return {
        "testId": _normalized_test_id(test.id()),
        "exceptionType": (
            type(exception).__name__ if exception is not None else "TestLoadError"
        ),
        "message": str(exception or "unittest could not load the requested test"),
        "traceback": "",
    }


def _write_json(path: str | Path, value: object) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _collect(output: str | Path) -> int:
    started = time.monotonic()
    test_ids = collect_test_ids()
    _write_json(output, {
        "contractVersion": 1,
        "testCount": len(test_ids),
        "uniqueTestCount": len(set(test_ids)),
        "durationMs": round((time.monotonic() - started) * 1000, 3),
        "testIds": test_ids,
    })
    print(f"Collected {len(test_ids)} unique application tests.")
    return 0


def _load_batch(plan_path: str | Path, batch_index: int) -> tuple[list[str], int]:
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    batches = plan.get("batches")
    if not isinstance(batches, list):
        raise ValueError("Application test plan must contain a batches list.")
    matching = [item for item in batches if item.get("index") == batch_index]
    if len(matching) != 1:
        raise ValueError(f"Application test plan has no unique batch {batch_index}.")
    test_ids = matching[0].get("testIds")
    if not isinstance(test_ids, list) or not test_ids or not all(
        isinstance(item, str) and item.startswith("tests.") for item in test_ids
    ):
        raise ValueError(f"Application test batch {batch_index} has invalid test IDs.")
    if len(test_ids) != len(set(test_ids)):
        raise ValueError(f"Application test batch {batch_index} has duplicate test IDs.")
    return test_ids, len(batches)


def _run_batch(plan_path: str | Path, batch_index: int, output: str | Path) -> int:
    test_ids, batch_count = _load_batch(plan_path, batch_index)
    suite = unittest.defaultTestLoader.loadTestsFromNames(test_ids)
    loaded = list(_tests_in(suite))
    loaded_ids = [_normalized_test_id(test.id()) for test in loaded]
    failed_loads = [
        test.id()
        for test in loaded
        if type(test).__name__ == "_FailedTest"
    ]
    load_complete = not failed_loads and loaded_ids == test_ids
    if not load_complete:
        result = {
            "contractVersion": 2,
            "batchIndex": batch_index,
            "batchCount": batch_count,
            "expectedCount": len(test_ids),
            "testsRun": 0,
            "complete": False,
            "successful": False,
            "failureCount": 0,
            "errorCount": len(failed_loads),
            "failures": [],
            "errors": [
                _load_error(test)
                for test in loaded
                if type(test).__name__ == "_FailedTest"
            ],
            "skipped": 0,
            "testTimings": [],
            "loadErrors": sorted(failed_loads),
        }
        _write_json(output, result)
        print(
            f"Batch {batch_index + 1}/{batch_count} could not load its exact test IDs: "
            f"{failed_loads or loaded_ids!r}"
        )
        return 1

    started = time.monotonic()
    runner = unittest.TextTestRunner(
        stream=sys.stdout,
        verbosity=2,
        resultclass=TimedTextTestResult,
    )
    test_result = runner.run(suite)
    observed_ids = [item["id"] for item in test_result.test_timings]
    complete = (
        test_result.testsRun == len(test_ids)
        and sorted(observed_ids) == sorted(test_ids)
    )
    result = {
        "contractVersion": 2,
        "batchIndex": batch_index,
        "batchCount": batch_count,
        "expectedCount": len(test_ids),
        "testsRun": test_result.testsRun,
        "complete": complete,
        "successful": test_result.wasSuccessful() and complete,
        "failureCount": len(test_result.failure_details),
        "errorCount": len(test_result.error_details),
        "failures": test_result.failure_details,
        "errors": test_result.error_details,
        "skipped": len(test_result.skipped),
        "durationMs": round((time.monotonic() - started) * 1000, 3),
        "testTimings": test_result.test_timings,
        "loadErrors": [],
    }
    _write_json(output, result)
    return 0 if result["successful"] else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--collect", action="store_true")
    mode.add_argument("--run", action="store_true")
    parser.add_argument("--plan")
    parser.add_argument("--batch", type=int)
    parser.add_argument("--json-out", required=True)
    args = parser.parse_args()

    try:
        if args.collect:
            return _collect(args.json_out)
        if args.plan is None or args.batch is None:
            parser.error("--run requires --plan and --batch")
        return _run_batch(args.plan, args.batch, args.json_out)
    except Exception as exc:
        print(f"Coverage batch runner failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
