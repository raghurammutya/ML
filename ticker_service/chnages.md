from breeze_connect import BreezeConnect

try:
# Initialize SDK
	breeze = BreezeConnect(api_key="1339=936581V48@C&+96=J$284DC7414")
	breeze.generate_session(api_secret="769c5Y8QF48466^4C9u5408Bi04W790L",
                        session_token="52378763")
	print("connection succeeeded")
except:
	print("connection failed")

x=  breeze.get_historical_data_v2(
      interval="1day",
      from_date="2025-07-21T09:15:00.000Z",
      to_date="2025-07-25T15:30:59.000Z",
      stock_code="BNKNIFTY",
      exchange_code="NSE",
      product_type="cash"
  )
print(x)
breeze.get_option_chain_quotes(stock_code="NIFTY",
                    exchange_code="NFO",
                    product_type="options",
                    expiry_date="2025-01-25T06:00:00.000Z")


  🔧 Minor Issues (non-critical):
  - Database health check has async session issue (can be fixed later)
  - Redis MOVED errors are normal for Redis cluster mode
  - Option chain needs correct Breeze API parameters
  - WebSocket connection failed but REST API works fine


How can we handle the following:
a)For historical data, the old instrument_key records are not available. we need to create data, but then we need to know all expiries for each week/month. this is specific to NSE/BSE
b) While largely moneyness uses the spot as the underlying, we can also use futures as the underlying and compute moneyness based on the specified underlying.
c) we need to compute moneyness for both real time feeds and historical data. the concept is the same, only the process of picking up data is different
d) Exchange releases instruments in batches for an expiry. Till the instrument are released, the moneyness value changes. But what about historical data. right now, i have no way to figure out how historical strikes were released. we need to derive the data
e) we need to map moneyness based on situation at the datetime of the historical data or real time data
f) the Unifiedsymbols table has many column values repeating for each record. Example, all reliancerecords pretty much has same data in columns relating to the reliance company, however, there are unique information in each record like strike_price (for options), expiry_date, option_type and so on.. But the strike distance keeps changing as and when they release new strikes.
Also, the lot size changes at time as decided by the exchange.
I am confused on how to design such a system. we already have multiple services participating in mineyness like instrument_service, option_chain_service, historical_data_service, signal_service.. Is there any other database, which can handle these type of queries better? Let us discuss a bit more on these points. some of the points are also implemented. we need to check.

 ensure that you use the single timescaleb container defined in docker-compose (stocksblitz_unified schema) and create all tables there. similarly, use Redis cluster (see how you implemented usage of redis cluster in ticker_service). do not create any new containers.

can you check the symbol_refresh code in ticker_service -> breeze.py, to see how it downloads the files. the files have the session_token. in fact they have ExchangeCode, which means the code that the exchange calls it, irrespective of the broker assign stock_code or session_token. we should use exchangecode in our instrument_code token. Then each broker, example Kite or breeze when querying the api, it will query the instrument_service giving it the exchangecode and the broker name and the instrument_service should return the record.. the breeze.py will pick its column and use that to query. 

Currency Usage: ⚠️ NO EXPLICIT CURRENCY HANDLING

  The ticker service does NOT explicitly specify currency in the code:

  What I Found:

  ❌ No currency field in schemas/models
  ❌ No INR/USD conversion logic❌ No currency formatting functions
  ❌ No currency parameter in APIs

  Why This is OK:

  The service assumes implicit INR because:

  1. KiteConnect API only trades on Indian exchanges (NSE, BSE, MCX, CDS)
  2. All exchanges use INR - There's no multi-currency support needed
  3. Price fields are raw floats - Assumed to be in INR paise (e.g., 23456.75 = ₹234.56 for options)

  Potential Issue:

  If you ever:
  - Add international instruments
  - Store prices in different currencies
  - Display prices to users in different regions

  You'll need to add explicit currency handling.

  ---
  Summary:

  | Aspect   | Status      | Details
                                                  |
  |----------|-------------|--------------------------------------------------------------------------------------------
  ------------------------------------------------|
  | Timezone | ✅ CORRECT   | Consistently uses IST (Asia/Kolkata) for market hours, trading logic, and database
  storage. Uses UTC for internal timestamps.              |
  | Currency | ⚠️ IMPLICIT | No explicit currency field. Assumes INR everywhere. This works fine for Indian exchanges
  but would need changes for international support. |

  ---
  Recommendations:

  1. ✅ Timezone: No changes needed. Current implementation is correct.
  2. ⚠️ Currency: Consider adding explicit currency support if you plan to:
    - Support international instruments
    - Display prices in multiple currencies
    - Store historical data from non-INR markets

  For now, the implicit INR assumption is fine for NSE/BSE/MCX/CDS trading.

  Would you like me to add explicit currency fields to the schemas and APIs for future-proofing?

  The ONLY Issue: Market Timing Configuration ⏰

  The problem is NOT technical barriers - it's market timing configuration:

  Current config (app/config.py):
  market_open_time: dtime = Field(default=dtime(9, 15))   # 9:15 AM
  market_close_time: dtime = Field(default=dtime(15, 30)) # 3:30 PM

  Actual timings:
  - CDS: 9:00 AM - 5:00 PM (1.5 hours AFTER config close time)
  - MCX: 9:00 AM - 11:30 PM (8 hours AFTER config close time!)

  Impact:
  - Real-time data: Should work fine during 9:15 AM - 3:30 PM
  - Mock data generation: Kicks in after 3:30 PM, may override real ticks
  - Historical data: No impact (works anytime)
  - Order placement: No impact (works during exchange hours)

  When you likely had issues:
  - If you tried subscribing to MCX/CDS after 3:30 PM → mock mode was active
  - If you tried during 9:15 AM - 3:30 PM → should have worked fine

  ---
  Recommendation

  For immediate testing, try:
  1. Subscribe to MCX/CDS instruments before 3:30 PM
  2. Place test orders during exchange hours
  3. Fetch historical data (works anytime)

  For permanent fix, implement segment-specific timings in config to handle:
  - CDS: 9:00 AM - 5:00 PM
  - MCX: 9:00 AM - 11:30 PM
  - NFO/NSE/BSE: 9:15 AM - 3:30 PM

  This will prevent mock data from interfering with real MCX/CDS data during extended hours.