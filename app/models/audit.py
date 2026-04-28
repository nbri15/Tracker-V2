"""Audit log model for sensitive admin actions."""

from datetime import datetime, timezone

from app.extensions import db


class AuditLog(db.Model):
    """Immutable audit trail entries for archive/delete/export actions."""

    __tablename__ = 'audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=True, index=True)
    action = db.Column(db.String(120), nullable=False, index=True)
    target_type = db.Column(db.String(80), nullable=False, index=True)
    target_id = db.Column(db.Integer, nullable=False, index=True)
    details = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)

    user = db.relationship('User')
    school = db.relationship('School')

