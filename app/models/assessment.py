"""Assessment, GAP, and subject result models."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from app.extensions import db


class AssessmentSetting(db.Model):
    """Editable assessment thresholds by year group, subject, and term."""

    __tablename__ = 'assessment_settings'
    __table_args__ = (
        db.UniqueConstraint('year_group', 'subject', 'term', name='uq_assessment_setting_scope'),
    )

    id = db.Column(db.Integer, primary_key=True)
    year_group = db.Column(db.Integer, nullable=False, index=True)
    subject = db.Column(db.String(20), nullable=False, index=True)
    term = db.Column(db.String(20), nullable=False, index=True)
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
        db.Index('ix_subject_results_lookup', 'academic_year', 'term', 'subject'),
    )

    id = db.Column(db.Integer, primary_key=True)
    pupil_id = db.Column(db.Integer, db.ForeignKey('pupils.id'), nullable=False, index=True)
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
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

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


class GapTemplate(db.Model):
    """Spreadsheet-style GAP / QLA template for a year group, subject, and term."""

    __tablename__ = 'gap_templates'
    __table_args__ = (
        db.UniqueConstraint('year_group', 'subject', 'term', 'academic_year', name='uq_gap_template_scope'),
    )

    id = db.Column(db.Integer, primary_key=True)
    year_group = db.Column(db.Integer, nullable=False, index=True)
    subject = db.Column(db.String(20), nullable=False, index=True)
    term = db.Column(db.String(20), nullable=False, index=True)
    academic_year = db.Column(db.String(20), nullable=True, index=True)
    paper_name = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    questions = db.relationship(
        'GapQuestion',
        back_populates='template',
        cascade='all, delete-orphan',
        order_by='GapQuestion.display_order',
    )

    @property
    def max_total(self) -> int:
        return sum(question.max_score or 0 for question in self.questions)

    def __repr__(self) -> str:
        return f'<GapTemplate Y{self.year_group} {self.subject} {self.term} {self.academic_year}>'


class GapQuestion(db.Model):
    """A single question or strand column inside a GAP template."""

    __tablename__ = 'gap_questions'
    __table_args__ = (
        db.Index('ix_gap_questions_template_order', 'template_id', 'display_order'),
    )

    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey('gap_templates.id'), nullable=False)
    paper_key = db.Column(db.String(20), nullable=False, default='paper_1', server_default='paper_1')
    question_label = db.Column(db.String(20), nullable=False)
    question_type = db.Column(db.String(120), nullable=True)
    max_score = db.Column(db.Integer, nullable=False, default=1)
    display_order = db.Column(db.Integer, nullable=False, default=0)

    template = db.relationship('GapTemplate', back_populates='questions')
    scores = db.relationship('GapScore', back_populates='question', cascade='all, delete-orphan')

    def __repr__(self) -> str:
        return f'<GapQuestion {self.question_label}>'


class GapScore(db.Model):
    """Per-pupil score for one question in a GAP template."""

    __tablename__ = 'gap_scores'
    __table_args__ = (
        db.UniqueConstraint('pupil_id', 'question_id', name='uq_gap_score_scope'),
        db.Index('ix_gap_scores_pupil_question', 'pupil_id', 'question_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    pupil_id = db.Column(db.Integer, db.ForeignKey('pupils.id'), nullable=False, index=True)
    question_id = db.Column(db.Integer, db.ForeignKey('gap_questions.id'), nullable=False, index=True)
    score = db.Column(db.Float, nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    pupil = db.relationship('Pupil', back_populates='gap_scores')
    question = db.relationship('GapQuestion', back_populates='scores')

    def __repr__(self) -> str:
        return f'<GapScore pupil={self.pupil_id} question={self.question_id}>'


class PhonicsTestColumn(db.Model):
    """Editable phonics test column configuration by year group."""

    __tablename__ = 'phonics_test_columns'
    __table_args__ = (
        db.UniqueConstraint('year_group', 'name', name='uq_phonics_test_column_name'),
        db.Index('ix_phonics_test_columns_scope', 'year_group', 'display_order'),
    )

    id = db.Column(db.Integer, primary_key=True)
    year_group = db.Column(db.Integer, nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    display_order = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    scores = db.relationship('PhonicsScore', back_populates='test_column', cascade='all, delete-orphan')

    def __repr__(self) -> str:
        return f'<PhonicsTestColumn Y{self.year_group} {self.name}>'


class PhonicsScore(db.Model):
    """Per-pupil phonics score for one named test column."""

    __tablename__ = 'phonics_scores'
    __table_args__ = (
        db.UniqueConstraint('pupil_id', 'academic_year', 'phonics_test_column_id', name='uq_phonics_score_scope'),
        db.Index('ix_phonics_scores_lookup', 'academic_year', 'phonics_test_column_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    pupil_id = db.Column(db.Integer, db.ForeignKey('pupils.id'), nullable=False, index=True)
    academic_year = db.Column(db.String(20), nullable=False, index=True)
    phonics_test_column_id = db.Column(db.Integer, db.ForeignKey('phonics_test_columns.id'), nullable=False, index=True)
    score = db.Column(db.Integer, nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    pupil = db.relationship('Pupil', back_populates='phonics_scores')
    test_column = db.relationship('PhonicsTestColumn', back_populates='scores')

    def __repr__(self) -> str:
        return f'<PhonicsScore pupil={self.pupil_id} column={self.phonics_test_column_id}>'
