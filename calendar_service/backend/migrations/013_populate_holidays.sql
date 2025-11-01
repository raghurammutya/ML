-- Migration 013: Populate Market Holidays
-- Date: 2025-11-01
-- Purpose: Insert known NSE/BSE/MCX holidays for 2024-2026

-- NSE Holidays 2024
INSERT INTO calendar_events (calendar_type_id, event_date, event_name, event_type, is_trading_day, category, source, verified) VALUES
((SELECT id FROM calendar_types WHERE code = 'NSE'), '2024-01-26', 'Republic Day', 'holiday', false, 'market_holiday', 'Fallback (hardcoded)', false),
((SELECT id FROM calendar_types WHERE code = 'NSE'), '2024-03-08', 'Maha Shivaratri', 'holiday', false, 'market_holiday', 'Fallback (hardcoded)', false),
((SELECT id FROM calendar_types WHERE code = 'NSE'), '2024-03-25', 'Holi', 'holiday', false, 'market_holiday', 'Fallback (hardcoded)', false),
((SELECT id FROM calendar_types WHERE code = 'NSE'), '2024-03-29', 'Good Friday', 'holiday', false, 'market_holiday', 'Fallback (hardcoded)', false),
((SELECT id FROM calendar_types WHERE code = 'NSE'), '2024-04-11', 'Id-Ul-Fitr', 'holiday', false, 'market_holiday', 'Fallback (hardcoded)', false),
((SELECT id FROM calendar_types WHERE code = 'NSE'), '2024-04-17', 'Shri Ram Navmi', 'holiday', false, 'market_holiday', 'Fallback (hardcoded)', false),
((SELECT id FROM calendar_types WHERE code = 'NSE'), '2024-04-21', 'Mahavir Jayanti', 'holiday', false, 'market_holiday', 'Fallback (hardcoded)', false),
((SELECT id FROM calendar_types WHERE code = 'NSE'), '2024-05-01', 'Maharashtra Day', 'holiday', false, 'market_holiday', 'Fallback (hardcoded)', false),
((SELECT id FROM calendar_types WHERE code = 'NSE'), '2024-05-23', 'Buddha Pournima', 'holiday', false, 'market_holiday', 'Fallback (hardcoded)', false),
((SELECT id FROM calendar_types WHERE code = 'NSE'), '2024-06-17', 'Id-Ul-Zuha (Bakri Id)', 'holiday', false, 'market_holiday', 'Fallback (hardcoded)', false),
((SELECT id FROM calendar_types WHERE code = 'NSE'), '2024-07-17', 'Moharram', 'holiday', false, 'market_holiday', 'Fallback (hardcoded)', false),
((SELECT id FROM calendar_types WHERE code = 'NSE'), '2024-08-15', 'Independence Day', 'holiday', false, 'market_holiday', 'Fallback (hardcoded)', false),
((SELECT id FROM calendar_types WHERE code = 'NSE'), '2024-08-26', 'Ganesh Chaturthi', 'holiday', false, 'market_holiday', 'Fallback (hardcoded)', false),
((SELECT id FROM calendar_types WHERE code = 'NSE'), '2024-10-02', 'Mahatma Gandhi Jayanti', 'holiday', false, 'market_holiday', 'Fallback (hardcoded)', false),
((SELECT id FROM calendar_types WHERE code = 'NSE'), '2024-10-12', 'Dussehra', 'holiday', false, 'market_holiday', 'Fallback (hardcoded)', false),
((SELECT id FROM calendar_types WHERE code = 'NSE'), '2024-11-01', 'Diwali Laxmi Pujan', 'holiday', false, 'market_holiday', 'Fallback (hardcoded)', false),
((SELECT id FROM calendar_types WHERE code = 'NSE'), '2024-11-15', 'Guru Nanak Jayanti', 'holiday', false, 'market_holiday', 'Fallback (hardcoded)', false),
((SELECT id FROM calendar_types WHERE code = 'NSE'), '2024-12-25', 'Christmas', 'holiday', false, 'market_holiday', 'Fallback (hardcoded)', false)
ON CONFLICT (calendar_type_id, event_date, event_name) DO NOTHING;

-- NSE Holidays 2025
INSERT INTO calendar_events (calendar_type_id, event_date, event_name, event_type, is_trading_day, category, source, verified) VALUES
((SELECT id FROM calendar_types WHERE code = 'NSE'), '2025-01-26', 'Republic Day', 'holiday', false, 'market_holiday', 'Fallback (hardcoded)', false),
((SELECT id FROM calendar_types WHERE code = 'NSE'), '2025-03-14', 'Holi', 'holiday', false, 'market_holiday', 'Fallback (hardcoded)', false),
((SELECT id FROM calendar_types WHERE code = 'NSE'), '2025-03-31', 'Id-Ul-Fitr', 'holiday', false, 'market_holiday', 'Fallback (hardcoded)', false),
((SELECT id FROM calendar_types WHERE code = 'NSE'), '2025-04-10', 'Mahavir Jayanti', 'holiday', false, 'market_holiday', 'Fallback (hardcoded)', false),
((SELECT id FROM calendar_types WHERE code = 'NSE'), '2025-04-14', 'Dr. Baba Saheb Ambedkar Jayanti', 'holiday', false, 'market_holiday', 'Fallback (hardcoded)', false),
((SELECT id FROM calendar_types WHERE code = 'NSE'), '2025-04-18', 'Good Friday', 'holiday', false, 'market_holiday', 'Fallback (hardcoded)', false),
((SELECT id FROM calendar_types WHERE code = 'NSE'), '2025-05-01', 'Maharashtra Day', 'holiday', false, 'market_holiday', 'Fallback (hardcoded)', false),
((SELECT id FROM calendar_types WHERE code = 'NSE'), '2025-08-15', 'Independence Day', 'holiday', false, 'market_holiday', 'Fallback (hardcoded)', false),
((SELECT id FROM calendar_types WHERE code = 'NSE'), '2025-08-27', 'Ganesh Chaturthi', 'holiday', false, 'market_holiday', 'Fallback (hardcoded)', false),
((SELECT id FROM calendar_types WHERE code = 'NSE'), '2025-10-02', 'Mahatma Gandhi Jayanti', 'holiday', false, 'market_holiday', 'Fallback (hardcoded)', false),
((SELECT id FROM calendar_types WHERE code = 'NSE'), '2025-10-21', 'Dussehra', 'holiday', false, 'market_holiday', 'Fallback (hardcoded)', false),
((SELECT id FROM calendar_types WHERE code = 'NSE'), '2025-11-01', 'Diwali Laxmi Pujan', 'holiday', false, 'market_holiday', 'Fallback (hardcoded)', false),
((SELECT id FROM calendar_types WHERE code = 'NSE'), '2025-11-04', 'Diwali Balipratipada', 'holiday', false, 'market_holiday', 'Fallback (hardcoded)', false),
((SELECT id FROM calendar_types WHERE code = 'NSE'), '2025-11-05', 'Guru Nanak Jayanti', 'holiday', false, 'market_holiday', 'Fallback (hardcoded)', false),
((SELECT id FROM calendar_types WHERE code = 'NSE'), '2025-12-25', 'Christmas', 'holiday', false, 'market_holiday', 'Fallback (hardcoded)', false)
ON CONFLICT (calendar_type_id, event_date, event_name) DO NOTHING;

-- NSE Holidays 2026
INSERT INTO calendar_events (calendar_type_id, event_date, event_name, event_type, is_trading_day, category, source, verified) VALUES
((SELECT id FROM calendar_types WHERE code = 'NSE'), '2026-01-26', 'Republic Day', 'holiday', false, 'market_holiday', 'Fallback (hardcoded)', false),
((SELECT id FROM calendar_types WHERE code = 'NSE'), '2026-03-03', 'Holi', 'holiday', false, 'market_holiday', 'Fallback (hardcoded)', false),
((SELECT id FROM calendar_types WHERE code = 'NSE'), '2026-03-21', 'Id-Ul-Fitr', 'holiday', false, 'market_holiday', 'Fallback (hardcoded)', false),
((SELECT id FROM calendar_types WHERE code = 'NSE'), '2026-03-30', 'Shri Ram Navmi', 'holiday', false, 'market_holiday', 'Fallback (hardcoded)', false),
((SELECT id FROM calendar_types WHERE code = 'NSE'), '2026-04-02', 'Mahavir Jayanti', 'holiday', false, 'market_holiday', 'Fallback (hardcoded)', false),
((SELECT id FROM calendar_types WHERE code = 'NSE'), '2026-04-03', 'Good Friday', 'holiday', false, 'market_holiday', 'Fallback (hardcoded)', false),
((SELECT id FROM calendar_types WHERE code = 'NSE'), '2026-04-06', 'Dr. Baba Saheb Ambedkar Jayanti', 'holiday', false, 'market_holiday', 'Fallback (hardcoded)', false),
((SELECT id FROM calendar_types WHERE code = 'NSE'), '2026-05-01', 'Maharashtra Day', 'holiday', false, 'market_holiday', 'Fallback (hardcoded)', false),
((SELECT id FROM calendar_types WHERE code = 'NSE'), '2026-08-15', 'Independence Day', 'holiday', false, 'market_holiday', 'Fallback (hardcoded)', false),
((SELECT id FROM calendar_types WHERE code = 'NSE'), '2026-09-16', 'Ganesh Chaturthi', 'holiday', false, 'market_holiday', 'Fallback (hardcoded)', false),
((SELECT id FROM calendar_types WHERE code = 'NSE'), '2026-10-02', 'Mahatma Gandhi Jayanti', 'holiday', false, 'market_holiday', 'Fallback (hardcoded)', false),
((SELECT id FROM calendar_types WHERE code = 'NSE'), '2026-10-20', 'Dussehra', 'holiday', false, 'market_holiday', 'Fallback (hardcoded)', false),
((SELECT id FROM calendar_types WHERE code = 'NSE'), '2026-11-10', 'Diwali Laxmi Pujan', 'holiday', false, 'market_holiday', 'Fallback (hardcoded)', false),
((SELECT id FROM calendar_types WHERE code = 'NSE'), '2026-12-25', 'Christmas', 'holiday', false, 'market_holiday', 'Fallback (hardcoded)', false)
ON CONFLICT (calendar_type_id, event_date, event_name) DO NOTHING;

-- BSE Holidays (mirror NSE)
INSERT INTO calendar_events (calendar_type_id, event_date, event_name, event_type, is_trading_day, category, source, verified)
SELECT
    (SELECT id FROM calendar_types WHERE code = 'BSE'),
    event_date,
    event_name,
    event_type,
    is_trading_day,
    category,
    'BSE (mirrored from NSE)',
    false
FROM calendar_events
WHERE calendar_type_id = (SELECT id FROM calendar_types WHERE code = 'NSE')
AND category = 'market_holiday'
ON CONFLICT (calendar_type_id, event_date, event_name) DO NOTHING;

-- MCX Holidays (major holidays only)
INSERT INTO calendar_events (calendar_type_id, event_date, event_name, event_type, is_trading_day, category, source, verified) VALUES
-- 2024
((SELECT id FROM calendar_types WHERE code = 'MCX'), '2024-01-26', 'Republic Day', 'holiday', false, 'market_holiday', 'MCX (fallback)', false),
((SELECT id FROM calendar_types WHERE code = 'MCX'), '2024-03-25', 'Holi', 'holiday', false, 'market_holiday', 'MCX (fallback)', false),
((SELECT id FROM calendar_types WHERE code = 'MCX'), '2024-03-29', 'Good Friday', 'holiday', false, 'market_holiday', 'MCX (fallback)', false),
((SELECT id FROM calendar_types WHERE code = 'MCX'), '2024-08-15', 'Independence Day', 'holiday', false, 'market_holiday', 'MCX (fallback)', false),
((SELECT id FROM calendar_types WHERE code = 'MCX'), '2024-10-02', 'Mahatma Gandhi Jayanti', 'holiday', false, 'market_holiday', 'MCX (fallback)', false),
((SELECT id FROM calendar_types WHERE code = 'MCX'), '2024-11-01', 'Diwali', 'holiday', false, 'market_holiday', 'MCX (fallback)', false),
((SELECT id FROM calendar_types WHERE code = 'MCX'), '2024-12-25', 'Christmas', 'holiday', false, 'market_holiday', 'MCX (fallback)', false),
-- 2025
((SELECT id FROM calendar_types WHERE code = 'MCX'), '2025-01-26', 'Republic Day', 'holiday', false, 'market_holiday', 'MCX (fallback)', false),
((SELECT id FROM calendar_types WHERE code = 'MCX'), '2025-03-14', 'Holi', 'holiday', false, 'market_holiday', 'MCX (fallback)', false),
((SELECT id FROM calendar_types WHERE code = 'MCX'), '2025-04-18', 'Good Friday', 'holiday', false, 'market_holiday', 'MCX (fallback)', false),
((SELECT id FROM calendar_types WHERE code = 'MCX'), '2025-08-15', 'Independence Day', 'holiday', false, 'market_holiday', 'MCX (fallback)', false),
((SELECT id FROM calendar_types WHERE code = 'MCX'), '2025-10-02', 'Mahatma Gandhi Jayanti', 'holiday', false, 'market_holiday', 'MCX (fallback)', false),
((SELECT id FROM calendar_types WHERE code = 'MCX'), '2025-11-01', 'Diwali', 'holiday', false, 'market_holiday', 'MCX (fallback)', false),
((SELECT id FROM calendar_types WHERE code = 'MCX'), '2025-12-25', 'Christmas', 'holiday', false, 'market_holiday', 'MCX (fallback)', false),
-- 2026
((SELECT id FROM calendar_types WHERE code = 'MCX'), '2026-01-26', 'Republic Day', 'holiday', false, 'market_holiday', 'MCX (fallback)', false),
((SELECT id FROM calendar_types WHERE code = 'MCX'), '2026-03-03', 'Holi', 'holiday', false, 'market_holiday', 'MCX (fallback)', false),
((SELECT id FROM calendar_types WHERE code = 'MCX'), '2026-04-03', 'Good Friday', 'holiday', false, 'market_holiday', 'MCX (fallback)', false),
((SELECT id FROM calendar_types WHERE code = 'MCX'), '2026-08-15', 'Independence Day', 'holiday', false, 'market_holiday', 'MCX (fallback)', false),
((SELECT id FROM calendar_types WHERE code = 'MCX'), '2026-10-02', 'Mahatma Gandhi Jayanti', 'holiday', false, 'market_holiday', 'MCX (fallback)', false),
((SELECT id FROM calendar_types WHERE code = 'MCX'), '2026-11-10', 'Diwali', 'holiday', false, 'market_holiday', 'MCX (fallback)', false),
((SELECT id FROM calendar_types WHERE code = 'MCX'), '2026-12-25', 'Christmas', 'holiday', false, 'market_holiday', 'MCX (fallback)', false)
ON CONFLICT (calendar_type_id, event_date, event_name) DO NOTHING;

-- Currency markets (mirror NSE)
INSERT INTO calendar_events (calendar_type_id, event_date, event_name, event_type, is_trading_day, category, source, verified)
SELECT
    (SELECT id FROM calendar_types WHERE code = 'NSE_CURRENCY'),
    event_date,
    event_name,
    event_type,
    is_trading_day,
    category,
    'Currency (mirrored from NSE)',
    false
FROM calendar_events
WHERE calendar_type_id = (SELECT id FROM calendar_types WHERE code = 'NSE')
AND category = 'market_holiday'
ON CONFLICT (calendar_type_id, event_date, event_name) DO NOTHING;

-- Show summary
SELECT
    ct.code as calendar,
    COUNT(*) as holiday_count
FROM calendar_events ce
JOIN calendar_types ct ON ce.calendar_type_id = ct.id
WHERE ce.category = 'market_holiday'
GROUP BY ct.code
ORDER BY ct.code;
