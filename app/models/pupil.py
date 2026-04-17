"""Pupil model definitions."""

from datetime import datetime, timezone

from app.extensions import db


class Pupil(db.Model):
    """Stores a pupil's core demographic and class membership details."""

    __tablename__ = 'pupils'

    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(80), nullable=False, index=True)
    last_name = db.Column(db.String(80), nullable=False, index=True)
    gender = db.Column(db.String(20), nullable=False)
    pupil_premium = db.Column(db.Boolean, nullable=False, default=False, index=True)
    laps = db.Column(db.Boolean, nullable=False, default=False, index=True)
    service_child = db.Column(db.Boolean, nullable=False, default=False, index=True)
    class_id = db.Column(db.Integer, db.ForeignKey('school_classes.id'), nullable=False, index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    school_class = db.relationship('SchoolClass', back_populates='pupils')
    subject_results = db.relationship('SubjectResult', back_populates='pupil', cascade='all, delete-orphan')
    writing_results = db.relationship('WritingResult', back_populates='pupil', cascade='all, delete-orphan')
    interventions = db.relationship('Intervention', back_populates='pupil', cascade='all, delete-orphan')
    sats_results = db.relationship('SatsResult', back_populates='pupil', cascade='all, delete-orphan')
    sats_writing_results = db.relationship('SatsWritingResult', back_populates='pupil', cascade='all, delete-orphan')
    sats_column_results = db.relationship('SatsColumnResult', back_populates='pupil', cascade='all, delete-orphan')
    gap_scores = db.relationship('GapScore', back_populates='pupil', cascade='all, delete-orphan')
    class_history = db.relationship('PupilClassHistory', back_populates='pupil', cascade='all, delete-orphan')
    reception_tracker_entries = db.relationship('ReceptionTrackerEntry', back_populates='pupil', cascade='all, delete-orphan')
    phonics_scores = db.relationship('PhonicsScore', back_populates='pupil', cascade='all, delete-orphan')
    times_table_scores = db.relationship('TimesTableScore', back_populates='pupil', cascade='all, delete-orphan')

    @property
    def full_name(self) -> str:
        return f'{self.first_name} {self.last_name}'

    def __repr__(self) -> str:
        return f'<Pupil {self.full_name}>'
