"""Academic-year history models."""

from datetime import datetime, timezone

from app.extensions import db


class AcademicYear(db.Model):
    """Known academic years for admin filtering and promotion."""

    __tablename__ = 'academic_years'

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=True, index=True)
    name = db.Column(db.String(20), nullable=False, unique=True)
    is_current = db.Column(db.Boolean, nullable=False, default=False)
    is_archived = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    def __repr__(self) -> str:
        return f'<AcademicYear {self.name}>'


class PupilClassHistory(db.Model):
    """Snapshot of a pupil's class membership for an academic year."""

    __tablename__ = 'pupil_class_history'
    __table_args__ = (
        db.UniqueConstraint('pupil_id', 'academic_year', name='uq_pupil_class_history_scope'),
        db.Index('ix_pupil_class_history_year_group', 'academic_year', 'year_group'),
    )

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=True, index=True)
    pupil_id = db.Column(db.Integer, db.ForeignKey('pupils.id'), nullable=False, index=True)
    academic_year = db.Column(db.String(20), nullable=False, index=True)
    class_name = db.Column(db.String(120), nullable=False)
    year_group = db.Column(db.Integer, nullable=False)
    teacher_username = db.Column(db.String(80), nullable=True)
    promoted_to_year_group = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    pupil = db.relationship('Pupil', back_populates='class_history')

    def __repr__(self) -> str:
        return f'<PupilClassHistory pupil={self.pupil_id} year={self.academic_year}>'
