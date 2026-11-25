from celery import Celery
from celery.schedules import crontab
from .config import settings

celery_app = Celery("factorylink", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(task_serializer="json", accept_content=["json"], result_serializer="json", timezone="Asia/Tokyo", enable_utc=True)
celery_app.conf.beat_schedule = {
    "maintenance-reminders-daily": {
        "task": "app.tasks.create_maintenance_reminders",
        "schedule": crontab(hour=8, minute=0),
    }
}
celery_app.autodiscover_tasks(["app"])
