# ✨ API-Expert-Option – Setup & Installation (Token Login Ready)

> A fast setup guide for installing **API-Expert-Option**, enabling **Playwright**-based token login (get_token), and testing your first connection.

<p align="center">
  <img alt="Python" src="https://img.shields.io/pypi/pyversions/pandas?label=python&logo=python" />
  <img alt="AsyncIO" src="https://img.shields.io/badge/Framework-AsyncIO-informational" />
  <img alt="Playwright" src="https://img.shields.io/badge/Login-Playwright-blue" />
  <img alt="Status" src="https://img.shields.io/badge/Status-Stable-success" />
  <img alt="License" src="https://img.shields.io/github/license/A11ksa/API-Expert-Option" />
</p>

---

## ✅ Requirements

- Python 3.8+
- `pip`, `venv`, and `playwright`
- Access to `expertoption.com` from your region

---

## ⚙️ Installation

```bash
git clone https://github.com/A11ksa/API-Expert-Option
cd API-Expert-Option
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -U pip
pip install .
python -m playwright install chromium
```

---

## 🔐 Login Setup (get_token)

```json
# sessions/config.json
{
  "email": "you@example.com",
  "password": "YourPassword"
}
```

> First-time login opens Chromium → logs in → saves your **demo/live token** into:
```
sessions/session.json
```

---

## 🧪 Run Smoke Test

```bash
python test1.py
```

Expected output:
- Connection success
- Account balance
- (optional) place order
- Result WIN/LOSS/DRAW

---

## 🆘 Troubleshooting

| Problem               | Solution                                 |
|-----------------------|------------------------------------------|
| Playwright error      | `python -m playwright install chromium`  |
| Token expired         | Delete `session.json` and retry login    |
| SSL error             | Check Python + OpenSSL install           |
| No candles/trades     | Check IP / region or try VPN             |

---

## 📬 Contact

📧 [ar123ksa@gmail.com](mailto:ar123ksa@gmail.com)  
💬 [Telegram: @A11ksa](https://t.me/A11ksa)

---

## 🏁 Done

You’re now ready to trade with **Expert Option** + fully async Python client.
