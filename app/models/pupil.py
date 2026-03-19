"""Pupil model definitions."""

from datetime import datetime, UTC

from app.extensions import db


class Pupil(db.Model):
    """Stores a pupil's core demographic and class membership details."""

    __tablename__ = 'pupils'

    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    gender = db.Column(db.String(20), nullable=False)
    pupil_premium = db.Column(db.Boolean, nullable=False, default=False)
    laps = db.Column(db.Boolean, nullable=False, default=False)
    service_child = db.Column(db.Boolean, nullable=False, default=False)
    class_id = db.Column(db.Integer, db.ForeignKey('school_classes.id'), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(UTC))

    school_class = db.relationship('SchoolClass', back_populates='pupils')
    subject_results = db.relationship('SubjectResult', back_populates='pupil', cascade='all, delete-orphan')
    writing_results = db.relationship('WritingResult', back_populates='pupil', cascade='all, delete-orphan')
    interventions = db.relationship('Intervention', back_populates='pupil', cascade='all, delete-orphan')
    sats_results = db.relationship('SatsResult', back_populates='pupil', cascade='all, delete-orphan')

    @property
    def full_name(self) -> str:
        return f'{self.first_name} {self.last_name}'

    def __repr__(self) -> str:
        return f'<Pupil {self.full_name}>'
