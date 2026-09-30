from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from app.errors import validation_field_errors
from app.services.billing import cycle_date, occurrence_response, plan_response
from app.services.logging import list_log_files


class FakeValidationError:
    def errors(self):
        return [
            {"loc": ("body", "cycle_days"), "msg": "Input should be greater than 0", "type": "greater_than"},
            {"loc": ("query", "page"), "msg": "Input should be a valid integer", "type": "int_parsing"},
        ]


def test_cycle_date_handles_month_end_and_leap_year():
    assert cycle_date(date(2024, 1, 31), "monthly", 1) == date(2024, 2, 29)
    assert cycle_date(date(2023, 1, 31), "monthly", 1) == date(2023, 2, 28)
    assert cycle_date(date(2024, 2, 29), "yearly", 1) == date(2025, 2, 28)


def test_cycle_date_handles_custom_days():
    assert cycle_date(date(2026, 7, 20), "custom_days", 3, 10) == date(2026, 8, 19)


def test_plan_and_occurrence_responses_include_frontend_contract_fields():
    created = datetime(2026, 7, 20, 1, 2, 3)
    plan = SimpleNamespace(
        id=3,
        name="Hosting",
        amount="12.50",
        first_due_date=date(2026, 7, 20),
        cycle_type="custom_days",
        cycle_days=14,
        is_enabled=True,
        note="",
        created_at=created,
        updated_at=created,
    )
    occurrence = SimpleNamespace(
        id=4,
        plan_id=3,
        due_date=date(2026, 7, 20),
        amount_snapshot="12.50",
        is_valid=True,
    )

    plan_result = plan_response(plan)
    occurrence_result = occurrence_response(occurrence, plan, date(2026, 7, 19))

    assert plan_result["created_at"] == created
    assert plan_result["updated_at"] == created
    assert occurrence_result["plan_name"] == "Hosting"
    assert occurrence_result["cycle_type"] == "custom_days"
    assert occurrence_result["cycle_days"] == 14
    assert "name" not in occurrence_result


def test_log_listing_returns_filename_and_utc_modification_time(tmp_path: Path):
    log_dir = tmp_path / "logs" / "users" / "2"
    log_dir.mkdir(parents=True)
    path = log_dir / "2026-07-20.log"
    path.write_text("{}\n", encoding="utf-8")
    settings = SimpleNamespace(logging=SimpleNamespace(directory=str(tmp_path / "logs")))

    result = list_log_files(settings, "user", 2)

    assert result[0]["filename"] == "2026-07-20.log"
    assert result[0]["size"] == 3
    assert result[0]["modified_at"].tzinfo == timezone.utc


def test_validation_errors_strip_transport_location():
    assert validation_field_errors(FakeValidationError()) == [
        {"field": "cycle_days", "message": "Input should be greater than 0"},
        {"field": "page", "message": "Input should be a valid integer"},
    ]
