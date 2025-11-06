#!/usr/bin/env python3
"""
Quick test script to verify Greeks are being published to Redis
"""
import redis
import json
import time

# Connect to Redis
r = redis.Redis(host='localhost', port=6379, db=0, password='redis123', decode_responses=True)

print("Subscribing to ticker:nifty:options channel...")
print("Waiting for option tick data with Greeks...\n")

pubsub = r.pubsub()
pubsub.subscribe('ticker:nifty:options')

count = 0
max_samples = 5

for message in pubsub.listen():
    if message['type'] == 'message':
        try:
            data = json.loads(message['data'])

            # Check if this is option data (not underlying)
            if data.get('type') in ('CE', 'PE'):
                count += 1
                print(f"\n{'='*80}")
                print(f"Sample {count}: {data.get('tradingsymbol', 'UNKNOWN')}")
                print(f"{'='*80}")
                print(f"Type:         {data.get('type')}")
                print(f"Strike:       {data.get('strike')}")
                print(f"Expiry:       {data.get('expiry')}")
                print(f"Last Price:   {data.get('price')}")
                print(f"Volume:       {data.get('volume')}")
                print(f"OI:           {data.get('oi')}")
                print(f"\nGREEKS:")
                print(f"  IV:         {data.get('iv', 0):.4f}")
                print(f"  Delta:      {data.get('delta', 0):.4f}")
                print(f"  Gamma:      {data.get('gamma', 0):.4f}")
                print(f"  Theta:      {data.get('theta', 0):.4f}")
                print(f"  Vega:       {data.get('vega', 0):.4f}")

                # Verify Greeks are non-zero
                if data.get('iv', 0) > 0 or data.get('delta', 0) != 0:
                    print(f"\n✅ Greeks calculation is WORKING!")
                else:
                    print(f"\n⚠️  Greeks are zero - may need underlying price first")

                if count >= max_samples:
                    print(f"\n{'='*80}")
                    print(f"Test complete! Collected {count} samples.")
                    print(f"{'='*80}\n")
                    break
        except json.JSONDecodeError:
            pass
        except Exception as e:
            print(f"Error parsing message: {e}")

pubsub.unsubscribe()
pubsub.close()
r.close()
