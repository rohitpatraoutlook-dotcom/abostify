from datetime import datetime, timezone, date
from models import db


def utcnow():
    return datetime.now(timezone.utc)


class Attendance(db.Model):
    __tablename__ = "company_attendance"

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(
        db.Integer, db.ForeignKey("company.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    work_date = db.Column(db.Date, nullable=False, default=date.today)
    check_in = db.Column(db.DateTime(timezone=True))
    check_out = db.Column(db.DateTime(timezone=True))
    status = db.Column(db.String(20), nullable=False, default="present")
    note = db.Column(db.String(300))

    __table_args__ = (
        db.UniqueConstraint(
            "company_id", "user_id", "work_date",
            name="uq_company_attendance_day"
        ),
        db.CheckConstraint(
            "status IN ('present','late','absent','half_day','on_leave')",
            name="ck_attendance_status"
        ),
    )

    company = db.relationship("Company")
    user = db.relationship("User")


class LeaveRequest(db.Model):
    __tablename__ = "company_leave_request"

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(
        db.Integer, db.ForeignKey("company.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    leave_type = db.Column(db.String(40), nullable=False, default="casual")
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    reason = db.Column(db.String(1000), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending")
    reviewed_by_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="SET NULL")
    )
    reviewed_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow
    )

    __table_args__ = (
        db.CheckConstraint(
            "status IN ('pending','approved','rejected','cancelled')",
            name="ck_leave_status"
        ),
    )

    company = db.relationship("Company")
    user = db.relationship("User", foreign_keys=[user_id])
    reviewer = db.relationship("User", foreign_keys=[reviewed_by_id])
