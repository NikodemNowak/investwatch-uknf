# 0003: Job queue: Celery + Redis

**Context:** Scraping (slow I/O, Chromium) and analysis (waits on the LLM) must scale separately, and sources run on per-source schedules.

**Decision:** Celery with Redis as broker; queues `scrape`, `analyze`, `maintenance`; Celery Beat runs `tick_sources` every minute, which enqueues sources whose `next_run_at` has passed.

**Consequences:** One tool gives queue, scheduler, retries with backoff and rate limits; Redis is reused as the Socket.IO bus. Rejected: RQ + APScheduler (no routing/cron in one tool), Airflow/Prefect (too heavy), Kafka (unneeded at this scale).
