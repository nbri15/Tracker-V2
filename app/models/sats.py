"""Year 6 SATs data models."""

from datetime import datetime, timezone

from app.extensions import db


class SatsResult(db.Model):
    """Stores SATs practice or assessment point outcomes for Year 6 pupils."""

    __tablename__ = 'sats_results'
    __table_args__ = (
        db.UniqueConstraint('pupil_id', 'subject', 'assessment_point', 'academic_year', name='uq_sats_result_scope'),
        db.Index('ix_sats_result_lookup', 'academic_year', 'subject', 'assessment_point'),
    )

    id = db.Column(db.Integer, primary_key=True)
    pupil_id = db.Column(db.Integer, db.ForeignKey('pupils.id'), nullable=False, index=True)
    subject = db.Column(db.String(20), nullable=False)
    assessment_point = db.Column(db.Integer, nullable=False)
    raw_score = db.Column(db.Integer, nullable=True)
    scaled_score = db.Column(db.Integer, nullable=True)
    is_most_recent = db.Column(db.Boolean, nullable=False, default=False)
    academic_year = db.Column(db.String(20), nullable=False)
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    pupil = db.relationship('Pupil', back_populates='sats_results')

    def __repr__(self) -> str:
        return f'<SatsResult {self.subject} AP{self.assessment_point}>'


class SatsWritingResult(db.Model):
    """Stores Year 6 writing judgements for each assessment point."""

    __tablename__ = 'sats_writing_results'
    __table_args__ = (
        db.UniqueConstraint('pupil_id', 'assessment_point', 'academic_year', name='uq_sats_writing_scope'),
        db.Index('ix_sats_writing_lookup', 'academic_year', 'assessment_point'),
    )

    id = db.Column(db.Integer, primary_key=True)
    pupil_id = db.Column(db.Integer, db.ForeignKey('pupils.id'), nullable=False, index=True)
    assessment_point = db.Column(db.Integer, nullable=False)
    academic_year = db.Column(db.String(20), nullable=False)
    band = db.Column(db.String(50), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    pupil = db.relationship('Pupil', back_populates='sats_writing_results')

    def __repr__(self) -> str:
        return f'<SatsWritingResult AP{self.assessment_point}>'
