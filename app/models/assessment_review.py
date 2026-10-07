"""Year-scoped setup and short-lived server-side assessment reviews."""
from datetime import datetime, timezone
import secrets
from app.extensions import db


class AssessmentConfiguration(db.Model):
    __tablename__ = 'assessment_configurations'
    __table_args__ = (db.UniqueConstraint('school_id', 'academic_year', 'year_group', 'subject', 'term', name='uq_assessment_configuration_scope'),)
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False, index=True)
    academic_year = db.Column(db.String(20), nullable=False)
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


class AssessmentReview(db.Model):
    __tablename__ = 'assessment_reviews'
    id = db.Column(db.String(64), primary_key=True, default=lambda: secrets.token_urlsafe(32))
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    kind = db.Column(db.String(30), nullable=False)
    payload = db.Column(db.JSON, nullable=False)
    report = db.Column(db.JSON, nullable=False)
    baseline = db.Column(db.String(64), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    confirmed_at = db.Column(db.DateTime, nullable=True)
