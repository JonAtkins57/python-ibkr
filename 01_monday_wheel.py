# run Monday morning 9:45am et:  wheels F, SNAP, TSLL
from ib_insync import *
import csv
import os
import argparse
from datetime import datetime

# ---- CONFIG ----
UNDERLYINGS = ['TSLL', 'F', 'SNAP', 'OLO']
MIN_RETURN = 0.02
CASH_LIMIT = 10000
CONTRACTS = 1
TWS_PORT = 4001
CLIENT_ID = 1
DELAY = 1.5
TRACKING_FILE = 'assigned_positions.csv'
LOG_FILE = 'wheel_log.csv'
rejected_trades = []
filled_trades = []

# ---- DRYRUN FLAG ----
parser = argparse.ArgumentParser()
parser.add_argument('--dryrun', action='store_true', help='Simulate only, no orders placed')
args = parser.parse_args()
DRYRUN = args.dryrun

# ---- INIT ----
ib = IB()
ib.connect('127.0.0.1', TWS_PORT, clientId=CLIENT_ID)
print(f"Connected to TWS: {ib.isConnected()}")

# ---- STEP 1: COVERED CALLS ----
if os.path.exists(TRACKING_FILE):
    with open(TRACKING_FILE, newline='') as f:
        reader = csv.DictReader(f)
        assigned_positions = [(row['Symbol'], int(row['Shares'])) for row in reader]
else:
    assigned_positions = []

for symbol, shares in assigned_positions:
    stock = Stock(symbol, 'SMART', 'USD')
    ib.qualifyContracts(stock)
    chains = ib.reqSecDefOptParams(stock.symbol, '', stock.secType, stock.conId)
    chain = next((c for c in chains if c.exchange == 'SMART'), chains[0] if chains else None)
    if not chain:
        print(f"❌ No option chain found for {symbol}")
        continue

    trading_class = chain.tradingClass
    multiplier = chain.multiplier
    expiry = sorted(chain.expirations)[0]
    strikes = sorted(chain.strikes)

    market_price = ib.reqMktData(stock)
    ib.sleep(DELAY)
    current_price = float(market_price.last or market_price.close or 0)
    otm_strikes = [s for s in strikes if s > current_price]
    if not otm_strikes:
        continue

    cc_strike = otm_strikes[0]
    option = Option(symbol=symbol, lastTradeDateOrContractMonth=expiry,
                    strike=cc_strike, right='C', exchange='SMART',
                    tradingClass=trading_class, multiplier=multiplier, currency='USD')
    ib.qualifyContracts(option)
    cc_market = ib.reqMktData(option)
    ib.sleep(DELAY)

    bid = float(cc_market.bid or 0)
    if bid > 0:
        print(f"[CC] {symbol} {expiry} Call ${cc_strike} @ ${bid:.2f}")
        if not DRYRUN:
            order = LimitOrder('SELL', shares // 100, bid, tif='GTC')
            ib.placeOrder(option, order)

# ---- STEP 2: CSPs ----
for symbol in UNDERLYINGS:
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
    expiry = sorted(chain.expirations)[0]
    valid_strikes = sorted([s for s in chain.strikes if s < price], reverse=True)[:5]

    used_cash = 0
    for strike in valid_strikes:
        option = Option(symbol=symbol, lastTradeDateOrContractMonth=expiry,
                        strike=strike, right='P', exchange='SMART',
                        tradingClass=trading_class, multiplier=multiplier, currency='USD')
        try:
            ib.qualifyContracts(option)
        except:
            print(f"❌ Could not qualify {symbol} PUT ${strike}")
            continue

        if not option.conId:
            print(f"❌ No valid contract for {symbol} strike ${strike}")
            continue

        market = ib.reqMktData(option)
        ib.sleep(DELAY)
        bid = float(market.bid or 0)
        if bid <= 0:
            rejected_trades.append((symbol, strike, 0, 0, strike * 100))
            print(f"❌ Skipped: {symbol} PUT ${strike} — no bid")
            continue

        premium = bid * 100 * CONTRACTS
        collateral = strike * 100 * CONTRACTS
        roi = premium / collateral

        if roi >= MIN_RETURN and (used_cash + collateral) <= CASH_LIMIT:
            print(f"✅ CSP: {symbol} PUT ${strike} @ ${bid:.2f} (ROI: {roi:.2%})")
            if not DRYRUN:
                order = LimitOrder('SELL', CONTRACTS, bid, tif='GTC')
                ib.placeOrder(option, order)
            used_cash += collateral
            filled_trades.append((symbol, strike, bid, roi))
        else:
            rejected_trades.append((symbol, strike, bid, roi, collateral))
            print(f"❌ Rejected: {symbol} PUT ${strike} @ ${bid:.2f} (ROI: {roi:.2%})")

ib.disconnect()

print("\n===== CSP Summary =====")
total_premium = sum(bid * 100 for (_, _, bid, _) in filled_trades)
total_collateral = sum(strike * 100 for (_, strike, _, _) in filled_trades)
est_return = (total_premium / total_collateral) if total_collateral else 0

print(f"Filled Trades: {len(filled_trades)}")
print(f"Total Premium: ${total_premium:.2f}")
print(f"Total Capital Used: ${total_collateral:.2f}")
print(f"Estimated Weekly ROI: {est_return:.2%}")
print(f"Projected Annual (compounded): {(1 + est_return)**52 - 1:.2%}")

if rejected_trades:
    print("\n===== Rejected Trades (Below ROI Threshold) =====")
    for symbol, strike, bid, roi, col in rejected_trades:
        print(f"• {symbol} PUT ${strike} @ ${bid:.2f} → ROI: {roi:.2%} (Needed: {MIN_RETURN:.2%})")

# ---- WRITE LOG ----
log_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
with open(LOG_FILE, 'a', newline='') as f:
    writer = csv.writer(f)
    if os.stat(LOG_FILE).st_size == 0:
        writer.writerow(['Timestamp', 'Type', 'Symbol', 'Strike', 'Bid', 'ROI'])
    for symbol, strike, bid, roi in filled_trades:
        writer.writerow([log_time, 'FILLED', symbol, strike, bid, f"{roi:.4f}"])
    for symbol, strike, bid, roi, _ in rejected_trades:
        writer.writerow([log_time, 'REJECTED', symbol, strike, bid, f"{roi:.4f}"])

print(f"\nLog written to {LOG_FILE}")
