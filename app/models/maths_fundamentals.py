"""Standalone Maths Fundamentals model definitions."""

from __future__ import annotations

from datetime import datetime, timezone
import secrets

from app.extensions import db


class MathsFundamentalStrand(db.Model):
    """A configurable Maths Fundamentals strand imported from the ladder spreadsheet."""

    __tablename__ = 'maths_fundamental_strands'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True, index=True)
    display_order = db.Column(db.Integer, nullable=False, default=0, index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)

    skills = db.relationship('MathsFundamentalSkill', back_populates='strand', cascade='all, delete-orphan', lazy='dynamic')
    results = db.relationship('MathsFundamentalResult', back_populates='strand', cascade='all, delete-orphan')
    sessions = db.relationship('MathsFundamentalsSession', back_populates='strand', cascade='all, delete-orphan')

    def __repr__(self) -> str:
        return f'<MathsFundamentalStrand {self.name}>'


class MathsFundamentalSkill(db.Model):
    """A ladder skill, teaching prompt and source question prompt for a strand/level."""

    __tablename__ = 'maths_fundamental_skills'
    __table_args__ = (
        db.Index('ix_mf_skills_strand_level_order', 'strand_id', 'level', 'display_order'),
    )

    id = db.Column(db.Integer, primary_key=True)
    strand_id = db.Column(db.Integer, db.ForeignKey('maths_fundamental_strands.id'), nullable=False, index=True)
    level = db.Column(db.Integer, nullable=False, index=True)
    band = db.Column(db.String(80), nullable=True)
    skill_text = db.Column(db.Text, nullable=False)
    teaching_prompt = db.Column(db.Text, nullable=True)
    question_prompt = db.Column(db.Text, nullable=True)
    question_type = db.Column(db.String(80), nullable=True)
    evidence = db.Column(db.Text, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    display_order = db.Column(db.Integer, nullable=False, default=0)

    strand = db.relationship('MathsFundamentalStrand', back_populates='skills')
    templates = db.relationship('MathsQuestionTemplate', back_populates='skill', cascade='all, delete-orphan', lazy='dynamic')
    questions = db.relationship('MathsFundamentalQuestion', back_populates='skill')

    def __repr__(self) -> str:
        return f'<MathsFundamentalSkill {self.strand_id} L{self.level}>'


class MathsQuestionTemplate(db.Model):
    """Question generator template for dynamic Maths Fundamentals assessments."""

    __tablename__ = 'maths_question_templates'

    id = db.Column(db.Integer, primary_key=True)
    skill_id = db.Column(db.Integer, db.ForeignKey('maths_fundamental_skills.id'), nullable=False, index=True)
    generator_type = db.Column(db.String(80), nullable=False, default='template')
    template_text = db.Column(db.Text, nullable=False)
    generator_config_json = db.Column(db.Text, nullable=True)
    answer_type = db.Column(db.String(80), nullable=False, default='text')
    difficulty = db.Column(db.String(40), nullable=False, default='standard')
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)

    skill = db.relationship('MathsFundamentalSkill', back_populates='templates')


class MathsFundamentalResult(db.Model):
    """Current secure level for one pupil/strand/year."""

    __tablename__ = 'maths_fundamental_results'
    __table_args__ = (
        db.UniqueConstraint('school_id', 'pupil_id', 'academic_year', 'strand_id', name='uq_mf_result_pupil_year_strand'),
        db.Index('ix_mf_results_school_year_strand', 'school_id', 'academic_year', 'strand_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False, index=True)
    pupil_id = db.Column(db.Integer, db.ForeignKey('pupils.id'), nullable=False, index=True)
    academic_year = db.Column(db.String(20), nullable=False, index=True)
    strand_id = db.Column(db.Integer, db.ForeignKey('maths_fundamental_strands.id'), nullable=False, index=True)
    current_level = db.Column(db.Integer, nullable=False, default=0)
    current_skill_id = db.Column(db.Integer, db.ForeignKey('maths_fundamental_skills.id'), nullable=True)
    last_assessed = db.Column(db.DateTime, nullable=True)
    next_step = db.Column(db.Text, nullable=True)
    teacher_note = db.Column(db.Text, nullable=True)

    school = db.relationship('School')
    pupil = db.relationship('Pupil', backref=db.backref('maths_fundamental_results', cascade='all, delete-orphan'))
    strand = db.relationship('MathsFundamentalStrand', back_populates='results')
    current_skill = db.relationship('MathsFundamentalSkill')


class MathsFundamentalAttempt(db.Model):
    """One adaptive Maths Fundamentals assessment attempt."""

    __tablename__ = 'maths_fundamental_attempts'
    __table_args__ = (
        db.Index('ix_mf_attempt_school_pupil_year', 'school_id', 'pupil_id', 'academic_year'),
    )

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False, index=True)
    pupil_id = db.Column(db.Integer, db.ForeignKey('pupils.id'), nullable=False, index=True)
    strand_id = db.Column(db.Integer, db.ForeignKey('maths_fundamental_strands.id'), nullable=False, index=True)
    academic_year = db.Column(db.String(20), nullable=False, index=True)
    started_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    completed_at = db.Column(db.DateTime, nullable=True)
    final_level = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(30), nullable=False, default='in_progress', index=True)
    session_id = db.Column(db.Integer, db.ForeignKey('maths_fundamentals_sessions.id'), nullable=True, index=True)
    current_level = db.Column(db.Integer, nullable=False, default=1)
    questions_per_level = db.Column(db.Integer, nullable=False, default=3)
    last_activity_at = db.Column(db.DateTime, nullable=True)

    school = db.relationship('School')
    pupil = db.relationship('Pupil')
    strand = db.relationship('MathsFundamentalStrand')
    session = db.relationship('MathsFundamentalsSession', back_populates='attempts')
    questions = db.relationship('MathsFundamentalQuestion', back_populates='attempt', cascade='all, delete-orphan', order_by='MathsFundamentalQuestion.id')


class MathsFundamentalQuestion(db.Model):
    """Generated question stored exactly as asked."""

    __tablename__ = 'maths_fundamental_questions'

    id = db.Column(db.Integer, primary_key=True)
    attempt_id = db.Column(db.Integer, db.ForeignKey('maths_fundamental_attempts.id'), nullable=False, index=True)
    skill_id = db.Column(db.Integer, db.ForeignKey('maths_fundamental_skills.id'), nullable=False, index=True)
    question_text = db.Column(db.Text, nullable=False)
    correct_answer = db.Column(db.String(255), nullable=True)
    pupil_answer = db.Column(db.String(255), nullable=True)
    is_correct = db.Column(db.Boolean, nullable=True)
    teacher_mark_required = db.Column(db.Boolean, nullable=False, default=False)
    level = db.Column(db.Integer, nullable=False, default=1, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    answered_at = db.Column(db.DateTime, nullable=True)

    attempt = db.relationship('MathsFundamentalAttempt', back_populates='questions')
    skill = db.relationship('MathsFundamentalSkill', back_populates='questions')


class MathsFundamentalsSession(db.Model):
    """Teacher-controlled QR assessment session."""

    __tablename__ = 'maths_fundamentals_sessions'
    __table_args__ = (
        db.Index('ix_mf_sessions_school_class_open', 'school_id', 'class_id', 'is_open'),
    )

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False, index=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    class_id = db.Column(db.Integer, db.ForeignKey('school_classes.id'), nullable=True, index=True)
    strand_id = db.Column(db.Integer, db.ForeignKey('maths_fundamental_strands.id'), nullable=False, index=True)
    academic_year = db.Column(db.String(20), nullable=False, index=True)
    is_open = db.Column(db.Boolean, nullable=False, default=True, index=True)
    opened_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    closed_at = db.Column(db.DateTime, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    starting_level = db.Column(db.Integer, nullable=False, default=1)
    questions_per_level = db.Column(db.Integer, nullable=False, default=3)
    group_name = db.Column(db.String(120), nullable=True)

    school = db.relationship('School')
    teacher = db.relationship('User')
    school_class = db.relationship('SchoolClass')
    strand = db.relationship('MathsFundamentalStrand', back_populates='sessions')
    attempts = db.relationship('MathsFundamentalAttempt', back_populates='session', cascade='all, delete-orphan')

    @property
    def is_available(self) -> bool:
        now = datetime.now(timezone.utc)
        return bool(self.is_open and (self.expires_at is None or self.expires_at > now))


class PupilQrToken(db.Model):
    """Permanent secure QR token for a pupil without exposing pupil IDs."""

    __tablename__ = 'pupil_qr_tokens'
    __table_args__ = (
        db.UniqueConstraint('token', name='uq_pupil_qr_token_token'),
        db.UniqueConstraint('school_id', 'pupil_id', name='uq_pupil_qr_token_pupil'),
    )

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False, index=True)
    pupil_id = db.Column(db.Integer, db.ForeignKey('pupils.id'), nullable=False, index=True)
    token = db.Column(db.String(96), nullable=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    last_used_at = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)

    school = db.relationship('School')
    pupil = db.relationship('Pupil')

    @staticmethod
    def generate_token() -> str:
        return secrets.token_urlsafe(32)
