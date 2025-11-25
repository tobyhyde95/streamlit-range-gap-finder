web: gunicorn --worker-class gevent --bind 0.0.0.0:5000 --timeout 300 seo_analyzer.app:app
worker: celery -A seo_analyzer.celery_app:celery_app worker --loglevel=info -P gevent