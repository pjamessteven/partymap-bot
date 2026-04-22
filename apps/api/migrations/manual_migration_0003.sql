-- Manual Database Migration
-- Run this SQL in your PostgreSQL database

-- Add new columns to festivals table
ALTER TABLE festivals 
    ADD COLUMN IF NOT EXISTS update_required BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS update_reasons JSONB DEFAULT '[]',
    ADD COLUMN IF NOT EXISTS existing_event_data JSONB,
    ADD COLUMN IF NOT EXISTS workflow_type VARCHAR(20),
    ADD COLUMN IF NOT EXISTS goabase_modified VARCHAR(50);

-- Change partymap_event_id from UUID to INTEGER
-- Note: This will lose existing data if any
ALTER TABLE festivals 
    ALTER COLUMN partymap_event_id TYPE INTEGER 
    USING (NULL);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_festivals_update_required ON festivals(update_required);
CREATE INDEX IF NOT EXISTS idx_festivals_workflow_type ON festivals(workflow_type);
CREATE INDEX IF NOT EXISTS idx_festivals_goabase_modified ON festivals(goabase_modified);

-- Add new system settings for Goabase
INSERT INTO system_settings (key, value, value_type, description, editable, category)
VALUES 
    ('goabase_sync_enabled', 'true', 'boolean', 'Enable automatic Goabase sync', true, 'goabase'),
    ('goabase_sync_frequency', 'weekly', 'string', 'Frequency: daily, weekly, monthly', true, 'goabase'),
    ('goabase_sync_day', 'sunday', 'string', 'Day of week for sync', true, 'goabase'),
    ('goabase_sync_hour', '2', 'integer', 'Hour (0-23) for sync', true, 'goabase'),
    ('discovery_enabled', 'true', 'boolean', 'Enable discovery pipeline', true, 'pipeline'),
    ('research_enabled', 'true', 'boolean', 'Enable research pipeline', true, 'pipeline'),
    ('sync_enabled', 'true', 'boolean', 'Enable sync pipeline', true, 'pipeline')
ON CONFLICT (key) DO NOTHING;

-- Update existing festivals to new states
UPDATE festivals 
SET state = 'needs_research_new', 
    workflow_type = 'new'
WHERE state = 'discovered';

-- Verify migration
SELECT 
    'New columns added' as status,
    COUNT(*) as total_festivals,
    SUM(CASE WHEN state = 'needs_research_new' THEN 1 ELSE 0 END) as new_workflow,
    SUM(CASE WHEN state = 'needs_research_update' THEN 1 ELSE 0 END) as update_workflow
FROM festivals;
