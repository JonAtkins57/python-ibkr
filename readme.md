# IBKR Wheel Automation

This repo automates a weekly options wheel strategy using Interactive Brokers (IBKR) API.
It executes cash-secured puts (CSPs) and covered calls (CCs) using a defined ruleset.

---

## 🧠 Strategy Summary

- Sell **cash-secured puts** (CSPs) every Monday on tickers like `TSLL`, `F`, `SNAP`, and `OLO`
- If assigned, sell **covered calls** the following Monday
- Only trade options that yield **≥2% weekly ROI**
- Skip low-liquidity or invalid contracts
- Trades are placed automatically through the IBKR API
- Tracks filled & rejected trades with logging

---

## 📂 Files Overview

| File                              | Purpose                                                  |
| --------------------------------- | -------------------------------------------------------- |
| `00_evaluate_wheel.py`            | Evaluate tickers for wheel suitability (IV, ROI, spread) |
| `01_monday_wheel.py`              | Main automation script — sells CSPs and CCs              |
| `02_friday_assignment_checker.py` | End-of-week scanner for assigned stocks                  |
| `assigned_positions.csv`          | Tracks assigned shares to inform covered call sales      |
| `wheel_log.csv`                   | Logs filled & rejected trades with ROI, timestamp, etc.  |
| `test_api.py`                     | Simple test of IBKR connection and contract fetch        |
| `readme.md`                       | You're reading it!                                       |

---

## 🚀 Usage

### 1. ✅ Prerequisites

- IBKR TWS or Gateway **running** with API enabled (port `4001`)
- Market data subscriptions for options and equities (e.g. NASDAQ, OPRA, NYSE)
- Python 3.9+

```bash
pip install ib_insync
```

---

### 2. 🛠 Configuration

Edit `01_monday_wheel.py`:

```python
UNDERLYINGS = ['TSLL', 'F', 'SNAP']   # Stocks to wheel
MIN_RETURN = 0.02                     # Minimum weekly ROI (2%)
CASH_LIMIT = 10000                   # Max capital to deploy across CSPs
```

---

### 3. 🗓 Weekly Schedule

| Day        | Script                            | Purpose                                     |
| ---------- | --------------------------------- | ------------------------------------------- |
| **Friday** | `02_friday_assignment_checker.py` | Scan for assigned puts (before close)       |
| **Monday** | `01_monday_wheel.py`              | Place CSPs + CCs, optionally use `--dryrun` |

```bash
python 01_monday_wheel.py            # live trading
python 01_monday_wheel.py --dryrun   # simulate only
```

---

### 4. 📊 Output Files

- `wheel_log.csv`: Logs all filled/rejected trades with timestamp, strike, ROI
- Console output: Summary of total premium, estimated ROI, and projected annual return

---

## 💡 Example Account Setup

From your IBKR dashboard:

- ✅ $72,053 settled cash
- 📈 $544K buying power
- 🎯 Only risking $10K/week in wheel strategy initially

---

## 📈 Future Ideas

- Covered call ROI filter
- Auto-roll if options expire ITM
- Telegram/Email alerts
- Portfolio summary dashboard

---

Happy wheeling! 💰 Let your cash work for you.

---

Questions? DM your friendly bot.
