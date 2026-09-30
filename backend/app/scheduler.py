from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler

from app.services.logging import cleanup_logs, write_system_log


class Scheduler:
    def __init__(self, settings, database, fernet):
        self.settings = settings
        self.database = database
        self.fernet = fernet
        self.scheduler = BackgroundScheduler(timezone=settings.app.timezone)
        self.running = False

    def start(self) -> None:
        if not self.settings.scheduler.enabled:
            return
        self.scheduler.add_job(
            self._run_bill_completion,
            "cron",
            hour=self.settings.scheduler.bill_check_hour,
            minute=self.settings.scheduler.bill_check_minute,
            id="bill_completion",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        self.scheduler.add_job(
            self._run_notification_check,
            "interval",
            seconds=self.settings.scheduler.notification_interval_seconds,
            id="notification_check",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        self.scheduler.add_job(
            self._run_log_cleanup,
            "cron",
            hour=self.settings.scheduler.log_cleanup_hour,
            id="log_cleanup",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        self.scheduler.start()
        self.running = True

    def shutdown(self) -> None:
        if self.running:
            self.scheduler.shutdown(wait=False)
            self.running = False

    def _run_bill_completion(self) -> None:
        try:
            from app.services.billing import complete_all_active_plans

            complete_all_active_plans(self.database, self.settings)
        except Exception as exc:
            write_system_log(self.settings, level="ERROR", module="scheduler", event="bill_completion_failed", request_id=None, message="账单补全任务失败", data={"error_type": type(exc).__name__})

    def _run_notification_check(self) -> None:
        try:
            from app.services.notifications import check_notifications

            check_notifications(self.database, self.settings, self.fernet)
        except Exception as exc:
            write_system_log(self.settings, level="ERROR", module="scheduler", event="notification_check_failed", request_id=None, message="通知检查任务失败", data={"error_type": type(exc).__name__})

    def _run_log_cleanup(self) -> None:
        try:
            removed = cleanup_logs(self.settings)
            write_system_log(self.settings, level="INFO", module="scheduler", event="log_cleanup_completed", request_id=None, message="日志清理任务完成", data={"removed": removed})
        except Exception as exc:
            write_system_log(self.settings, level="ERROR", module="scheduler", event="log_cleanup_failed", request_id=None, message="日志清理任务失败", data={"error_type": type(exc).__name__})
