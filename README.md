<div align="center">

<h1>🚀 API-ExpertOption – Async WebSocket Client for ExpertOption</h1>

<p><b>High-performance, production-ready Python client with <u>Playwright</u> login (Token) & full trade lifecycle.</b></p>

<p>
  <a href="https://www.python.org/"><img alt="Python" src="https://img.shields.io/pypi/pyversions/pandas?label=python&logo=python" /></a>
  <a href="https://docs.python.org/3/library/asyncio.html"><img alt="AsyncIO" src="https://img.shields.io/badge/Framework-AsyncIO-informational" /></a>
  <a href="https://playwright.dev/"><img alt="Playwright" src="https://img.shields.io/badge/Login-Playwright-blue" /></a>
  <a href="https://github.com/A11ksa/API-Expert-Option/actions"><img alt="Status" src="https://img.shields.io/badge/Status-Stable-success" /></a>
  <a href="https://github.com/A11ksa/API-Expert-Option/blob/main/LICENSE"><img alt="License" src="https://img.shields.io/github/license/A11ksa/API-Expert-Option?style=flat-square" /></a>
</p>

</div>

---

## ✨ Features
- ⚡ **Async**: non-blocking WebSocket client optimized for realtime data
- 🔐 **Playwright Login**: automated Token extraction & reuse (demo/live)
- 📈 **Market Data**: assets, payouts, quotes, and real-time candles
- 🧾 **Orders**: open, track, and resolve full trade lifecycle (WIN/LOSS/DRAW)
- 🩺 **Monitoring**: structured logging & health checks
- 🧪 **Examples**: quick-start scripts for connection, candles, and orders

---

## 🧭 Table of Contents
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Why Playwright?](#why-playwright)
- [Architecture](#architecture)
- [Examples](#examples)
- [Sessions & Token](#sessions--token)
- [Troubleshooting](#troubleshooting)
- [Contact](#-contact)
- [Contributing](#contributing)
- [License](#license)

---

## Installation
```bash
git clone https://github.com/A11ksa/API-Expert-Option
cd API-Expert-Option
python -m venv venv
# Linux/macOS:
source venv/bin/activate
# Windows:
venv\Scripts\activate
pip install -U pip
pip install .
python -m playwright install chromium
