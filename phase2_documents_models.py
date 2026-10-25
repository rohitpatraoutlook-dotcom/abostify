from datetime import datetime, timezone
from models import db


class CompanyDocument(db.Model):
    __tablename__ = "company_documents"

    id = db.Column(db.Integer, primary_key=True)

    company_id = db.Column(
        db.Integer,
        db.ForeignKey("company.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    uploaded_by_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    original_filename = db.Column(db.String(255), nullable=False)
    storage_filename = db.Column(
        db.String(100), nullable=False, unique=True
    )
    mime_type = db.Column(db.String(120))
    size_bytes = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    company = db.relationship("Company")
    uploader = db.relationship("User")
