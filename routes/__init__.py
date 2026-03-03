"""
Routes package - Blueprint registration for all application routes
"""


def register_blueprints(app):
    """Register all application blueprints"""
    from .core import core_bp
    from .agents import agents_bp
    from .campaigns import campaigns_bp
    from .inbound import inbound_bp
    from .public_api import public_api_bp
    from .workflows import workflows_bp
    from .test_agent import test_agent_bp
    from .api_v1 import api_v1_bp
    from .whatsapp import whatsapp_bp
    from .clinic import clinic_bp

    # Phase 1: CallTradie Features
    from .jobs import jobs_bp
    from .booking import booking_bp
    from .address import address_bp
    from .business_setup import business_setup_bp
    from .phase1 import phase1_bp
    from .voice import voice_bp
    from .sms import sms_bp
    from .customers import customers_bp

    # Register blueprints in order
    app.register_blueprint(core_bp)
    app.register_blueprint(agents_bp, url_prefix='/agent')
    app.register_blueprint(campaigns_bp, url_prefix='/outbound')
    app.register_blueprint(inbound_bp, url_prefix='/inbound')
    app.register_blueprint(workflows_bp)  # Workflows API (has /api/workflows prefix)
    app.register_blueprint(public_api_bp)  # Public API has its own prefix defined in blueprint
    app.register_blueprint(test_agent_bp, url_prefix='/test-agent')  # Test agent via browser
    app.register_blueprint(api_v1_bp)  # API v1 for external integrations (/api/v1/*)
    app.register_blueprint(whatsapp_bp, url_prefix='/whatsapp')  # WhatsApp agent management
    app.register_blueprint(clinic_bp)  # Clinic platform pages (/clinic/*)

    # Phase 1: CallTradie Features - Booking, Jobs, Address Validation, Voice, SMS
    app.register_blueprint(phase1_bp)  # Phase 1 home & test dashboard (/*)
    app.register_blueprint(jobs_bp)  # Job management (/jobs/*)
    app.register_blueprint(booking_bp)  # Appointment booking (/api/booking/*)
    app.register_blueprint(address_bp)  # Address validation (/api/address/*)
    app.register_blueprint(business_setup_bp)  # Business setup (/setup/*)
    app.register_blueprint(voice_bp)  # Voice call system (/voice/*)
    app.register_blueprint(sms_bp)  # SMS management (/api/sms/*)
    app.register_blueprint(customers_bp)  # Customer management (/customers/*)
