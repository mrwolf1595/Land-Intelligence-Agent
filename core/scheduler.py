"""
Thin wrapper around APScheduler used by main.py.
Supports both blocking (main process) and background (testing/embedded) modes.
"""
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.schedulers.background import BackgroundScheduler
from core.logger import get_logger

logger = get_logger("scheduler")


class AgentScheduler:
    def __init__(self, blocking: bool = True):
        self._sched = BlockingScheduler() if blocking else BackgroundScheduler()

    def add_interval(self, func, **kwargs):
        """Register a recurring job. Pass minutes=N or hours=N in kwargs."""
        self._sched.add_job(func, "interval", id=func.__name__, **kwargs)
        interval_desc = ", ".join(f"{k}={v}" for k, v in kwargs.items())
        logger.info(f"Scheduled '{func.__name__}' every {interval_desc}")

    def start(self):
        logger.info("Scheduler starting — press Ctrl+C to stop")
        self._sched.start()

    def stop(self):
        if self._sched.running:
            self._sched.shutdown(wait=False)
            logger.info("Scheduler stopped")
