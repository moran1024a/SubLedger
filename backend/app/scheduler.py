from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from threading import RLock
from time import monotonic

from apscheduler.schedulers.background import BackgroundScheduler

from app.services.logging import cleanup_logs, write_system_log


@dataclass
class TaskState:
    id: str
    name: str
    next_run_at: datetime | None = None
    last_started_at: datetime | None = None
    last_finished_at: datetime | None = None
    last_success_at: datetime | None = None
    duration_seconds: float | None = None
    consecutive_failures: int = 0
    last_error: str | None = None
    running: bool = False
    counts: dict | None = None


class Scheduler:
    def __init__(self, settings, database, fernet):
        self.settings = settings
        self.database = database
        self.fernet = fernet
        self.scheduler = BackgroundScheduler(timezone=settings.app.timezone)
        self.running = False
        self._lock = RLock()
        self._started_monotonic: dict[str, float] = {}
        self._states = {
            key: TaskState(key, name) for key, name in (
                ("bill_completion", "账单补全"), ("notification_check", "通知检查"),
                ("log_cleanup", "日志清理"), ("session_cleanup", "过期会话清理"),
            )
        }

    def start(self) -> None:
        if not self.settings.scheduler.enabled:
            return
        config = self.settings.scheduler
        jobs = (
            ("bill_completion", self._run_bill_completion, "cron", dict(hour=config.bill_check_hour, minute=config.bill_check_minute)),
            ("notification_check", self._run_notification_check, "interval", dict(seconds=config.notification_interval_seconds)),
            ("log_cleanup", self._run_log_cleanup, "cron", dict(hour=config.log_cleanup_hour)),
            ("session_cleanup", self._run_session_cleanup, "cron", dict(hour=config.session_cleanup_hour)),
        )
        for key, function, trigger, arguments in jobs:
            self.scheduler.add_job(function, trigger, id=key, replace_existing=True, max_instances=1, coalesce=True, **arguments)
        self.scheduler.start(paused=True)
        with self._lock:
            for job in self.scheduler.get_jobs():
                self._states[job.id].next_run_at = job.next_run_time
            self.running = True
        self.scheduler.resume()

    def shutdown(self) -> None:
        if self.running:
            self.scheduler.shutdown(wait=True)
            self.running = False

    def snapshot(self, now: datetime | None = None) -> dict:
        now = now or datetime.now(timezone.utc)
        enabled = self.settings.scheduler.enabled
        with self._lock:
            tasks = []
            for key, state in self._states.items():
                item = asdict(state)
                grace = max(120, 2 * self.settings.scheduler.notification_interval_seconds) if key == "notification_check" and enabled else 600
                overdue = state.next_run_at is not None and now > state.next_run_at + timedelta(seconds=grace)
                too_long = state.running and monotonic() - self._started_monotonic[key] > self.settings.scheduler.task_timeout_seconds
                if not enabled:
                    status = "disabled"
                elif not self.running or too_long or state.consecutive_failures >= 3 or (overdue and not state.running):
                    status = "error"
                elif state.running:
                    status = "running"
                elif state.consecutive_failures or (state.counts or {}).get("failed", 0) or (state.counts or {}).get("unknown", 0):
                    status = "warning"
                else:
                    status = "ok" if state.last_finished_at else "waiting"
                item["status"] = status
                tasks.append(item)
        return {"status": "disabled" if not enabled else "error" if any(t["status"] == "error" for t in tasks) else "ok", "tasks": tasks}

    def _run(self, key, function) -> None:
        started = monotonic()
        with self._lock:
            state = self._states[key]
            state.last_started_at = datetime.now(timezone.utc)
            state.running = True
            self._started_monotonic[key] = started
        error = None
        counts = None
        try:
            counts = function()
            if isinstance(counts, dict) and counts.get("errors", 0):
                error = "NotificationCheckError"
        except Exception as exc:
            error = type(exc).__name__
        finally:
            finished = datetime.now(timezone.utc)
            with self._lock:
                state.running = False
                state.last_finished_at = finished
                state.duration_seconds = round(monotonic() - started, 3)
                state.counts = counts if isinstance(counts, dict) else None
                state.last_error = error
                state.consecutive_failures = state.consecutive_failures + 1 if error else 0
                if not error:
                    state.last_success_at = finished
                job = self.scheduler.get_job(key)
                if job:
                    state.next_run_at = job.trigger.get_next_fire_time(None, finished + timedelta(microseconds=1))
            write_system_log(self.settings, level="ERROR" if error else "INFO", module="scheduler", event=key + ("_failed" if error else "_completed"), request_id=None, message=state.name + ("失败" if error else "完成"), data={"error_type": error, "duration_seconds": state.duration_seconds, "counts": counts})

    def _run_bill_completion(self) -> None:
        from app.services.billing import complete_all_active_plans
        self._run("bill_completion", lambda: complete_all_active_plans(self.database))

    def _run_notification_check(self) -> None:
        from app.services.notifications import check_notifications
        self._run("notification_check", lambda: check_notifications(self.database, self.settings, self.fernet))

    def _run_log_cleanup(self) -> None:
        self._run("log_cleanup", lambda: {"removed": cleanup_logs(self.settings)})

    def _run_session_cleanup(self) -> None:
        from app.services.auth import cleanup_expired_sessions
        self._run("session_cleanup", lambda: {"removed": cleanup_expired_sessions(self.database)})
