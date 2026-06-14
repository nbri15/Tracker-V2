"""Maths Fundamentals assessment models."""

from datetime import datetime, timezone

from app.extensions import db


class FundamentalStrand(db.Model):
    __tablename__ = 'fundamental_strands'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), nullable=False, unique=True, index=True)
    name = db.Column(db.String(140), nullable=False)
    description = db.Column(db.Text, nullable=True)

    levels = db.relationship('FundamentalLevel', back_populates='strand', cascade='all, delete-orphan')
    questions = db.relationship('FundamentalQuestion', back_populates='strand', cascade='all, delete-orphan')
    sessions = db.relationship('FundamentalSession', back_populates='strand')


class FundamentalLevel(db.Model):
    __tablename__ = 'fundamental_levels'
    __table_args__ = (db.UniqueConstraint('strand_id', 'level_number', name='uq_fundamental_level_strand_number'),)

    id = db.Column(db.Integer, primary_key=True)
    strand_id = db.Column(db.Integer, db.ForeignKey('fundamental_strands.id'), nullable=False, index=True)
    level_number = db.Column(db.Integer, nullable=False, index=True)
    skill = db.Column(db.String(255), nullable=False)
    expected_year = db.Column(db.String(80), nullable=True)
    pass_mark = db.Column(db.Integer, nullable=False, default=70)

    strand = db.relationship('FundamentalStrand', back_populates='levels')


class FundamentalQuestion(db.Model):
    __tablename__ = 'fundamental_questions'
    __table_args__ = (db.UniqueConstraint('strand_id', 'question_id', name='uq_fundamental_question_strand_question_id'),)

    id = db.Column(db.Integer, primary_key=True)
    strand_id = db.Column(db.Integer, db.ForeignKey('fundamental_strands.id'), nullable=False, index=True)
    level_number = db.Column(db.Integer, nullable=False, index=True)
    question_id = db.Column(db.String(60), nullable=False, index=True)
    question_type = db.Column(db.String(80), nullable=True)
    question_text = db.Column(db.Text, nullable=False)
    answer = db.Column(db.String(255), nullable=False)

    strand = db.relationship('FundamentalStrand', back_populates='questions')
    responses = db.relationship('FundamentalResponse', back_populates='question')


class FundamentalSession(db.Model):
    __tablename__ = 'fundamental_sessions'

    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('school_classes.id'), nullable=False, index=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    strand_id = db.Column(db.Integer, db.ForeignKey('fundamental_strands.id'), nullable=False, index=True)
    start_level = db.Column(db.Integer, nullable=False, default=1)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    school_class = db.relationship('SchoolClass')
    teacher = db.relationship('User')
    strand = db.relationship('FundamentalStrand', back_populates='sessions')
    attempts = db.relationship('FundamentalPupilAttempt', back_populates='session', cascade='all, delete-orphan')


class FundamentalPupilAttempt(db.Model):
    __tablename__ = 'fundamental_pupil_attempts'
    __table_args__ = (db.UniqueConstraint('session_id', 'pupil_id', name='uq_fundamental_attempt_session_pupil'),)

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('fundamental_sessions.id'), nullable=False, index=True)
    pupil_id = db.Column(db.Integer, db.ForeignKey('pupils.id'), nullable=False, index=True)
    current_level = db.Column(db.Integer, nullable=False)
    secure_level = db.Column(db.Integer, nullable=True)
    intervention_level = db.Column(db.Integer, nullable=True)
    below_70_streak = db.Column(db.Integer, nullable=False, default=0)
    is_complete = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    completed_at = db.Column(db.DateTime, nullable=True)

    session = db.relationship('FundamentalSession', back_populates='attempts')
    pupil = db.relationship('Pupil')
    responses = db.relationship('FundamentalResponse', back_populates='attempt', cascade='all, delete-orphan')


class FundamentalResponse(db.Model):
    __tablename__ = 'fundamental_responses'

    id = db.Column(db.Integer, primary_key=True)
    attempt_id = db.Column(db.Integer, db.ForeignKey('fundamental_pupil_attempts.id'), nullable=False, index=True)
    question_id = db.Column(db.Integer, db.ForeignKey('fundamental_questions.id'), nullable=False, index=True)
    level_number = db.Column(db.Integer, nullable=False, index=True)
    pupil_answer = db.Column(db.String(255), nullable=True)
    is_correct = db.Column(db.Boolean, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    attempt = db.relationship('FundamentalPupilAttempt', back_populates='responses')
    question = db.relationship('FundamentalQuestion', back_populates='responses')
