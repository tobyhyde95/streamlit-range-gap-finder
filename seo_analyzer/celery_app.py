# seo_analyzer/celery_app.py
import os
from celery import Celery

# The broker URL points to your running Redis instance
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')

# Initialize the central Celery app object
celery_app = Celery(
    'tasks',
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    # THIS LINE IS CHANGED: Tell Celery to look for tasks in tasks.py
    include=['seo_analyzer.tasks']
)

# Optional configuration
celery_app.conf.update(
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    timezone='Europe/London',
    enable_utc=True,
)