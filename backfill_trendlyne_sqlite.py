"""
Backfill historical option chain data from Trendlyne SmartOptions API.
This populates a local SQLite database with today's historical data.
"""
import requests
import time
from datetime import datetime, timedelta, date
import sqlite3

# Keep a cache to avoid repeated API calls
STOCK_ID_CACHE = {}

def init_db(db_name='trendlyne_data.db'):
    """Initializes the SQLite database and creates the table if it doesn't exist."""
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS oi_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            date TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            expiry_date TEXT NOT NULL,
            call_oi INTEGER,
            put_oi INTEGER,
            change_in_call_oi INTEGER,
            change_in_put_oi INTEGER,
            pcr REAL,
            source TEXT,
            UNIQUE(symbol, date, timestamp)
        )
    ''')
    conn.commit()
    return conn

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

def backfill_from_trendlyne(conn, symbol, stock_id, expiry_date_str, timestamp_snapshot):
    """Fetch and save historical OI data from Trendlyne for a specific timestamp snapshot"""

    url = f"https://smartoptions.trendlyne.com/phoenix/api/live-oi-data/"
    params = {
        'stockId': stock_id,
        'expDateList': expiry_date_str,
        'minTime': "09:15",
        'maxTime': timestamp_snapshot
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

        if 'tradingDate' in input_data:
            current_date_str = input_data['tradingDate']
        else:
            current_date_str = date.today().strftime("%Y-%m-%d")

        expiry_str = input_data.get('expDateList', [expiry_date_str])[0]

        total_call_oi = 0
        total_put_oi = 0
        total_call_change = 0
        total_put_change = 0

        for strike_str, strike_data in oi_data.items():
            total_call_oi += int(strike_data.get('callOi', 0))
            total_put_oi += int(strike_data.get('putOi', 0))
            total_call_change += int(strike_data.get('callOiChange', 0))
            total_put_change += int(strike_data.get('putOiChange', 0))

        pcr = total_put_oi / total_call_oi if total_call_oi > 0 else 0

        cursor = conn.cursor()
        sql = '''
            INSERT OR REPLACE INTO oi_data
            (symbol, date, timestamp, expiry_date, call_oi, put_oi, change_in_call_oi, change_in_put_oi, pcr, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        '''

        values = (
            symbol,
            current_date_str,
            timestamp_snapshot,
            expiry_str,
            total_call_oi,
            total_put_oi,
            total_call_change,
            total_put_change,
            pcr,
            'trendlyne_backfill'
        )

        cursor.execute(sql, values)
        conn.commit()

    except Exception as e:
        print(f"[ERROR] Error fetching data for {symbol} at {timestamp_snapshot}: {e}")

def generate_time_intervals(start_time="09:15", end_time="15:30", interval_minutes=1):
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
    print("Backfilling historical OI data from Trendlyne API -> SQLite")
    print("=" * 60)

    db_conn = init_db()

    symbols = ["NIFTY"]

    successful = 0
    failed = 0

    now = datetime.now()
    market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)

    if now < market_open:
        end_time_str = "15:30"
    elif now > market_close:
        end_time_str = "15:30"
    else:
        end_time_str = now.strftime("%H:%M")

    time_slots = generate_time_intervals(end_time=end_time_str)
    print(f"Backfilling for {len(time_slots)} time slots from 09:15 to {end_time_str}")

    for symbol in symbols:
        stock_id = get_stock_id_for_symbol(symbol)
        if not stock_id:
            failed += 1
            print(f"Skipping {symbol}: No stock ID found.")
            continue

        try:
            expiry_url = f"https://smartoptions.trendlyne.com/phoenix/api/fno/get-expiry-dates/?mtype=options&stock_id={stock_id}"
            resp = requests.get(expiry_url, timeout=10)
            expiry_data = resp.json()
            if 'body' in expiry_data and 'expiryDates' in expiry_data['body']:
                default_expiry = expiry_data['body']['expiryDates'][0]
            else:
                print(f"[WARN] Could not get expiry for {symbol}. Skipping.")
                continue

            print(f"Backfilling {symbol} (Expiry: {default_expiry})...")

            for i, ts in enumerate(time_slots):
                backfill_from_trendlyne(db_conn, symbol, stock_id, default_expiry, ts)
                print(f"  -> Progress: {i+1}/{len(time_slots)} ({ts})", end='\r')

            successful += 1
            print(f"\n[DONE] {symbol} complete.")

        except Exception as e:
            print(f"\n[ERROR] Failed processing {symbol}: {e}")
            failed += 1

        time.sleep(0.5)

    db_conn.close()

    print("\n" + "=" * 60)
    print(f"[DONE] Backfill complete! {successful} successful, {failed} failed")
    print("=" * 60)
