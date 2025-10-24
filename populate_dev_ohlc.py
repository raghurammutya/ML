#!/usr/bin/env python3
"""
Script to safely copy OHLC data from production to development database
This script only READS from production and WRITES to development
"""

import psycopg2
import sys
from datetime import datetime, timedelta

def main():
    # Database connections
    prod_conn = psycopg2.connect(
        host="localhost",
        port=5432,
        database="stocksblitz_unified",
        user="stocksblitz", 
        password="stocksblitz123"
    )
    
    dev_conn = psycopg2.connect(
        host="localhost",
        port=5432,
        database="stocksblitz_unified_dev",
        user="stocksblitz",
        password="stocksblitz123"
    )
    
    prod_cursor = prod_conn.cursor()
    dev_cursor = dev_conn.cursor()
    
    # Get recent data from production (last month)
    cutoff_date = datetime.now() - timedelta(days=30)
    
    print(f"Copying OHLC data from production to development...")
    print(f"Fetching data from {cutoff_date.strftime('%Y-%m-%d')} onwards...")
    
    # Read from production (READ-ONLY)
    prod_cursor.execute("""
        SELECT time, open, high, low, close, volume, symbol 
        FROM nifty50_ohlc 
        WHERE time >= %s 
        ORDER BY time 
        LIMIT 10000
    """, (cutoff_date,))
    
    rows = prod_cursor.fetchall()
    print(f"Found {len(rows)} records to copy")
    
    # Insert into development in smaller batches to avoid TimescaleDB issues
    batch_size = 100
    total_inserted = 0
    
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i+batch_size]
        
        try:
            # Insert batch into development database
            for row in batch:
                dev_cursor.execute("""
                    INSERT INTO nifty50_ohlc (time, open, high, low, close, volume, symbol)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (time, symbol) DO NOTHING
                """, row)
            
            dev_conn.commit()
            total_inserted += len(batch)
            print(f"Inserted batch {i//batch_size + 1}, total: {total_inserted}")
            
        except Exception as e:
            print(f"Error inserting batch {i//batch_size + 1}: {e}")
            dev_conn.rollback()
            continue
    
    print(f"Successfully copied {total_inserted} records to development database")
    
    # Verify the data
    dev_cursor.execute("SELECT COUNT(*) FROM nifty50_ohlc")
    count = dev_cursor.fetchone()[0]
    print(f"Development database now has {count} OHLC records")
    
    # Close connections
    prod_cursor.close()
    dev_cursor.close()
    prod_conn.close()
    dev_conn.close()

if __name__ == "__main__":
    main()