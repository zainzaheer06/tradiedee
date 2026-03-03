-- Migration: Add SIP Trunk fields to User and Agent models
-- Date: 2025-01-18
-- Description: Enable multi-tenant SIP trunk support

-- Add trunk fields to User table (for outbound calls)
ALTER TABLE user ADD COLUMN outbound_trunk_id VARCHAR(100);
ALTER TABLE user ADD COLUMN sip_configured BOOLEAN DEFAULT FALSE;
ALTER TABLE user ADD COLUMN sip_configured_at DATETIME;
ALTER TABLE user ADD COLUMN sip_notes TEXT;

-- Add trunk field to Agent table (for inbound calls)
ALTER TABLE agent ADD COLUMN inbound_trunk_id VARCHAR(100);

-- Update existing users to not be configured
UPDATE user SET sip_configured = FALSE WHERE sip_configured IS NULL;
