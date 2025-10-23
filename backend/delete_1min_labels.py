#!/usr/bin/env python3
"""Delete all labels for 1min timeframe from the database"""

import asyncio
import asyncpg
import os
from datetime import datetime

async def delete_1min_labels():
    # Get database URL from environment
    db_url = (
        os.getenv("DATABASE_URL")
        or os.getenv("TIMESCALE_DATABASE_URL")
        or os.getenv("POSTGRES_URL")
    )
    
    if not db_url:
        print("ERROR: No database URL found in environment variables")
        return
    
    try:
        # Connect to database
        conn = await asyncpg.connect(db_url)
        
        # First, count how many labels we're about to delete
        count_query = """
            SELECT COUNT(*) 
            FROM ml_labeled_data 
            WHERE symbol = 'NIFTY' 
            AND timeframe = '1min'
        """
        
        count = await conn.fetchval(count_query)
        print(f"Found {count} labels for NIFTY 1min timeframe")
        
        if count == 0:
            print("No labels to delete")
            await conn.close()
            return
        
        # Show a sample of what we're about to delete
        sample_query = """
            SELECT time, label, label_confidence 
            FROM ml_labeled_data 
            WHERE symbol = 'NIFTY' 
            AND timeframe = '1min'
            ORDER BY time DESC
            LIMIT 5
        """
        
        samples = await conn.fetch(sample_query)
        print("\nSample of labels to be deleted:")
        for row in samples:
            print(f"  {row['time']} - {row['label']} (confidence: {row['label_confidence']})")
        
        # Ask for confirmation
        print(f"\nAre you sure you want to delete ALL {count} labels for NIFTY 1min timeframe?")
        confirm = input("Type 'YES' to confirm: ")
        
        if confirm.upper() == 'YES':
            # Delete the labels
            delete_query = """
                DELETE FROM ml_labeled_data 
                WHERE symbol = 'NIFTY' 
                AND timeframe = '1min'
            """
            
            result = await conn.execute(delete_query)
            print(f"\nDeleted {count} labels successfully")
            print(f"Result: {result}")
        else:
            print("\nDeletion cancelled")
        
        await conn.close()
        
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(delete_1min_labels())