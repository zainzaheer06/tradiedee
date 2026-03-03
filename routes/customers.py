"""
Customer Management Routes
Handles customer listing, detail views, and auto-backfilling from jobs
"""

import logging
from flask import Blueprint, request, render_template, session, redirect, url_for
from datetime import datetime
from functools import wraps

from models import db, Customer, Job, Business
from utils.decorators import login_required

logger = logging.getLogger(__name__)

customers_bp = Blueprint('customers', __name__, url_prefix='/customers')


def require_business(f):
    """Decorator to check if user has business configured"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')
        if not user_id:
            return redirect(url_for('core.login'))
        business = Business.query.filter_by(user_id=user_id).first()
        if not business:
            return redirect(url_for('business_setup.setup'))
        return f(*args, business=business, **kwargs)
    return decorated_function


def backfill_customers(business_id):
    """Create Customer records from existing jobs that have no customer_id"""
    orphan_jobs = Job.query.filter(
        Job.business_id == business_id,
        Job.customer_id.is_(None),
        Job.customer_phone.isnot(None),
        Job.customer_phone != ''
    ).all()

    if not orphan_jobs:
        return

    for job in orphan_jobs:
        # Find existing customer by phone within this business
        existing = Customer.query.filter_by(
            business_id=business_id,
            phone=job.customer_phone
        ).first()

        if existing:
            job.customer_id = existing.id
            # Update customer info if newer job has better data
            if job.customer_name and not existing.name:
                existing.name = job.customer_name
            if job.customer_email and not existing.email:
                existing.email = job.customer_email
            if job.customer_address and not existing.address:
                existing.address = job.customer_address
            if job.customer_suburb and not existing.suburb:
                existing.suburb = job.customer_suburb
            if job.customer_postcode and not existing.postcode:
                existing.postcode = job.customer_postcode
        else:
            customer = Customer(
                business_id=business_id,
                name=job.customer_name,
                phone=job.customer_phone,
                email=job.customer_email,
                address=job.customer_address,
                suburb=job.customer_suburb,
                postcode=job.customer_postcode,
            )
            db.session.add(customer)
            db.session.flush()  # Get the ID
            job.customer_id = customer.id

    db.session.commit()
    logger.info(f"Backfilled {len(orphan_jobs)} jobs with customer records for business {business_id}")


def find_or_create_customer(business_id, data):
    """Find existing customer by phone or create a new one. Returns Customer instance."""
    phone = data.get('customer_phone', '').strip()
    if not phone:
        return None

    customer = Customer.query.filter_by(business_id=business_id, phone=phone).first()

    if customer:
        # Update with any new info
        if data.get('customer_name') and not customer.name:
            customer.name = data['customer_name']
        if data.get('customer_email') and not customer.email:
            customer.email = data['customer_email']
        if data.get('customer_address') and not customer.address:
            customer.address = data['customer_address']
        if data.get('customer_suburb') and not customer.suburb:
            customer.suburb = data['customer_suburb']
        if data.get('customer_postcode') and not customer.postcode:
            customer.postcode = data['customer_postcode']
    else:
        customer = Customer(
            business_id=business_id,
            name=data.get('customer_name'),
            phone=phone,
            email=data.get('customer_email'),
            address=data.get('customer_address'),
            suburb=data.get('customer_suburb'),
            postcode=data.get('customer_postcode'),
        )
        db.session.add(customer)
        db.session.flush()

    return customer


@customers_bp.route('/', methods=['GET'])
@login_required
@require_business
def customer_list(business):
    """List all customers for this business"""
    try:
        # Backfill any orphan jobs
        backfill_customers(business.id)

        search = request.args.get('search', '').strip()

        query = Customer.query.filter_by(business_id=business.id)

        if search:
            query = query.filter(
                db.or_(
                    Customer.name.ilike(f'%{search}%'),
                    Customer.phone.ilike(f'%{search}%'),
                    Customer.email.ilike(f'%{search}%'),
                    Customer.suburb.ilike(f'%{search}%'),
                )
            )

        customers = query.order_by(Customer.created_at.desc()).all()

        # Attach job counts
        for c in customers:
            c.job_count = Job.query.filter_by(customer_id=c.id).count()
            last_job = Job.query.filter_by(customer_id=c.id).order_by(Job.created_at.desc()).first()
            c.last_job_date = last_job.created_at if last_job else None

        return render_template(
            'customers/list.html',
            customers=customers,
            business=business,
            search=search,
            total=len(customers),
        )

    except Exception as e:
        logger.error(f"Error loading customer list: {str(e)}")
        return render_template('customers/list.html', customers=[], business=business, search='', total=0)


@customers_bp.route('/<int:customer_id>', methods=['GET'])
@login_required
@require_business
def customer_detail(customer_id, business):
    """View customer details with job history"""
    customer = Customer.query.filter_by(id=customer_id, business_id=business.id).first()
    if not customer:
        return redirect(url_for('customers.customer_list'))

    jobs = Job.query.filter_by(customer_id=customer.id).order_by(Job.created_at.desc()).all()

    return render_template(
        'customers/detail.html',
        customer=customer,
        jobs=jobs,
        business=business,
    )
