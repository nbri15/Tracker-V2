"""Authentication forms."""

from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, EqualTo, Length


class LoginForm(FlaskForm):
    """Simple username and password login form."""

    username = StringField('Username', validators=[DataRequired(), Length(max=80)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=4, max=128)])
    submit = SubmitField('Sign in')


class ChangePasswordForm(FlaskForm):
    """Password update form used for forced password reset."""

    new_password = PasswordField('New password', validators=[DataRequired(), Length(min=8, max=128)])
    confirm_password = PasswordField(
        'Confirm password',
        validators=[DataRequired(), EqualTo('new_password', message='Passwords must match.')],
    )
    submit = SubmitField('Update password')
