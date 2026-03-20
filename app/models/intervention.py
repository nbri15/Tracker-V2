"""Intervention tracking model."""

from datetime import datetime, timezone

from app.extensions import db


class Intervention(db.Model):
    """Flags pupils requiring intervention support in a subject area."""

    __tablename__ = 'interventions'
    __table_args__ = (
        db.Index('ix_interventions_scope', 'subject', 'term', 'academic_year', 'is_active'),
    )

    id = db.Column(db.Integer, primary_key=True)
    pupil_id = db.Column(db.Integer, db.ForeignKey('pupils.id'), nullable=False, index=True)
    subject = db.Column(db.String(20), nullable=False)
    term = db.Column(db.String(20), nullable=False)
    academic_year = db.Column(db.String(20), nullable=False, index=True)
    reason = db.Column(db.String(255), nullable=False)
    note = db.Column(db.Text, nullable=True)
    auto_flagged = db.Column(db.Boolean, nullable=False, default=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    pupil = db.relationship('Pupil', back_populates='interventions')

    def __repr__(self) -> str:
        return f'<Intervention {self.subject}>'
