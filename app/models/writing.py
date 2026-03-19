"""Writing assessment models."""

from datetime import datetime, timezone

from app.extensions import db


class WritingResult(db.Model):
    """Stores teacher-assessed writing bands for a pupil."""

    __tablename__ = 'writing_results'
    __table_args__ = (
        db.UniqueConstraint('pupil_id', 'academic_year', 'term', name='uq_writing_result_scope'),
    )

    id = db.Column(db.Integer, primary_key=True)
    pupil_id = db.Column(db.Integer, db.ForeignKey('pupils.id'), nullable=False)
    academic_year = db.Column(db.String(20), nullable=False)
    term = db.Column(db.String(20), nullable=False)
    band = db.Column(db.String(50), nullable=False)
    notes = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    pupil = db.relationship('Pupil', back_populates='writing_results')

    def __repr__(self) -> str:
        return f'<WritingResult {self.band}>'
