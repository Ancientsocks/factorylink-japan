from datetime import date, timedelta

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app import models
from app import tasks


def test_maintenance_reminder_redelivery_is_idempotent_per_tenant(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    Base.metadata.create_all(bind=engine)
    with testing_session() as db:
        organizations = [
            models.Organization(name="Factory One", code="FACTORY-ONE"),
            models.Organization(name="Factory Two", code="FACTORY-TWO"),
        ]
        db.add_all(organizations)
        db.flush()
        for index, organization in enumerate(organizations, start=1):
            equipment = models.Equipment(
                organization_id=organization.id,
                code=f"EQ-{index}",
                name=f"Machine {index}",
            )
            db.add(equipment)
            db.flush()
            db.add(models.MaintenanceTask(
                organization_id=organization.id,
                equipment_id=equipment.id,
                title="Scheduled inspection",
                due_date=date.today() + timedelta(days=1),
            ))
        db.commit()

    monkeypatch.setattr(tasks, "SessionLocal", testing_session)
    try:
        first = tasks.create_maintenance_reminders.run()
        redelivery = tasks.create_maintenance_reminders.run()

        assert first == {"notifications_created": 2}
        assert redelivery == {"notifications_created": 0}
        with testing_session() as db:
            assert db.scalar(select(func.count()).select_from(models.Notification)) == 2
            assert set(db.scalars(select(models.Notification.organization_id)).all()) == {1, 2}
    finally:
        engine.dispose()
