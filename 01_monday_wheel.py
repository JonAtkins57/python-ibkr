from ib_insync import *
import csv
import os
import argparse
from datetime import datetime, timedelta

# ---- CONFIG ----
UNDERLYINGS = ['TSLL', 'F', 'SNAP', 'OLO','LUMN','CLNE','PAYO', 'TSLQ']
MIN_RETURN = 0.02
CASH_LIMIT = 10000
CONTRACTS = 1
TWS_PORT = 4001
CLIENT_ID = 1
DELAY = 1.5
TRACKING_FILE = 'assigned_positions.csv'
LOG_FILE = 'wheel_log.csv'
MIN_CC_BID = 0.50  # Minimum premium to sell covered calls

# ---- DRYRUN FLAG ----
parser = argparse.ArgumentParser()
parser.add_argument('--dryrun', action='store_true', help='Simulate only, no orders placed')
args = parser.parse_args()
DRYRUN = args.dryrun

# ---- INIT ----
ib = IB()
ib.connect('127.0.0.1', TWS_PORT, clientId=CLIENT_ID)
print(f"Connected to TWS: {ib.isConnected()}")

# ---- Utility: Find Next Friday ----
def get_next_friday():
    today = datetime.now().date()
    days_ahead = 4 - today.weekday()  # 4 is Friday
    if days_ahead <= 0:
        days_ahead += 7
    next_friday = today + timedelta(days=days_ahead)
    return next_friday.strftime('%Y%m%d')  # IBKR expects YYYYMMDD

# ---- STEP 1: Assigned Positions and Active Symbols ----
if os.path.exists(TRACKING_FILE):
    with open(TRACKING_FILE, newline='') as f:
        reader = csv.DictReader(f)
        assigned_positions = [(row['Symbol'], int(row['Shares'])) for row in reader]
else:
    assigned_positions = []

if assigned_positions:
    active_symbols = set(UNDERLYINGS).intersection(set(s for s, _ in assigned_positions))
    print(f"Symbols from assigned_positions AND UNDERLYINGS: {active_symbols}")
else:
    print("No assigned_positions loaded, using UNDERLYINGS list.")
    active_symbols = set(UNDERLYINGS)

wheel_log_rows = []

# ---- STEP 2: Covered Calls (Select OTM Strike with Highest ROI) ----
for symbol, shares in assigned_positions:
    if symbol not in active_symbols:
        continue
    stock = Stock(symbol, 'SMART', 'USD')
    ib.qualifyContracts(stock)
    chains = ib.reqSecDefOptParams(stock.symbol, '', stock.secType, stock.conId)
    chain = next((c for c in chains if c.exchange == 'SMART'), chains[0] if chains else None)
    if not chain:
        print(f"❌ No option chain found for {symbol}")
        continue

    trading_class = chain.tradingClass
    multiplier = chain.multiplier
    all_expiries = sorted(chain.expirations)
    next_friday_str = get_next_friday()
    expiry = next((e for e in all_expiries if e >= next_friday_str), all_expiries[0] if all_expiries else None)
    if not expiry:
        print(f"❌ No suitable expiry found for {symbol}")
        continue

    strikes = sorted(chain.strikes)
    market_price = ib.reqMktData(stock)
    ib.sleep(DELAY)
    current_price = float(market_price.last or market_price.close or 0)
    otm_strikes = [s for s in strikes if s > current_price]

    best_row = None
    best_roi = 0

    for cc_strike in otm_strikes:
        option = Option(symbol=symbol, lastTradeDateOrContractMonth=expiry,
                        strike=cc_strike, right='C', exchange='SMART',
                        tradingClass=trading_class, multiplier=multiplier, currency='USD')
        try:
            ib.qualifyContracts(option)
        except Exception as e:
            print(f"❌ Could not qualify CC {symbol} {cc_strike}: {e}")
            continue

        cc_market = ib.reqMktData(option)
        ib.sleep(DELAY)
        bid = float(cc_market.bid or 0)
        roi = (bid * 100) / (current_price * 100) if current_price > 0 else 0

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        row = {
            'Timestamp': timestamp,
            'Type': '',
            'OrderType': 'CC',
            'Symbol': symbol,
            'Strike': cc_strike,
            'Bid': bid,
            'ROI': roi,
            'OrderID': '',
            'Qty': shares // 100,
            'Action': 'SELL',
            'Expiry': expiry,
            'Status': '',
        }

        if bid < MIN_CC_BID or roi < MIN_RETURN:
            row['Type'] = 'SKIPPED'
            if bid < MIN_CC_BID:
                row['Status'] = f"CC bid < ${MIN_CC_BID:.2f}"
            else:
                row['Status'] = f"CC ROI < {MIN_RETURN:.2%}"
            wheel_log_rows.append(row)
            continue

        if roi > best_roi:
            best_row = row.copy()
            best_row['Type'] = 'PLACED'
            best_row['Status'] = ''
            best_row['Bid'] = bid
            best_row['ROI'] = roi
            best_row['Strike'] = cc_strike
            # Save these in case multiple qualify, we want the highest ROI

    if best_row:
        print(f"[CC] {symbol} {expiry} Call ${best_row['Strike']} @ ${best_row['Bid']:.2f} (ROI: {best_row['ROI']:.2%})")
        if not DRYRUN:
            option = Option(symbol=symbol, lastTradeDateOrContractMonth=expiry,
                            strike=best_row['Strike'], right='C', exchange='SMART',
                            tradingClass=trading_class, multiplier=multiplier, currency='USD')
            order = LimitOrder('SELL', shares // 100, best_row['Bid'], tif='GTC')
            trade = ib.placeOrder(option, order)
            best_row['OrderID'] = str(trade.order.orderId)
            best_row['Status'] = "PLACED"
        else:
            best_row['Status'] = "DRYRUN"
        wheel_log_rows.append(best_row)
    else:
        print(f"[CC] {symbol} No OTM strikes met ROI/bid requirements.")

# ---- STEP 3: Cash-Secured Puts ----
used_cash = 0
for symbol in active_symbols:
    stock = Stock(symbol, 'SMART', 'USD')
    ib.qualifyContracts(stock)
    market_price = ib.reqMktData(stock)
    ib.sleep(DELAY)
    price = float(market_price.last or market_price.close or 0)
    print(f"{symbol} price: ${price:.2f}")

    chains = ib.reqSecDefOptParams(stock.symbol, '', stock.secType, stock.conId)
    chain = next((c for c in chains if c.exchange == 'SMART'), chains[0] if chains else None)
    if not chain:
        print(f"❌ No option chain found for {symbol}")
        continue

    trading_class = chain.tradingClass
    multiplier = chain.multiplier
    all_expiries = sorted(chain.expirations)
    next_friday_str = get_next_friday()
    expiry = next((e for e in all_expiries if e >= next_friday_str), all_expiries[0] if all_expiries else None)
    if not expiry:
        print(f"❌ No suitable expiry found for {symbol}")
        continue

    valid_strikes = sorted([s for s in chain.strikes if s < price], reverse=True)[:5]

    for strike in valid_strikes:
        option = Option(symbol=symbol, lastTradeDateOrContractMonth=expiry,
                        strike=strike, right='P', exchange='SMART',
                        tradingClass=trading_class, multiplier=multiplier, currency='USD')
        try:
            ib.qualifyContracts(option)
        except Exception as e:
            print(f"❌ Could not qualify {symbol} PUT ${strike}: {e}")
            continue

        if not option.conId:
            print(f"❌ No valid contract for {symbol} strike ${strike}")
            continue

        market = ib.reqMktData(option)
        ib.sleep(DELAY)
        bid = float(market.bid or 0)
        premium = bid * 100 * CONTRACTS
        collateral = strike * 100 * CONTRACTS
        roi = premium / collateral if collateral > 0 else 0
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        row = {
            'Timestamp': timestamp,
            'Type': '',
            'OrderType': 'CSP',
            'Symbol': symbol,
            'Strike': strike,
            'Bid': bid,
            'ROI': roi,
            'OrderID': '',
            'Qty': CONTRACTS,
            'Action': 'SELL',
            'Expiry': expiry,
            'Status': '',
        }

        if bid <= 0:
            print(f"❌ Skipped: {symbol} PUT ${strike} — no bid")
            row['Type'] = 'REJECTED'
            row['Status'] = "No bid"
            wheel_log_rows.append(row)
            continue

        if roi >= MIN_RETURN and (used_cash + collateral) <= CASH_LIMIT:
            print(f"✅ CSP: {symbol} PUT ${strike} @ ${bid:.2f} (ROI: {roi:.2%})")
            row['Type'] = 'PLACED'
            if not DRYRUN:
                order = LimitOrder('SELL', CONTRACTS, bid, tif='GTC')
                trade = ib.placeOrder(option, order)
                row['OrderID'] = str(trade.order.orderId)
                row['Status'] = "PLACED"
            else:
                row['Status'] = "DRYRUN"
            used_cash += collateral
        else:
            row['Type'] = 'REJECTED'
            row['Status'] = f"ROI too low ({roi:.2%}) or exceeds cash"
            print(f"❌ Rejected: {symbol} PUT ${strike} @ ${bid:.2f} (ROI: {roi:.2%})")
        wheel_log_rows.append(row)

ib.disconnect()

# ---- WRITE LOG ----
headers = [
    'Timestamp', 'Type', 'OrderType', 'Symbol', 'Strike', 'Bid', 'ROI',
    'OrderID', 'Qty', 'Action', 'Expiry', 'Status'
]
file_exists = os.path.exists(LOG_FILE)
write_header = not file_exists or os.stat(LOG_FILE).st_size == 0

with open(LOG_FILE, 'a', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=headers)
    if write_header:
        writer.writeheader()
    for row in wheel_log_rows:
        writer.writerow(row)

print(f"\nLog written to {LOG_FILE}")
