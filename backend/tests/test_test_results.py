from app.services.test_results import parse_test_summary


def test_pytest_summary_is_normalized():
    result = parse_test_summary("python-tests", "2 failed, 8 passed, 1 skipped in 1.2s", "FAILED")
    assert result == {"framework": "pytest", "discovered": 11, "passed": 8, "failed": 2,
                      "skipped": 1, "status": "FAILED"}


def test_zero_tests_is_not_reported_as_passed():
    result = parse_test_summary("python-tests", "no tests ran in 0.01s", "PASSED")
    assert result["status"] == "NO_TESTS"
    assert result["discovered"] == 0


def test_go_json_events_are_counted():
    output = '\n'.join(['{"Action":"pass","Test":"TestOne"}', '{"Action":"skip","Test":"TestTwo"}'])
    result = parse_test_summary("go-tests", output, "PASSED")
    assert result["discovered"] == 2
    assert result["passed"] == 1
    assert result["skipped"] == 1


def test_jest_summary_is_counted():
    result = parse_test_summary("js-tests", "Tests: 1 failed, 4 passed, 5 total", "FAILED")
    assert result["discovered"] == 5
    assert result["failed"] == 1
    assert result["passed"] == 4


def test_junit_summary_counts_errors_as_failures():
    result = parse_test_summary(
        "java-tests", "Tests run: 8, Failures: 1, Errors: 1, Skipped: 2", "FAILED"
    )
    assert result["discovered"] == 8
    assert result["passed"] == 4
    assert result["failed"] == 2
    assert result["skipped"] == 2


def test_coverage_is_extracted_without_inventing_it():
    covered = parse_test_summary("python-tests", "10 passed\nTOTAL 100 15 85%", "PASSED")
    uncovered = parse_test_summary("python-tests", "10 passed", "PASSED")
    assert covered["coverage_percent"] == "85.0"
    assert "coverage_percent" not in uncovered
