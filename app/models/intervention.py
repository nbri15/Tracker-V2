"""Intervention tracking model."""

from datetime import datetime, timezone

from app.extensions import db


class Intervention(db.Model):
    """Flags pupils requiring intervention support in a subject area."""

    __tablename__ = 'interventions'
    __table_args__ = (
        db.Index('ix_interventions_scope', 'subject', 'term', 'academic_year', 'is_active'),
    )

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=True, index=True)
    pupil_id = db.Column(db.Integer, db.ForeignKey('pupils.id'), nullable=False, index=True)
    subject = db.Column(db.String(20), nullable=False)
    term = db.Column(db.String(20), nullable=False)
    academic_year = db.Column(db.String(20), nullable=False, index=True)
    reason = db.Column(db.String(255), nullable=False)
    note = db.Column(db.Text, nullable=True)
    auto_flagged = db.Column(db.Boolean, nullable=False, default=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    closed_by_teacher = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    is_demo = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    pupil = db.relationship('Pupil', back_populates='interventions')
    programme_assignments = db.relationship('InterventionProgrammeAssignment', back_populates='intervention', cascade='all, delete-orphan', lazy='selectin')

    @property
    def programmes(self):
        return [assignment.programme for assignment in self.programme_assignments]

    def __repr__(self) -> str:
        return f'<Intervention {self.subject}>'


class InterventionProgramme(db.Model):
    """A reusable school-owned support programme; archiving preserves assignments."""
    __tablename__ = 'intervention_programmes'
    __table_args__ = (db.UniqueConstraint('school_id', 'subject', 'name_key', name='uq_intervention_programme_name'),)
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    name_key = db.Column(db.String(120), nullable=False)
    subject = db.Column(db.String(20), nullable=False)
    description = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())


class InterventionProgrammeAssignment(db.Model):
    __tablename__ = 'intervention_programme_assignments'
    intervention_id = db.Column(db.Integer, db.ForeignKey('interventions.id', ondelete='CASCADE'), primary_key=True)
    programme_id = db.Column(db.Integer, db.ForeignKey('intervention_programmes.id', ondelete='CASCADE'), primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False, index=True)
    intervention = db.relationship('Intervention', back_populates='programme_assignments')
    programme = db.relationship('InterventionProgramme', lazy='joined')
