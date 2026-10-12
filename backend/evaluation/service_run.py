"""Reproducible service flow contracts; no live model accuracy claims."""

import json
import os
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.test_service import ServiceTests


class ReportResult(unittest.TextTestResult):
    def startTest(self, test):
        super().startTest(test)
        self.started = time.perf_counter()

    def stopTest(self, test):
        failed = any(t is test for t, _ in self.failures + self.errors)
        records.append(
            {
                "case": test._testMethodName,
                "passed": not failed,
                "elapsed_ms": round((time.perf_counter() - self.started) * 1000),
            }
        )
        super().stopTest(test)


if __name__ == "__main__":
    records = []
    suite = unittest.TestSuite(
        ServiceTests(name) for name in ServiceTests.__dict__ if name.startswith("test_")
    )
    result = unittest.TextTestRunner(verbosity=1, resultclass=ReportResult).run(suite)
    report = {
        "scope": "Hand-authored business flow contracts in rule mode, not LLM task completion or answer accuracy.",
        "database": "mysql" if os.environ.get("MYSQL_TEST_URL") else "sqlite-isolated",
        "mode": "demo",
        "passed": sum(r["passed"] for r in records),
        "total": len(records),
        "cases": records,
    }
    Path(__file__).with_name("service-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {k: v for k, v in report.items() if k != "cases"}, ensure_ascii=False
        )
    )
    raise SystemExit(0 if result.wasSuccessful() else 1)
