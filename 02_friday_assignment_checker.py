# run after market close 4:15 pm et

import csv
from ib_insync import *

# ---- CONFIG ----
PORTFOLIO_TRACKING_FILE = 'assigned_positions.csv'
TWS_PORT = 4001
CLIENT_ID = 2  # Separate client ID from Monday bot

# ---- INIT ----
ib = IB()
ib.connect('127.0.0.1', TWS_PORT, clientId=CLIENT_ID)
print(f"Connected to TWS: {ib.isConnected()}")

# ---- STEP 1: Fetch all current positions ----
positions = ib.positions()

# ---- STEP 2: Filter for assigned stocks (in 100-share blocks)
assigned = []
for pos in positions:
    if pos.position >= 100 and pos.contract.secType == 'STK':
        symbol = pos.contract.symbol
        shares = int(pos.position)
        assigned.append((symbol, shares))

# ---- STEP 3: Save to CSV for Monday bot
if assigned:
    with open(PORTFOLIO_TRACKING_FILE, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Symbol', 'Shares'])
        writer.writerows(assigned)
    print(f"Saved assigned positions: {assigned}")
else:
    print("No assigned shares found.")

ib.disconnect()
