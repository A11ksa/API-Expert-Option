
```markdown
# ✨ API-ExpertOption – Setup & Installation (Playwright Login Ready)

> **Purpose:** A polished, one-stop setup guide for installing **API-ExpertOption**, enabling **Playwright**-based login (Token extraction), and running your first test.

<p align="center">
  <a href="https://github.com/A11ksa/API-Expert-Option"><img alt="AsyncIO" src="https://img.shields.io/badge/Framework-AsyncIO-informational" /></a>
  <a href="https://github.com/A11ksa/API-Expert-Option"><img alt="Playwright" src="https://img.shields.io/badge/Login-Playwright-blue" /></a>
  <a href="https://github.com/A11ksa/API-Expert-Option"><img alt="Status" src="https://img.shields.io/badge/Status-Stable-success" /></a>
  <a href="https://github.com/A11ksa/API-Expert-Option/blob/main/LICENSE"><img alt="License" src="https://img.shields.io/github/license/A11ksa/API-Expert-Option" /></a>
</p>

---

## 🔗 Quick Links
- **Repo:** https://github.com/A11ksa/API-Expert-Option
- **README:** See top-level `README.md` for API overview and examples
- **Issues:** https://github.com/A11ksa/API-Expert-Option/issues

---

## ✅ Prerequisites
- **Python 3.8+** (3.9+ recommended)
- `pip` and optionally `venv`
- Playwright browsers (we’ll install Chromium)
- Network access to `expertoption.com`

---

## ⚡ Install (recommended flow)
```bash
# 1) Clone
git clone https://github.com/A11ksa/API-Expert-Option.git
cd API-Expert-Option

# 2) Virtualenv
python -m venv venv
# Linux/macOS:
source venv/bin/activate
# Windows:
venv\Scripts\activate

# 3) Install package
pip install -U pip
pip install .

# 4) Install Playwright browser(s)
python -m playwright install chromium
