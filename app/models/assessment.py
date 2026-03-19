"""Assessment threshold and subject result models."""

from __future__ import annotations

from datetime import datetime, UTC
from decimal import Decimal, ROUND_HALF_UP

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
    __table_args__ = (
        db.UniqueConstraint('pupil_id', 'academic_year', 'term', 'subject', name='uq_subject_result_scope'),
    )

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

    @staticmethod
    def calculate_combined_score(paper_1_score: int | None, paper_2_score: int | None) -> int | None:
        """Return the combined score when both paper scores are available."""

        if paper_1_score is None or paper_2_score is None:
            return None
        return paper_1_score + paper_2_score

    @staticmethod
    def calculate_percent(combined_score: int | None, combined_max: int | None) -> float | None:
        """Return the combined percentage rounded to 1 decimal place."""

        if combined_score is None or not combined_max:
            return None
        percent = Decimal(str((combined_score / combined_max) * 100)).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
        return float(percent)

    @staticmethod
    def calculate_band_label(
        percent: float | None,
        below_are_threshold_percent: float | None,
        exceeding_threshold_percent: float | None,
    ) -> str | None:
        """Return the category band label for a given percentage."""

        if percent is None:
            return None
        if below_are_threshold_percent is not None and percent < below_are_threshold_percent:
            return 'Working Towards'
        if exceeding_threshold_percent is not None and percent >= exceeding_threshold_percent:
            return 'Exceeding'
        return 'On Track'

    def __repr__(self) -> str:
        return f'<SubjectResult {self.subject} {self.term}>'
