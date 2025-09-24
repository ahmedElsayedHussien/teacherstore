import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "math_tutor.settings")
app = Celery("math_tutor")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
