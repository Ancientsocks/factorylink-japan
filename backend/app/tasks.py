from datetime import date, timedelta
import smtplib
from sqlalchemy import text
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy import select
from .celery_app import celery_app
from .database import SessionLocal, set_system_job_context, set_tenant_context
from .models import MaintenanceTask, Notification, Equipment, Organization


@celery_app.task(
    name="app.tasks.create_maintenance_reminders",
    autoretry_for=(InterfaceError, OperationalError),
    retry_backoff=True,
    retry_kwargs={"max_retries": 5},
    acks_late=True,
    reject_on_worker_lost=True,
)
def create_maintenance_reminders():
    """Create reminders one tenant at a time under PostgreSQL RLS context."""
    db = SessionLocal()
    created = 0
    lock_connection = None
    lock_transaction = None
    try:
        if db.get_bind().dialect.name == "postgresql":
            # Hold one transaction-scoped lock across per-tenant commits so
            # overlapping beat/worker deliveries cannot create duplicate rows.
            lock_connection = db.get_bind().connect()
            lock_transaction = lock_connection.begin()
            acquired = lock_connection.execute(
                text("SELECT pg_try_advisory_xact_lock(701182993214)")
            ).scalar_one()
            if not acquired:
                return {"notifications_created": 0, "skipped": True}
        set_system_job_context(db, "maintenance-reminders")
        organization_ids = db.scalars(select(Organization.id).order_by(Organization.id)).all()
        target = date.today() + timedelta(days=3)
        for organization_id in organization_ids:
            set_tenant_context(db, organization_id)
            tasks = db.scalars(
                select(MaintenanceTask).where(
                    MaintenanceTask.organization_id == organization_id,
                    MaintenanceTask.due_date <= target,
                    MaintenanceTask.status.in_(["SCHEDULED", "OVERDUE"]),
                )
            ).all()
            for task in tasks:
                equipment = db.get(Equipment, task.equipment_id)
                title = "Maintenance reminder"
                body = f"{equipment.name if equipment else 'Equipment'}: {task.title} is due on {task.due_date}."
                exists = db.scalar(
                    select(Notification.id).where(
                        Notification.organization_id == organization_id,
                        Notification.title == title,
                        Notification.body == body,
                    )
                )
                if not exists:
                    db.add(Notification(organization_id=organization_id, title=title, body=body, level="WARNING"))
                    created += 1
            # Commit per tenant. SQLAlchemy reapplies the transaction-local
            # tenant setting at the next transaction via database.after_begin.
            db.commit()
        return {"notifications_created": created}
    finally:
        db.close()
        if lock_transaction is not None and lock_transaction.is_active:
            lock_transaction.rollback()
        if lock_connection is not None:
            lock_connection.close()


@celery_app.task(
    name="app.tasks.send_transactional_email",
    autoretry_for=(OSError, RuntimeError, smtplib.SMTPException),
    retry_backoff=True,
    retry_kwargs={"max_retries": 5},
    acks_late=True,
    reject_on_worker_lost=True,
)
def send_transactional_email(to_email: str, subject: str, body: str):
    """Send password-reset and invitation email outside the API request."""
    from .mailer import deliver_email
    deliver_email(to_email, subject, body)
    return {"sent": True, "to": to_email}
