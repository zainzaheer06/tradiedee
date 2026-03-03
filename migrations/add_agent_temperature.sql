-- Migration: Add temperature field to Agent model
-- Date: 2025-12-11
-- Description: Enable per-agent temperature control for LLM creativity (0.2-0.6)

-- Add temperature field to Agent table
ALTER TABLE agent ADD COLUMN temperature FLOAT DEFAULT 0.4 NOT NULL;

-- Update existing agents to use default temperature (0.4 - balanced)
UPDATE agent SET temperature = 0.4 WHERE temperature IS NULL;
