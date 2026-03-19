"""Year 6 SATs data model."""

from datetime import datetime, UTC

from app.extensions import db


class SatsResult(db.Model):
    """Stores SATs practice or assessment point outcomes for Year 6 pupils."""

    __tablename__ = 'sats_results'

    id = db.Column(db.Integer, primary_key=True)
    pupil_id = db.Column(db.Integer, db.ForeignKey('pupils.id'), nullable=False)
    subject = db.Column(db.String(20), nullable=False)
    assessment_point = db.Column(db.Integer, nullable=False)
    raw_score = db.Column(db.Integer, nullable=True)
    scaled_score = db.Column(db.Integer, nullable=True)
    is_most_recent = db.Column(db.Boolean, nullable=False, default=False)
    academic_year = db.Column(db.String(20), nullable=False)
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    pupil = db.relationship('Pupil', back_populates='sats_results')

    def __repr__(self) -> str:
        return f'<SatsResult {self.subject} AP{self.assessment_point}>'
