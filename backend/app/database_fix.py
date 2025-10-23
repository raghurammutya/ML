"""
Fix for handling NULL OHLC values in get_history method
This shows the corrected logic to handle NULL values in the 5-minute data
"""

# The issue is in these lines where NULL values cause float() to fail:
# o.append(float(r["open"]))
# h.append(float(r["high"]))
# l.append(float(r["low"]))
# c.append(float(r["close"]))

# The fix should be:
"""
        for r in rows:
            # Skip rows with NULL OHLC values
            if any(r[col] is None for col in ["open", "high", "low", "close"]):
                continue
                
            ts = int(r["ts"].timestamp())
            t.append(ts)
            o.append(float(r["open"]))
            h.append(float(r["high"]))
            l.append(float(r["low"]))
            c.append(float(r["close"]))
            v.append(int(r["volume"]) if r["volume"] is not None else 0)
"""

# Or handle NULL values with defaults:
"""
        for r in rows:
            ts = int(r["ts"].timestamp())
            
            # Skip if all OHLC values are NULL
            if all(r[col] is None for col in ["open", "high", "low", "close"]):
                continue
            
            # Use the close price as default for missing values
            close_val = r["close"]
            if close_val is None:
                continue  # Can't process without at least close price
            
            t.append(ts)
            o.append(float(r["open"]) if r["open"] is not None else float(close_val))
            h.append(float(r["high"]) if r["high"] is not None else float(close_val))
            l.append(float(r["low"]) if r["low"] is not None else float(close_val))
            c.append(float(close_val))
            v.append(int(r["volume"]) if r["volume"] is not None else 0)
"""