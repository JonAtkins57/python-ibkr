from ib_insync import *
import csv
import os

# ---- CONFIG ----
TWS_PORT = 4001
CLIENT_ID = 3
SOURCE = 'assigned_positions.csv'  # or set to None to use MANUAL list
# MANUAL = ['TSLL', 'F', 'SNAP', 'SPY'] need higher subscription: 📦 US Equity and Options Add-On Streaming Bundle ($4.50/mo) This covers NYSE + AMEX + NASDAQ + OPRA

DELAY = 1.5

ib = IB()
ib.connect('127.0.0.1', TWS_PORT, clientId=CLIENT_ID)

if SOURCE and os.path.exists(SOURCE):
    with open(SOURCE, newline='') as f:
        reader = csv.DictReader(f)
        tickers = list({row['Symbol'].strip().upper() for row in reader})
else:
    tickers = MANUAL

results = []

for symbol in tickers:
    try:
        stock = Stock(symbol, 'SMART', 'USD')
        ib.qualifyContracts(stock)
        chains = ib.reqSecDefOptParams(stock.symbol, '', stock.secType, stock.conId)
        chain = next((c for c in chains if c.exchange == 'SMART'), None)

        if not chain or not chain.expirations or not chain.strikes:
            results.append((symbol, '❌ No options', '', '', '', '', ''))
            continue

        expiry = sorted(chain.expirations)[0]
        trading_class = chain.tradingClass
        multiplier = chain.multiplier

        market_data = ib.reqMktData(stock)
        ib.sleep(DELAY)
        price = float(market_data.last or market_data.close)

        otm_strikes = sorted([s for s in chain.strikes if s < price], reverse=True)
        if not otm_strikes:
            results.append((symbol, '✅ Options', 'No OTM', '', '', '', ''))
            continue
        strike = otm_strikes[0]

        option = Option(symbol=symbol, lastTradeDateOrContractMonth=expiry,
                        strike=strike, right='P', exchange='SMART',
                        tradingClass=trading_class, multiplier=multiplier, currency='USD')
        ib.qualifyContracts(option)

        quote = ib.reqMktData(option)
        ib.sleep(DELAY)
        bid = float(quote.bid or 0)
        ask = float(quote.ask or 0)
        mid = (bid + ask) / 2 if ask > 0 and bid > 0 else 0
        spread_pct = ((ask - bid) / ask) * 100 if ask > 0 else 0
        roi = (mid * 100) / (strike * 100) if strike > 0 else 0
        iv = round(quote.impliedVolatility * 100, 2) if quote.impliedVolatility else ''

        results.append((
            symbol,
            '✅ Options',
            expiry,
            strike,
            f"${bid:.2f} / ${ask:.2f}",
            f"{iv}%",
            f"{roi:.2%} ROI, {spread_pct:.1f}% spread"
        ))
    except Exception as e:
        results.append((symbol, '❌ Error', '', '', '', '', str(e)))

ib.disconnect()

# Output
import pandas as pd
df = pd.DataFrame(results, columns=['Symbol', 'Status', 'Expiry', 'Strike', 'Bid/Ask', 'IV', 'Est. ROI & Spread'])
print(df.to_string(index=False))
