#!/usr/bin/env python3
"""
Script to run Celery worker
"""
import os
import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.celeryconfig import celery_app

if __name__ == "__main__":
    # Run the worker
    celery_app.worker_main([
        'worker',
        '--loglevel=info',
        '--queues=mcp_queue,default',
        '--concurrency=2',
        '--pool=prefork'
    ])