from __future__ import annotations

from pipelines.validation.validation_result import ValidationResult


class ValidationFailedError(RuntimeError):
    pass


def assert_no_blocking_failures(results: list[ValidationResult]) -> None:
    failures = [
        result
        for result in results
        if result.severity == "fail" and result.status == "failed"
    ]
    if failures:
        failed_ids = ", ".join(result.validation_check_id for result in failures)
        raise ValidationFailedError(
            f"Critical raw validation failures block loading: {failed_ids}"
        )
