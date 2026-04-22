-- Migration: Add agent streaming tables
-- Run this SQL to create the new tables for LangGraph streaming

-- Add current_thread_id to festivals
ALTER TABLE festivals ADD COLUMN IF NOT EXISTS current_thread_id VARCHAR(255);
CREATE INDEX IF NOT EXISTS idx_festivals_current_thread ON festivals(current_thread_id);

-- Add thread_id to agent_decisions for backward compatibility
ALTER TABLE agent_decisions ADD COLUMN IF NOT EXISTS thread_id VARCHAR(255);
CREATE INDEX IF NOT EXISTS idx_agent_decisions_thread ON agent_decisions(thread_id);

-- Agent thread tracking table
CREATE TABLE IF NOT EXISTS agent_threads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    festival_id UUID REFERENCES festivals(id) ON DELETE CASCADE,
    thread_id VARCHAR(255) UNIQUE NOT NULL,
    agent_type VARCHAR(50) NOT NULL,
    status VARCHAR(50) DEFAULT 'running',
    checkpoint_ns VARCHAR(255),
    checkpoint_id VARCHAR(255),
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    cost_cents INTEGER DEFAULT 0,
    result_data JSONB DEFAULT '{}',
    error_message TEXT,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_agent_threads_festival ON agent_threads(festival_id);
CREATE INDEX idx_agent_threads_status ON agent_threads(status);

-- Agent stream events table
CREATE TABLE IF NOT EXISTS agent_stream_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id VARCHAR(255) REFERENCES agent_threads(thread_id) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL,
    event_data JSONB NOT NULL,
    node_name VARCHAR(100),
    step_number INTEGER,
    run_id VARCHAR(255),
    tool_name VARCHAR(100),
    tool_call_id VARCHAR(100),
    model_name VARCHAR(100),
    usage JSONB,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_stream_events_thread ON agent_stream_events(thread_id);
CREATE INDEX idx_stream_events_timestamp ON agent_stream_events(timestamp);
CREATE INDEX idx_stream_events_type ON agent_stream_events(event_type);

-- Add comment to agent_decisions
COMMENT ON TABLE agent_decisions IS 'DEPRECATED: Use agent_threads and agent_stream_events instead. Kept for historical data.';
