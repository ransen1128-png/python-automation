"""Render-compatible defaults when starting with `gunicorn app:app`."""
import os

bind = '0.0.0.0:' + os.environ.get('PORT', '10000')
workers = 1
threads = 4
timeout = 60
accesslog = '-'
errorlog = '-'
