from ib_insync import *

# Connect to TWS or IB Gateway
TWS_PORT = 4001
CLIENT_ID = 3
ib = IB()
ib.connect('127.0.0.1', TWS_PORT, clientId=CLIENT_ID)

# Get account summary
summary = ib.accountSummary()
print("=== Account Summary ===")
for row in summary:
    if row.tag in ['NetLiquidation', 'TotalCashValue', 'AvailableFunds', 'ExcessLiquidity']:
        print(f"{row.tag}: {row.value} {row.currency}")

# Get full cash balance
account_values = ib.accountValues()
cash_balance = [v for v in account_values if v.tag == 'CashBalance']
print("\n=== Cash Balances ===")
for v in cash_balance:
    print(f"{v.account}: {v.value} {v.currency}")

# Get current positions
positions = ib.positions()
print("\n=== Open Positions ===")
for pos in positions:
    contract = pos.contract
    print(f"{contract.symbol} ({contract.secType}): {pos.position} shares @ avg cost {pos.avgCost}")

ib.disconnect()
