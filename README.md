<div align="center">
<h1>🚀 API-Expert-Option – Async WebSocket Client for Expert Option</h1>
<p><b>High-performance, production-ready Python client with <u>Playwright</u> login (get_token) & full trade lifecycle.</b></p>
<p>
  <a href="https://www.python.org/"><img alt="Python" src="https://img.shields.io/pypi/pyversions/pandas?label=python&logo=python" /></a>
  <a href="https://docs.python.org/3/library/asyncio.html"><img alt="AsyncIO" src="https://img.shields.io/badge/Framework-AsyncIO-informational" /></a>
  <a href="https://playwright.dev/"><img alt="Playwright" src="https://img.shields.io/badge/Login-Playwright-blue" /></a>
  <a href="#"><img alt="Status" src="https://img.shields.io/badge/Status-Stable-success" /></a>
  <a href="#"><img alt="License" src="https://img.shields.io/github/license/A11ksa/API-Expert-Option?style=flat-square" /></a>
</p>
</div>

---

## ✨ Features
- ⚡ **Async**: blazing fast non-blocking WebSocket client
- 🔐 **Playwright Login**: secure token-based login with get_token()
- 📈 **Market Data**: assets, quotes, candles, payouts in real-time
- 🧾 **Orders**: open, monitor, and resolve trades with full lifecycle
- 🩺 **Logging & Debugging**: with built-in health-checks
- 🧪 **Examples**: quick-start usage and scripts

---

## 🔧 Installation

```bash
git clone https://github.com/A11ksa/API-Expert-Option
cd API-Expert-Option
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate
pip install -U pip
pip install .
python -m playwright install chromium
```

---

## 🚀 Quick Start

```python
import asyncio
from api_expert_option import AsyncExpertOptionClient, OrderDirection, get_token

async def main():
    # 1. Fetch token using playwright helper (get_token)
    token_info = get_token(email="you@example.com", password="yourpassword")
    demo_token = token_info.get("demo")

    # 2. Connect
    client = AsyncExpertOptionClient(token=demo_token, is_demo=True)
    if not await client.connect():
        print("Connection failed.")
        return

    # 3. Balance
    balance = await client.get_balance()
    print(f"Balance: {balance.balance} {balance.currency}")

    # 4. Place Order
    order = await client.place_order(
        asset="EURUSD",
        amount=5.0,
        direction=OrderDirection.CALL,
        duration=60
    )

    # 5. Await result
    profit, status = await client.check_win(order.order_id)
    print("Result:", status, "Profit:", profit)

    # 6. Disconnect
    await client.disconnect()

asyncio.run(main())
```

---

## 📐 Architecture

```
+----------------------------+              +-----------------------------+
|      Playwright Login     |   --> TOKEN → |   sessions/session.json     |
|     (opens browser)       |              |    demo/live tokens stored  |
+----------------------------+              +-----------------------------+
              |
              v
+-----------------------------+ WebSocket (async) +--------------------------+
|  AsyncExpertOptionClient    |<----------------->|   Expert Option Servers  |
+-----------------------------+                   +--------------------------+
```

---

## 💡 Examples

### 🔁 Streaming Candles
```python
await client.subscribe_candles("EURUSD", timeframe=60)
async for candle in client.iter_candles("EURUSD", 60):
    print(candle)
```

### 📉 Trade with PUT
```python
order = await client.place_order(
    asset="EURUSD",
    amount=10.0,
    direction=OrderDirection.PUT,
    duration=60
)
profit, status = await client.check_win(order.order_id)
print(status, profit)
```

---

## 🗝️ Tokens & Sessions

> `get_token()` will store tokens in `sessions/session.json`

Manual override:

```json
{
  "live": "EXPERT_LIVE_TOKEN",
  "demo": "EXPERT_DEMO_TOKEN"
}
```

---

## 🆘 Troubleshooting

- ❌ **Browser not installed?** → `python -m playwright install chromium`
- 🔒 **Login fails?** → delete `sessions/session.json`
- 🌐 **Region errors?** → check IP or VPN
- ⚠️ **SSL errors?** → check your Python/OpenSSL env

---

## 📬 Contact

<p align="left">
  <a href="mailto:ar123ksa@gmail.com">
    <img alt="Email" src="https://img.shields.io/badge/Email-ar123ksa%40gmail.com-EA4335?logo=gmail" />
  </a>
  <a href="https://t.me/A11ksa">
    <img alt="Telegram" src="https://img.shields.io/badge/Telegram-@A11ksa-26A5E4?logo=telegram" />
  </a>
</p>

---

## 🛠️ Contributing

1. Fork + open a pull request
2. Follow formatting (PEP8, type hints)
3. Include tests when appropriate

---

## 📄 License

MIT — see `LICENSE`
