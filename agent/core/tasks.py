"""Background task system for async event parsing."""
import asyncio
import logging
from typing import Optional
from dataclasses import dataclass

from agent.core.callback import send_callback
from agent.core.schemas import Event
from agent.scraper.orchestrator import ScrapingOrchestrator
from agent.integrations.grist import save_event_to_grist

logger = logging.getLogger(__name__)


@dataclass
class ParseTask:
    """Represents a background parse task."""
    request_id: str
    url: str
    callback_url: str
    discord_message_id: Optional[int]
    include_screenshot: bool
    wait_time: int


class TaskRunner:
    """
    Simple asyncio-based task runner for background parsing.

    Design notes:
    - Uses asyncio.create_task for simplicity (no external queue)
    - Tasks are fire-and-forget; no persistence across restarts
    - Future: Could be replaced with Celery/Redis for persistence
    """

    def __init__(self):
        self._tasks: dict[str, asyncio.Task] = {}

    def submit(self, task: ParseTask) -> None:
        """
        Submit a parse task for background execution.

        Args:
            task: ParseTask with all necessary parameters
        """
        asyncio_task = asyncio.create_task(
            self._run_task(task),
            name=f"parse-{task.request_id}"
        )
        self._tasks[task.request_id] = asyncio_task

        # Clean up completed task reference when done
        asyncio_task.add_done_callback(
            lambda t: self._tasks.pop(task.request_id, None)
        )

        logger.info(f"Task {task.request_id} submitted for URL: {task.url}")

    async def _run_task(self, task: ParseTask) -> None:
        """
        Execute the parse task and send callback with results.

        Args:
            task: ParseTask to execute
        """
        event: Optional[Event] = None
        error: Optional[str] = None
        status = "failed"

        try:
            logger.info(f"Starting parse task {task.request_id}")

            orchestrator = ScrapingOrchestrator()
            response = await orchestrator.scrape_event(
                url=task.url,
                wait_time=task.wait_time,
                include_screenshot=task.include_screenshot
            )

            if response.success and response.event:
                event = response.event
                status = "completed"
                logger.info(
                    f"Task {task.request_id} completed successfully: "
                    f"{event.title}"
                )
            else:
                error = response.error or "Unknown extraction error"
                logger.warning(
                    f"Task {task.request_id} extraction failed: {error}"
                )

        except Exception as e:
            error = str(e)
            logger.exception(f"Task {task.request_id} crashed: {e}")

        # Save to Grist if successful
        result_url = None
        grist_record_id = None
        if status == "completed" and event:
            grist_result = await save_event_to_grist(event)
            if grist_result.success:
                result_url = grist_result.record_url
                grist_record_id = grist_result.record_id
                logger.info(
                    f"Task {task.request_id} saved to Grist: {result_url}, "
                    f"record_id={grist_record_id}"
                )
            else:
                # Log but don't fail the whole task
                logger.warning(
                    f"Task {task.request_id} Grist save failed: "
                    f"{grist_result.error}"
                )

        await send_callback(
            callback_url=task.callback_url,
            request_id=task.request_id,
            discord_message_id=task.discord_message_id,
            status=status,
            event=event,
            error=error,
            result_url=result_url,
            grist_record_id=grist_record_id
        )

    def get_active_count(self) -> int:
        """Return number of currently running tasks."""
        return len(self._tasks)

    def is_running(self, request_id: str) -> bool:
        """Check if a task is currently running."""
        return request_id in self._tasks


# Global task runner instance
task_runner = TaskRunner()
