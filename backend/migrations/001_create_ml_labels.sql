-- Migration: 001_create_ml_labels.sql

-- Create ml_labels table (metadata-only)
CREATE TABLE IF NOT EXISTS ml_labels (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    label_type VARCHAR(50) NOT NULL,
    metadata JSONB NOT NULL,
    tags TEXT[] DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Required metadata fields validation
ALTER TABLE ml_labels ADD CONSTRAINT metadata_required_fields CHECK (
    metadata ? 'timeframe' AND 
    metadata ? 'nearest_candle_timestamp_utc' AND 
    metadata ? 'sample_offset_seconds'
);

-- Create ml_label_samples table for ML export references
CREATE TABLE IF NOT EXISTS ml_label_samples (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    label_id UUID NOT NULL REFERENCES ml_labels(id) ON DELETE CASCADE,
    sample_uri TEXT NOT NULL,
    sample_type VARCHAR(50) NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_ml_labels_user_symbol ON ml_labels(user_id, symbol);
CREATE INDEX idx_ml_labels_timestamp ON ml_labels((metadata->>'nearest_candle_timestamp_utc'));
CREATE INDEX idx_ml_labels_timeframe ON ml_labels((metadata->>'timeframe'));
CREATE INDEX idx_ml_labels_tags ON ml_labels USING GIN(tags);
CREATE INDEX idx_ml_labels_metadata ON ml_labels USING GIN(metadata);

-- Trigger to update updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_ml_labels_updated_at BEFORE UPDATE ON ml_labels
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();