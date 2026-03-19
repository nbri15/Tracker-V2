"""Admin forms for assessment settings."""

from flask_wtf import FlaskForm
from wtforms import FloatField, IntegerField, SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, NumberRange, Optional

from app.services import CORE_SUBJECTS, TERMS, format_subject_name


class AssessmentSettingForm(FlaskForm):
    """Add or update assessment setting rows."""

    year_group = SelectField(
        'Year group',
        coerce=int,
        choices=[(year, f'Year {year}') for year in range(1, 7)],
        validators=[DataRequired()],
    )
    subject = SelectField(
        'Subject',
        choices=[(subject, format_subject_name(subject)) for subject in CORE_SUBJECTS],
        validators=[DataRequired()],
    )
    term = SelectField('Term', choices=TERMS, validators=[DataRequired()])
    paper_1_name = StringField('Paper 1 name', validators=[DataRequired()])
    paper_1_max = IntegerField('Paper 1 max', validators=[DataRequired(), NumberRange(min=0)])
    paper_2_name = StringField('Paper 2 name', validators=[DataRequired()])
    paper_2_max = IntegerField('Paper 2 max', validators=[DataRequired(), NumberRange(min=0)])
    combined_max = IntegerField('Combined max', validators=[Optional(), NumberRange(min=1)])
    below_are_threshold_percent = FloatField('Working Towards below %', validators=[DataRequired(), NumberRange(min=0, max=100)])
    on_track_threshold_percent = FloatField('On Track from %', validators=[DataRequired(), NumberRange(min=0, max=100)])
    exceeding_threshold_percent = FloatField('Exceeding from %', validators=[DataRequired(), NumberRange(min=0, max=100)])
    submit = SubmitField('Save setting')
