"""Assessment threshold and subject result models."""

from datetime import datetime, UTC

from app.extensions import db


class AssessmentSetting(db.Model):
    """Editable assessment thresholds by year group, subject, and term."""

    __tablename__ = 'assessment_settings'
    __table_args__ = (
        db.UniqueConstraint('year_group', 'subject', 'term', name='uq_assessment_setting_scope'),
    )

    id = db.Column(db.Integer, primary_key=True)
    year_group = db.Column(db.Integer, nullable=False)
    subject = db.Column(db.String(20), nullable=False)
    term = db.Column(db.String(20), nullable=False)
    paper_1_name = db.Column(db.String(100), nullable=False)
    paper_1_max = db.Column(db.Integer, nullable=False)
    paper_2_name = db.Column(db.String(100), nullable=False)
    paper_2_max = db.Column(db.Integer, nullable=False)
    combined_max = db.Column(db.Integer, nullable=False)
    below_are_threshold_percent = db.Column(db.Float, nullable=False)
    on_track_threshold_percent = db.Column(db.Float, nullable=False)
    exceeding_threshold_percent = db.Column(db.Float, nullable=False)

    def __repr__(self) -> str:
        return f'<AssessmentSetting Y{self.year_group} {self.subject} {self.term}>'


class SubjectResult(db.Model):
    """Stores subject-based attainment results for a pupil."""

    __tablename__ = 'subject_results'

    id = db.Column(db.Integer, primary_key=True)
    pupil_id = db.Column(db.Integer, db.ForeignKey('pupils.id'), nullable=False)
    academic_year = db.Column(db.String(20), nullable=False)
    term = db.Column(db.String(20), nullable=False)
    subject = db.Column(db.String(20), nullable=False)
    paper_1_score = db.Column(db.Integer, nullable=True)
    paper_2_score = db.Column(db.Integer, nullable=True)
    combined_score = db.Column(db.Integer, nullable=True)
    combined_percent = db.Column(db.Float, nullable=True)
    band_label = db.Column(db.String(50), nullable=True)
    source = db.Column(db.String(20), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    pupil = db.relationship('Pupil', back_populates='subject_results')

    def __repr__(self) -> str:
        return f'<SubjectResult {self.subject} {self.term}>'
