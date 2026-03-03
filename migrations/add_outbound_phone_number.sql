-- Migration: Add outbound_phone_number field to User model
-- Date: 2026-02-03
-- Description: Store phone number alongside trunk ID for accurate call log "From Number" display

-- Add outbound_phone_number field to User table
ALTER TABLE user ADD COLUMN outbound_phone_number VARCHAR(20);
