from ib_insync import *
import datetime

# Connect to IB Gateway
ib = IB()
ib.connect('127.0.0.1', 7497, clientId=1)  # TWS default port

# Define underlying
symbol = 'TSLL'
contract = Stock(symbol, 'SMART', 'USD')
ib.qualifyContracts(contract)

# Define strikes and premiums you want to target (mock for now)
strikes = [11.0, 10.5, 10.0]
expiry = (datetime.date.today() + datetime.timedelta(days=(4 - datetime.date.today().weekday()) % 7)).strftime('%Y%m%d')

# Place orders
for strike in strikes:
    option = Option(symbol, expiry, strike, 'P', 'SMART')
    ib.qualifyContracts(option)

    order = LimitOrder('SELL', 1, 0.40)  # Replace 0.40 with real bid later
    trade = ib.placeOrder(option, order)
    print(f"Placed order for strike {strike}")

ib.disconnect()
