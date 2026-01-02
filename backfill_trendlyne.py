"""
Backfill historical option chain data from Trendlyne SmartOptions API.
This populates the OptionChainData table with today's historical data.
"""
import requests
import time
from datetime import datetime, timedelta, date
from database import get_oi_collection, get_stocks_collection, get_tick_data_collection

# Keep a cache to avoid repeated API calls
STOCK_ID_CACHE = {}

def get_stock_id_for_symbol(symbol):
    """Automatically lookup Trendlyne stock ID for a given symbol"""
    if symbol in STOCK_ID_CACHE:
        return STOCK_ID_CACHE[symbol]
    
    search_url = "https://smartoptions.trendlyne.com/phoenix/api/search-contract-stock/"
    params = {'query': symbol.lower()}
    
    try:
        print(f"Looking up stock ID for {symbol}...")
        response = requests.get(search_url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data and 'body' in data and 'data' in data['body'] and len(data['body']['data']) > 0:
            stock_id = data['body']['data'][0]['stock_id']
            if stock_id:
                STOCK_ID_CACHE[symbol] = stock_id
                print(f"[OK] Found stock ID {stock_id} for {symbol}")
                return stock_id
        
        print(f"[FAIL] Could not find stock ID for {symbol}")
        return None
        
    except Exception as e:
        print(f"[ERROR] Error looking up {symbol}: {e}")
        return None

def backfill_from_trendlyne(symbol, stock_id, expiry_date_str, timestamp_snapshot):
    """Fetch and save historical OI data from Trendlyne for a specific timestamp snapshot"""
    
    # live-oi-data gives the snapshot at maxTime
    url = f"https://smartoptions.trendlyne.com/phoenix/api/live-oi-data/"
    params = {
        'stockId': stock_id,
        'expDateList': expiry_date_str,
        'minTime': "09:15", # Always start from market open
        'maxTime': timestamp_snapshot # Snapshot time
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data['head']['status'] != '0':
            print(f"[ERROR] API error: {data['head'].get('statusDescription', 'Unknown error')}")
            return
        
        body = data['body']
        oi_data = body.get('oiData', {})
        input_data = body.get('inputData', {})
        
        oi_collection = get_oi_collection()
        stocks_collection = get_stocks_collection()

        # Ensure stock exists in MongoDB
        stock = stocks_collection.find_one({'symbol': symbol})
        if not stock:
            start_stock = {'symbol': symbol, 'trendlyne_stock_id': stock_id}
            stocks_collection.insert_one(start_stock)
            stock_db_id = start_stock['_id'] # Use ObjectId
        else:
             stock_db_id = stock['_id']


        # Use today's date or the date from API
        if 'tradingDate' in input_data:
            current_date_str = input_data['tradingDate'] # YYYY-MM-DD
        else:
            current_date_str = date.today().strftime("%Y-%m-%d")

        expiry_str = input_data.get('expDateList', [expiry_date_str])[0]
        
        # Calculate Aggregates from the per-strike data
        total_call_oi = 0
        total_put_oi = 0
        total_call_change = 0
        total_put_change = 0

        for strike_str, strike_data in oi_data.items():
            total_call_oi += int(strike_data.get('callOi', 0))
            total_put_oi += int(strike_data.get('putOi', 0))
            total_call_change += int(strike_data.get('callOiChange', 0))
            total_put_change += int(strike_data.get('putOiChange', 0))

        # Construct a document for MongoDB 'oi_data' collection
        doc = {
            'stock_id': stock_db_id, # Link to stock
            'symbol': symbol,        # Helper for easier querying
            'date': current_date_str,
            'timestamp': timestamp_snapshot, # HH:MM
            'expiry_date': expiry_str,
            'call_oi': total_call_oi,
            'put_oi': total_put_oi,
            'change_in_call_oi': total_call_change,
            'change_in_put_oi': total_put_change,
            'source': 'trendlyne_backfill'
        }

        # Upsert based on symbol, date, timestamp
        query = {
            'symbol': symbol,
            'date': current_date_str,
            'timestamp': timestamp_snapshot
        }
        
        oi_collection.update_one(query, {'$set': doc}, upsert=True)
        # print(f"[OK] Saved aggregate record for {symbol} at {timestamp_snapshot}")

    except Exception as e:
        print(f"[ERROR] Error fetching data for {symbol}: {e}")

def generate_time_intervals(start_time="09:15", end_time="15:30", interval_minutes=15):
    """Generate time strings in HH:MM format"""
    start = datetime.strptime(start_time, "%H:%M")
    end = datetime.strptime(end_time, "%H:%M")
    current = start
    times = []
    while current <= end:
        times.append(current.strftime("%H:%M"))
        current += timedelta(minutes=interval_minutes)
    return times

if __name__ == "__main__":
    print("=" * 60)
    print("Backfilling historical OI data from Trendlyne API -> MongoDB")
    print("=" * 60)

    # Use MongoDB stocks collection
    stocks_collection = get_stocks_collection()
    
    tick_collection = get_tick_data_collection()
    
    # Get distinct trading symbols from tick data if stocks collection is empty
    if stocks_collection.count_documents({}) == 0:
        print("Stocks collection empty. Fetching symbols from tick_data...")
        # distinct 'fullFeed.marketFF.marketOHLC.ohlc.0.symbol' is hard.
        # Check app.py: it uses `collection.distinct('instrumentKey')`
        # and then maps to symbol.
        keys = tick_collection.distinct('instrumentKey')
        # We need to map keys to symbols. 'NSE_FO|41923' -> 'BANKNIFTY'?
        # For now, let's hardcode the majors or infer.
        # Actually, let's just use the ones we know or prompt user?
        # Fallback to defaults
        symbols = ["NIFTY", "BANKNIFTY", "FINNIFTY"]
        print(f"Using default symbols: {symbols}")
    else:
        stocks = list(stocks_collection.find({}, {'symbol': 1}))
        symbols = [s['symbol'] for s in stocks if 'symbol' in s]
        if not symbols:
             symbols = ["NIFTY", "BANKNIFTY", "FINNIFTY"]
        print(f"Found {len(symbols)} symbols in database")
    
    successful = 0
    failed = 0
    
    # Generate time slots for the day
    now = datetime.now()
    market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    
    if now < market_open:
        # If running before market opens (e.g. midnight), 
        # assume we want the full previous day's data
        end_time_str = "15:30"
    elif now > market_close:
        end_time_str = "15:30"
    else:
        end_time_str = now.strftime("%H:%M")
        
    time_slots = generate_time_intervals(end_time=end_time_str)
    print(f"Backfilling for {len(time_slots)} time slots: {time_slots}")

    for symbol in symbols:  
        if ' ' in symbol or len(symbol) > 15:
            continue
        
        stock_id = get_stock_id_for_symbol(symbol)
        if not stock_id:
            failed += 1
            print(f"Skipping {symbol}: No stock ID found.")
            continue
        
        try:
            # Get Expiry
            expiry_url = f"https://smartoptions.trendlyne.com/phoenix/api/fno/get-expiry-dates/?mtype=options&stock_id={stock_id}"
            resp = requests.get(expiry_url, timeout=10)
            expiry_data = resp.json()
            if 'body' in expiry_data and 'expiryDates' in expiry_data['body']:
                expiry_list = expiry_data['body']['expiryDates']
                default_expiry = expiry_list[0] # Nearest expiry
            else:
                print(f"[WARN] Could not get expiry for {symbol}, using default")
                # Dynamic default: next thursday? 
                # For safety let's use a far date or handle error.
                # Let's just try current date logic or skip.
                continue 
            
            print(f"Backfilling {symbol} (Expiry: {default_expiry})...")
            
            # Iterate through time slots
            for ts in time_slots:
                backfill_from_trendlyne(symbol, stock_id, default_expiry, ts)
            
            successful += 1
            print(f"[DONE] {symbol} complete.")
            
        except Exception as e:
            print(f"[ERROR] Failed processing {symbol}: {e}")
            failed += 1
        
        time.sleep(0.5) 
    
    print("\n" + "=" * 60)
    print(f"[DONE] Backfill complete! {successful} successful, {failed} failed")
    print("=" * 60)
