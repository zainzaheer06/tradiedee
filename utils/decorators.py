"""
Authentication and authorization decorators
"""
from functools import wraps
from flask import session, flash, redirect, url_for
from models import User, db


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login first', 'warning')
            return redirect(url_for('core.login'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login first', 'warning')
            return redirect(url_for('core.login'))
        user = User.query.get(session['user_id'])
        if not user or not user.is_admin:
            flash('Admin access required', 'danger')
            return redirect(url_for('core.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def approved_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = db.session.get(User, session['user_id'])
        if not user.is_approved and not user.is_admin:
            flash('Your account is pending admin approval', 'warning')
            return redirect(url_for('core.pending_approval'))
        return f(*args, **kwargs)
    return decorated_function
