"""
Email utility functions for user verification and notifications
"""
from flask import render_template, url_for
from flask_mail import Message
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
import logging
import os

logger = logging.getLogger(__name__)

# Email token serializer (will be initialized in app.py)
serializer = None
mail = None


def init_email_utils(app, mail_instance):
    """Initialize email utilities with app config and mail instance"""
    global serializer, mail
    serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
    mail = mail_instance


def generate_verification_token(email):
    """Generate a time-sensitive email verification token"""
    return serializer.dumps(email, salt='email-verification')


def verify_token(token, expiration=3600):
    """Verify the email token (default: 1 hour expiration)"""
    try:
        email = serializer.loads(token, salt='email-verification', max_age=expiration)
        return email
    except (SignatureExpired, BadSignature):
        return None


def send_verification_email(user_email, username):
    """Send email verification link to user"""
    try:
        token = generate_verification_token(user_email)
        verify_url = url_for('core.verify_email', token=token, _external=True)

        msg = Message(
            subject='Verify Your Email - Voice Agent Platform',
            recipients=[user_email],
            html=render_template('emails/verify_email.html',
                               username=username,
                               verify_url=verify_url)
        )

        mail.send(msg)
        logger.info(f"Verification email sent to {user_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send verification email to {user_email}: {e}")
        return False


def send_approval_notification(user_email, username):
    """Send notification when admin approves the account"""
    try:
        msg = Message(
            subject='Account Approved - Voice Agent Platform',
            recipients=[user_email],
            html=render_template('emails/account_approved.html',
                               username=username,
                               login_url=url_for('core.login', _external=True))
        )

        mail.send(msg)
        logger.info(f"Approval notification sent to {user_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send approval notification to {user_email}: {e}")
        return False
