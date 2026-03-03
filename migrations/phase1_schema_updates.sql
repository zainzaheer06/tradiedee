-- Phase 1 Schema Updates for Critical Features
-- Run this migration to add fields for:
-- 1. Scheduling Conflict Prevention
-- 2. Emergency Escalation
-- 3. Address Validation

-- Add columns to User table for business profile
ALTER TABLE "user" ADD COLUMN serviceM8_api_key VARCHAR(200);
ALTER TABLE "user" ADD COLUMN serviceM8_customer_id VARCHAR(100);
ALTER TABLE "user" ADD COLUMN google_api_key VARCHAR(200);
ALTER TABLE "user" ADD COLUMN twilio_phone_number VARCHAR(20);

-- Create Business table (if not exists)
CREATE TABLE IF NOT EXISTS business (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    business_name VARCHAR(200) NOT NULL,
    business_type VARCHAR(100),
    phone_number VARCHAR(20) UNIQUE,
    abn VARCHAR(20),
    address TEXT,

    -- Configuration
    greeting_message TEXT,
    after_hours_enabled BOOLEAN DEFAULT 1,
    tone VARCHAR(20) DEFAULT 'friendly',

    -- Service areas
    service_areas JSON,

    -- Working hours
    working_hours_start VARCHAR(5) DEFAULT '08:00',
    working_hours_end VARCHAR(5) DEFAULT '17:00',
    timezone VARCHAR(50) DEFAULT 'Australia/Sydney',

    -- Availability checking
    availability_check_enabled BOOLEAN DEFAULT 1,
    availability_check_method VARCHAR(50) DEFAULT 'serviceM8',

    -- Fallback contacts
    backup_business_phone VARCHAR(20),
    backup_business_name VARCHAR(100),

    -- Emergency configuration
    emergency_contacts JSON,
    emergency_escalation_enabled BOOLEAN DEFAULT 1,
    emergency_transfer_timeout INTEGER DEFAULT 30,

    -- ServiceM8 integration
    serviceM8_enabled BOOLEAN DEFAULT 0,
    serviceM8_api_key VARCHAR(200),
    serviceM8_customer_id VARCHAR(100),

    -- Cal.com integration
    calcom_enabled BOOLEAN DEFAULT 0,
    calcom_api_key VARCHAR(200),
    calcom_event_type_id VARCHAR(100),

    -- Twilio
    twilio_account_sid VARCHAR(100),
    twilio_auth_token VARCHAR(100),
    twilio_phone_number VARCHAR(20),

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES "user"(id) ON DELETE CASCADE
);

-- Create Job table (replaces CallLog for job tracking)
CREATE TABLE IF NOT EXISTS job (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    business_id INTEGER,

    -- Customer Info
    customer_name VARCHAR(100) NOT NULL,
    customer_phone VARCHAR(20) NOT NULL,
    customer_email VARCHAR(120),
    customer_address TEXT NOT NULL,
    customer_suburb VARCHAR(100) NOT NULL,
    customer_postcode VARCHAR(10) NOT NULL,

    -- Job Details
    job_type VARCHAR(100) NOT NULL,
    description TEXT NOT NULL,

    -- Urgency & Priority
    urgency VARCHAR(20) DEFAULT 'normal',
    is_emergency BOOLEAN DEFAULT 0,
    emergency_keywords_detected JSON,

    -- Scheduling
    preferred_datetime DATETIME,
    scheduled_datetime DATETIME,

    -- Status workflow
    status VARCHAR(20) DEFAULT 'new',

    -- Tracking
    estimated_duration_minutes INTEGER DEFAULT 60,
    actual_duration_minutes INTEGER,
    completion_notes TEXT,

    -- Call & Transcription
    original_call_id INTEGER,
    call_transcript TEXT,
    call_summary TEXT,
    recording_url VARCHAR(500),

    -- Booking confirmation
    booking_confirmed_at DATETIME,
    confirmation_sms_sent BOOLEAN DEFAULT 0,
    reminder_sms_sent BOOLEAN DEFAULT 0,

    -- ServiceM8 Integration
    serviceM8_job_id VARCHAR(100),
    serviceM8_sync_status VARCHAR(20),

    -- Cal.com Integration
    calcom_booking_id VARCHAR(100),
    calendar_event_url VARCHAR(500),

    -- Address validation
    address_validated BOOLEAN DEFAULT 0,
    address_validation_status VARCHAR(20),
    address_components JSON,
    address_coordinates JSON,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES "user"(id) ON DELETE CASCADE,
    FOREIGN KEY (business_id) REFERENCES business(id) ON DELETE CASCADE,
    FOREIGN KEY (original_call_id) REFERENCES call_log(id)
);

-- Create table for tracking address validations
CREATE TABLE IF NOT EXISTS address_validation_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER,
    input_address TEXT,
    validated_address TEXT,
    validation_status VARCHAR(20),
    coordinates JSON,
    attempt_number INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (job_id) REFERENCES job(id) ON DELETE CASCADE
);

-- Create table for emergency escalation tracking
CREATE TABLE IF NOT EXISTS emergency_escalation_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id INTEGER NOT NULL,
    job_id INTEGER,

    emergency_keywords JSON,

    -- Escalation attempts
    contact_1_name VARCHAR(100),
    contact_1_phone VARCHAR(20),
    contact_1_status VARCHAR(20),
    contact_1_answered_at DATETIME,

    contact_2_name VARCHAR(100),
    contact_2_phone VARCHAR(20),
    contact_2_status VARCHAR(20),
    contact_2_answered_at DATETIME,

    contact_3_name VARCHAR(100),
    contact_3_phone VARCHAR(20),
    contact_3_status VARCHAR(20),
    contact_3_answered_at DATETIME,

    -- SMS fallback
    sms_sent_to JSON,
    sms_sent_at DATETIME,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (business_id) REFERENCES business(id) ON DELETE CASCADE,
    FOREIGN KEY (job_id) REFERENCES job(id) ON DELETE CASCADE
);

-- Create table for SMS audit trail
CREATE TABLE IF NOT EXISTS sms_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER,
    business_id INTEGER,

    recipient_phone VARCHAR(20) NOT NULL,
    message_type VARCHAR(50),
    message_body TEXT NOT NULL,

    twilio_message_id VARCHAR(100),
    status VARCHAR(20) DEFAULT 'sent',

    sent_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (job_id) REFERENCES job(id) ON DELETE CASCADE,
    FOREIGN KEY (business_id) REFERENCES business(id) ON DELETE CASCADE
);

-- Create indexes for performance
CREATE INDEX idx_job_business_id ON job(business_id);
CREATE INDEX idx_job_status ON job(status);
CREATE INDEX idx_job_customer_phone ON job(customer_phone);
CREATE INDEX idx_job_scheduled_datetime ON job(scheduled_datetime);
CREATE INDEX idx_emergency_escalation_log_business ON emergency_escalation_log(business_id);
CREATE INDEX idx_sms_log_job ON sms_log(job_id);
