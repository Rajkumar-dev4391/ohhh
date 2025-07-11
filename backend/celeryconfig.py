import os
from celery import Celery

# Redis configuration
REDIS_URL = os.getenv("CELERY_BROKER_URL") or os.getenv("REDIS_URL", "redis://localhost:6379/0")
RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND") or os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Create Celery app
celery_app = Celery(
    "mcp_tasks",
    broker=REDIS_URL,
    backend=RESULT_BACKEND,
    include=["backend.tasks"]
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,  # 25 minutes
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
    result_expires=3600,  # 1 hour
    task_routes={
        "backend.tasks.run_mcp_toolkit": {"queue": "mcp_queue"},
    },
    task_default_queue="default",
    task_default_exchange="default",
    task_default_exchange_type="direct",
    task_default_routing_key="default",
)

# Optional: Configure different queues for different task types
celery_app.conf.task_routes = {
    "backend.tasks.run_mcp_toolkit": {"queue": "mcp_queue"},
}