"""
Worker tasks (spec §39–40).

`run_search` is the unit of background work: one search, start to finish. Phase 7
registers this exact function with Celery (`@celery_app.task(bind=True)`) and the
only change is how it gets invoked — the body stays.

The finer-grained tasks the spec lists (`run_query`, `extract_candidate`,
`score_candidate`) are stages inside the pipeline today. They become separate
tasks when they need separate retry policies and queues, which is a Phase 7
decision; splitting them now would add a queue hop with nothing to gain.
"""

from app.core.logging import bind, get_logger
from app.services.search.pipeline import SearchPipeline

log = get_logger(__name__)


async def run_search(
    search_id: str, *, pipeline: SearchPipeline, job_id: str | None = None
) -> None:
    bind(search_id=search_id, job_id=job_id)
    log.info("job_started", extra={"task": "run_search"})
    await pipeline.run(search_id)
    log.info("job_finished", extra={"task": "run_search"})
