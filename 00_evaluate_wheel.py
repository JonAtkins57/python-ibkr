from ib_insync import *
import csv
import os
from datetime import datetime, timedelta
import pandas as pd

# ---- CONFIG ----
TWS_PORT = 4001
CLIENT_ID = 3
SOURCE = 'assigned_positions.csv'
CHAIN_OUT = 'option_chain_eval.csv'
POS_OUT = 'assigned_positions_eval.csv'
DELAY = 1.5
ROI_THRESHOLD = 0.02  # 2% weekly

# ---- Connect ----
ib = IB()
ib.connect('127.0.0.1', TWS_PORT, clientId=CLIENT_ID)

# ---- Utility: Next Friday ----
def get_next_friday():
    today = datetime.now().date()
    days_ahead = 4 - today.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    next_friday = today + timedelta(days=days_ahead)
    return next_friday.strftime('%Y%m%d')

# ---- Load Assigned Positions ----
if SOURCE and os.path.exists(SOURCE):
    with open(SOURCE, newline='') as f:
        reader = csv.DictReader(f)
        positions = [row for row in reader]
        tickers = list({row['Symbol'].strip().upper() for row in positions})
else:
    positions = []
    tickers = []

# ---- Evaluate Positions ----
pos_eval_rows = []
for row in positions:
    symbol = row['Symbol'].strip().upper()
    shares = int(row.get('Shares', 0) or 0)
    cost_basis = float(row.get('CostBasis', 0) or 0)
    try:
        stock = Stock(symbol, 'SMART', 'USD')
        ib.qualifyContracts(stock)
        md = ib.reqMktData(stock)
        ib.sleep(DELAY)
        price = float(md.last or md.close or 0)
        pos_eval_rows.append({
            'Symbol': symbol,
            'Shares': shares,
            'CostBasis': cost_basis,
            'CurrentPrice': price,
            'TotalValue': price * shares,
            'UnrealizedPL': (price - cost_basis) * shares
        })
    except Exception as e:
        pos_eval_rows.append({
            'Symbol': symbol,
            'Shares': shares,
            'CostBasis': cost_basis,
            'CurrentPrice': 'Error',
            'TotalValue': '',
            'UnrealizedPL': f"Error: {e}"
        })

# ---- Option Chain Evaluation: Only Strikes Near-the-Money, >= 2% ROI ----
chain_rows = []
for symbol in tickers:
    try:
        stock = Stock(symbol, 'SMART', 'USD')
        ib.qualifyContracts(stock)
    except Exception:
        continue  # skip non-qualifying symbols
    try:
        chains = ib.reqSecDefOptParams(stock.symbol, '', stock.secType, stock.conId)
        chain = next((c for c in chains if c.exchange == 'SMART'), None)
        if not chain or not chain.expirations or not chain.strikes:
            continue

        all_expiries = sorted(chain.expirations)
        next_friday_str = get_next_friday()
        expiry = next((e for e in all_expiries if e >= next_friday_str), all_expiries[0] if all_expiries else None)
        if not expiry:
            continue

        trading_class = chain.tradingClass
        multiplier = chain.multiplier

        # Get spot price for smart filtering
        md = ib.reqMktData(stock)
        ib.sleep(DELAY)
        spot_price = float(md.last or md.close or 0)
        if not spot_price or spot_price == 0:
            continue

        # Only look at 3 strikes below/near spot, and only if potential ROI >= 2%
        eligible_strikes = [s for s in sorted(chain.strikes, reverse=True) if s < spot_price][:5]
        for strike in eligible_strikes:
            option = Option(symbol=symbol, lastTradeDateOrContractMonth=expiry,
                            strike=strike, right='P', exchange='SMART',
                            tradingClass=trading_class, multiplier=multiplier, currency='USD')
            try:
                ib.qualifyContracts(option)
                if not option.conId:
                    continue
            except Exception:
                continue
            q = ib.reqMktData(option)
            ib.sleep(DELAY)
            bid = float(q.bid or 0)
            ask = float(q.ask or 0)
            mid = (bid + ask) / 2 if ask > 0 and bid > 0 else 0
            roi = (mid * 100) / (strike * 100) if strike > 0 else 0
            if roi < ROI_THRESHOLD:
                continue
            iv = round(q.impliedVolatility * 100, 2) if q.impliedVolatility else ''
            spread_pct = ((ask - bid) / ask) * 100 if ask > 0 else 0
            chain_rows.append({
                'Symbol': symbol,
                'Expiry': expiry,
                'Strike': strike,
                'Bid': bid,
                'Ask': ask,
                'Mid': mid,
                'IV': iv,
                'SpotPrice': spot_price,
                'EstROI': roi,
                'EstROI%': f"{roi:.2%}",
                'SpreadPct': f"{spread_pct:.1f}%",
                'Meets2pct': "YES"
            })
    except Exception:
        continue

ib.disconnect()

# ---- Output Files ----
pd.DataFrame(pos_eval_rows).to_csv(POS_OUT, index=False)
pd.DataFrame(chain_rows).to_csv(CHAIN_OUT, index=False)

print(f"\nAssigned positions (with price and P/L) written to {POS_OUT}")
print(f"Option chain CSP eval (next Friday puts, ROI, 2% filter) written to {CHAIN_OUT}")
