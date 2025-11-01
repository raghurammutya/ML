-- Migration 012: Create Calendar Service
-- Date: 2025-11-01
-- Purpose: General calendar service supporting market holidays, events, and future user calendars

-- =====================================================
-- 1. CALENDAR TYPES
-- =====================================================

CREATE TABLE calendar_types (
    id SERIAL PRIMARY KEY,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    category TEXT NOT NULL, -- 'market', 'system', 'user'
    is_active BOOLEAN DEFAULT true,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Pre-populate calendar types
INSERT INTO calendar_types (code, name, description, category) VALUES
('NSE', 'National Stock Exchange', 'NSE India equity and derivatives market', 'market'),
('BSE', 'Bombay Stock Exchange', 'BSE India equity market', 'market'),
('MCX', 'Multi Commodity Exchange', 'MCX commodity derivatives market', 'market'),
('NCDEX', 'National Commodity & Derivatives Exchange', 'NCDEX agricultural commodities', 'market'),
('NSE_CURRENCY', 'NSE Currency Derivatives', 'NSE currency futures and options', 'market'),
('BSE_CURRENCY', 'BSE Currency Derivatives', 'BSE currency derivatives', 'market'),
('SYSTEM', 'System Events', 'System-wide scheduled events', 'system'),
('USER_DEFAULT', 'User Calendar', 'User-specific events (requires user_service)', 'user');

-- =====================================================
-- 2. TRADING SESSIONS (Template for regular days)
-- =====================================================

CREATE TABLE trading_sessions (
    id SERIAL PRIMARY KEY,
    calendar_type_id INTEGER REFERENCES calendar_types(id),
    session_type TEXT NOT NULL, -- 'regular', 'pre_market', 'post_market', 'muhurat', 'special'

    -- Trading hours
    trading_start TIME NOT NULL,
    trading_end TIME NOT NULL,

    -- Optional pre/post market
    pre_market_start TIME,
    pre_market_end TIME,
    post_market_start TIME,
    post_market_end TIME,

    -- Days this applies to (for regular sessions)
    applies_to_days INTEGER[], -- 1=Mon, 2=Tue, ..., 7=Sun (NULL = all days)

    -- Metadata
    description TEXT,
    is_active BOOLEAN DEFAULT true,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(calendar_type_id, session_type)
);

-- Pre-populate regular trading sessions
INSERT INTO trading_sessions
(calendar_type_id, session_type, trading_start, trading_end, pre_market_start, pre_market_end, post_market_start, post_market_end, applies_to_days, description)
VALUES
-- NSE Equity & F&O
((SELECT id FROM calendar_types WHERE code = 'NSE'), 'regular', '09:15:00', '15:30:00', '09:00:00', '09:08:00', '15:40:00', '16:00:00', ARRAY[1,2,3,4,5], 'NSE regular trading session'),

-- BSE Equity
((SELECT id FROM calendar_types WHERE code = 'BSE'), 'regular', '09:15:00', '15:30:00', '09:00:00', '09:08:00', '15:40:00', '16:00:00', ARRAY[1,2,3,4,5], 'BSE regular trading session'),

-- MCX Commodities
((SELECT id FROM calendar_types WHERE code = 'MCX'), 'regular', '09:00:00', '23:30:00', NULL, NULL, '23:30:00', '23:55:00', ARRAY[1,2,3,4,5], 'MCX regular trading session'),

-- NSE Currency
((SELECT id FROM calendar_types WHERE code = 'NSE_CURRENCY'), 'regular', '09:00:00', '17:00:00', NULL, NULL, NULL, NULL, ARRAY[1,2,3,4,5], 'NSE currency trading session');

-- =====================================================
-- 3. CALENDAR EVENTS (Holidays, Special Days)
-- =====================================================

CREATE TABLE calendar_events (
    id SERIAL PRIMARY KEY,
    calendar_type_id INTEGER REFERENCES calendar_types(id),

    -- Event details
    event_date DATE NOT NULL,
    event_name TEXT NOT NULL,
    event_type TEXT NOT NULL, -- 'holiday', 'special_hours', 'recurring', 'one_time'

    -- Status
    is_trading_day BOOLEAN DEFAULT false,
    is_settlement_day BOOLEAN DEFAULT false,

    -- Special hours (if is_trading_day = true but different hours)
    special_start TIME,
    special_end TIME,

    -- Recurrence (for recurring events)
    recurrence_rule TEXT, -- RRULE format or simple: 'WEEKLY:SAT,SUN'
    parent_event_id INTEGER REFERENCES calendar_events(id), -- For recurring instances

    -- User association (for future user calendars)
    user_id INTEGER, -- Will reference user_service.users.id when available

    -- Categorization
    category TEXT, -- 'national_holiday', 'market_holiday', 'weekend', 'special', 'user_event'
    tags TEXT[], -- For flexible categorization

    -- Additional data
    description TEXT,
    notes TEXT,
    metadata JSONB DEFAULT '{}',

    -- Source tracking
    source TEXT, -- 'NSE', 'BSE', 'manual', 'user', 'system'
    source_url TEXT,
    verified BOOLEAN DEFAULT false,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Constraints
    UNIQUE(calendar_type_id, event_date, event_name)
);

-- Indexes for performance
CREATE INDEX idx_calendar_events_date ON calendar_events(event_date);
CREATE INDEX idx_calendar_events_type ON calendar_events(calendar_type_id, event_date);
CREATE INDEX idx_calendar_events_trading ON calendar_events(is_trading_day, event_date);
CREATE INDEX idx_calendar_events_user ON calendar_events(user_id, event_date) WHERE user_id IS NOT NULL;
CREATE INDEX idx_calendar_events_category ON calendar_events(category);

-- =====================================================
-- 4. MARKET STATUS CACHE (Computed daily)
-- =====================================================

CREATE TABLE market_status_cache (
    id SERIAL PRIMARY KEY,
    calendar_type_id INTEGER REFERENCES calendar_types(id),
    status_date DATE NOT NULL,

    -- Computed status
    is_trading_day BOOLEAN NOT NULL,
    is_holiday BOOLEAN NOT NULL,
    is_weekend BOOLEAN NOT NULL,
    is_special_session BOOLEAN NOT NULL,

    -- Session times (from trading_sessions or special hours)
    session_start TIME,
    session_end TIME,
    pre_market_start TIME,
    pre_market_end TIME,
    post_market_start TIME,
    post_market_end TIME,

    -- Reference to event (if any)
    event_id INTEGER REFERENCES calendar_events(id),
    event_name TEXT,

    -- Metadata
    notes TEXT,
    computed_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(calendar_type_id, status_date)
);

CREATE INDEX idx_market_status_date ON market_status_cache(status_date);
CREATE INDEX idx_market_status_type_date ON market_status_cache(calendar_type_id, status_date);

-- =====================================================
-- 5. HELPER FUNCTIONS
-- =====================================================

-- Function to check if a date is a weekend
CREATE OR REPLACE FUNCTION is_weekend(check_date DATE)
RETURNS BOOLEAN AS $$
BEGIN
    RETURN EXTRACT(DOW FROM check_date) IN (0, 6); -- Sunday = 0, Saturday = 6
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Function to get market status for a specific date and calendar
CREATE OR REPLACE FUNCTION get_market_status(
    p_calendar_code TEXT,
    p_date DATE DEFAULT CURRENT_DATE
)
RETURNS TABLE (
    is_trading_day BOOLEAN,
    is_holiday BOOLEAN,
    is_weekend BOOLEAN,
    session_type TEXT,
    trading_start TIME,
    trading_end TIME,
    event_name TEXT
) AS $$
DECLARE
    v_calendar_id INTEGER;
    v_day_of_week INTEGER;
BEGIN
    -- Get calendar type ID
    SELECT id INTO v_calendar_id
    FROM calendar_types
    WHERE code = p_calendar_code AND is_active = true;

    IF v_calendar_id IS NULL THEN
        RAISE EXCEPTION 'Calendar type % not found', p_calendar_code;
    END IF;

    -- Check cache first
    RETURN QUERY
    SELECT
        msc.is_trading_day,
        msc.is_holiday,
        msc.is_weekend,
        CASE
            WHEN msc.is_special_session THEN 'special'
            WHEN msc.is_holiday THEN 'closed'
            WHEN msc.is_weekend THEN 'closed'
            ELSE 'regular'
        END::TEXT,
        msc.session_start,
        msc.session_end,
        msc.event_name
    FROM market_status_cache msc
    WHERE msc.calendar_type_id = v_calendar_id
    AND msc.status_date = p_date;

    -- If not in cache, return null (will be computed by application)
    IF NOT FOUND THEN
        RETURN QUERY SELECT NULL::BOOLEAN, NULL::BOOLEAN, NULL::BOOLEAN, NULL::TEXT, NULL::TIME, NULL::TIME, NULL::TEXT;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Function to populate weekends for a year
CREATE OR REPLACE FUNCTION populate_weekends(
    p_calendar_code TEXT,
    p_year INTEGER
)
RETURNS INTEGER AS $$
DECLARE
    v_calendar_id INTEGER;
    v_start_date DATE;
    v_end_date DATE;
    v_current_date DATE;
    v_count INTEGER := 0;
BEGIN
    -- Get calendar type ID
    SELECT id INTO v_calendar_id
    FROM calendar_types
    WHERE code = p_calendar_code;

    v_start_date := make_date(p_year, 1, 1);
    v_end_date := make_date(p_year, 12, 31);
    v_current_date := v_start_date;

    WHILE v_current_date <= v_end_date LOOP
        IF is_weekend(v_current_date) THEN
            INSERT INTO calendar_events (
                calendar_type_id,
                event_date,
                event_name,
                event_type,
                is_trading_day,
                category,
                source
            ) VALUES (
                v_calendar_id,
                v_current_date,
                to_char(v_current_date, 'Day'),
                'recurring',
                false,
                'weekend',
                'system'
            )
            ON CONFLICT (calendar_type_id, event_date, event_name) DO NOTHING;

            v_count := v_count + 1;
        END IF;

        v_current_date := v_current_date + 1;
    END LOOP;

    RETURN v_count;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- 6. INITIAL DATA - Populate weekends for 2024-2026
-- =====================================================

DO $$
DECLARE
    v_calendar_code TEXT;
    v_year INTEGER;
    v_count INTEGER;
BEGIN
    -- Populate weekends for all market calendars
    FOR v_calendar_code IN
        SELECT code FROM calendar_types WHERE category = 'market'
    LOOP
        FOR v_year IN 2024..2026 LOOP
            SELECT populate_weekends(v_calendar_code, v_year) INTO v_count;
            RAISE NOTICE 'Populated % weekends for % in year %', v_count, v_calendar_code, v_year;
        END LOOP;
    END LOOP;
END $$;

-- =====================================================
-- 7. COMMENTS
-- =====================================================

COMMENT ON TABLE calendar_types IS 'Defines different calendar types (NSE, BSE, MCX, user calendars, etc.)';
COMMENT ON TABLE trading_sessions IS 'Template for regular trading sessions by calendar type';
COMMENT ON TABLE calendar_events IS 'Specific events: holidays, special days, user events, recurring events';
COMMENT ON TABLE market_status_cache IS 'Pre-computed market status for fast lookups';

COMMENT ON FUNCTION get_market_status IS 'Get market status for a specific calendar and date';
COMMENT ON FUNCTION populate_weekends IS 'Populate weekend events for a calendar and year';
COMMENT ON FUNCTION is_weekend IS 'Check if a date falls on Saturday or Sunday';
