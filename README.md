# FinVision — Understand Before You Invest
Explainable Structured-Product & Derivatives Suitability Platform for Wealth Management

[![FastAPI](https://img.shields.io/badge/FastAPI-0.111.0-009688.svg?style=flat&logo=fastapi)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![Status](https://img.shields.io/badge/Status-Production%20Ready-success.svg)](#)

---

## 💡 Core Philosophy

> **"Deterministic financial engines calculate. A transparent rule engine decides. The LLM only orchestrates, translates, and explains. It NEVER invents numbers."**

**FinVision** is a purpose-built suitability and explainability platform that helps Relationship Managers (RMs) and retail/HNW customers understand complex structured products (Equity-Linked Notes, Dual Currency Deposits, Capital Protected Notes) *before* committing capital.

FinVision does **NOT** predict stock markets or recommend speculative trades. It guarantees mathematical determinism, transparent regulatory auditability, and clear investor comprehension.

---

## 🌟 Key Features

### 1. ⚖️ Deterministic Financial Engines
- **Payoff & Barrier Simulation**: Exact analytical payoff calculation across full spot range, barrier-breach simulations, and terminal loss estimation.
- **Rupee Impact Engine**: Translates percentages into tangible ₹ figures (Best case, Base case, Capital-at-risk, Tail risk loss at ₹10L/₹50L/₹1Cr ticket sizes).
- **Historical Replay & Historical Twin**: Evaluates proposed notes against historical rolling windows (including 2008 GFC, 2020 COVID crash) and calculates mathematical similarity distance to current market volatility regimes.
- **Stress Ladder & Regime Scenarios**: Instantaneous and macroeconomic shocks (Inflation surge, Rate cuts, Currency depreciation) with automatic suitability threshold evaluation at each shock level.
- **Portfolio Impact Analyzer**: Analyzes pre- vs post-allocation asset concentration, sector tilt, and weighted downside risk.

### 2. 🛡️ Suitability & Auto-Repair Engine
- Multi-dimensional rule engine evaluating:
  - **Risk Appetite alignment** (Conservative / Moderate / Aggressive)
  - **Loss Tolerance vs Worst-Case/Tail Risk**
  - **Investment Horizon vs Product Tenor**
  - **Underlying Asset Concentration Limit**
  - **Liquidity & Lock-in Constraints**
- **Deterministic Auto-Repair**: Suggests parameter modifications (e.g., lower barrier, increase tenor, reduce ticket size) to convert an `UNSUITABLE` or `REVIEW_REQUIRED` product into a `SUITABLE` one.

### 3. 🧠 Teach-Back Verification
- Generates 3 deterministic, multiple-choice comprehension questions verified strictly by calculation engines.
- Assesses investor understanding of downside scenarios, barrier breaches, and capital lock-ins before trade execution.

### 4. 📝 Audit Trail & RM Copilot
- **Complete SQLite Audit Log**: Every calculation, input payload, triggered rule, and generated explanation is fingerprinted and timestamped.
- **RM Note Generator**: Formats compliant advisory memorandums citing specific risk numbers and regulatory rationale.
- **Client PDF Report**: Downloads high-fidelity, client-ready suitability summary sheets.
- **Multilingual Explanations**: Instant client explanations in English, Hindi, and Marathi.

---

## 🚀 Quick Start Guide

### 1. Prerequisites
- Python 3.10+ (Python 3.11 recommended)
- `pip` / `virtualenv`

### 2. Installation & Setup

```bash
# Clone or navigate to the repository
cd structuraai

# Create virtual environment (optional but recommended)
python -m venv .venv
# On Windows PowerShell:
.venv\Scripts\Activate.ps1
# On Linux/macOS:
source .venv/bin/activate

# Install backend dependencies
pip install -r backend/requirements.txt
```

### 3. Running the Application

```bash
# Start backend server from structuraai/backend directory
cd backend
python -m uvicorn app.main:app --reload --port 8000
```

Open your browser and navigate to:
👉 **[http://localhost:8000](http://localhost:8000)**

---

## 👥 Demo Logins & Persona Roles

| Role | Username | Password | Purpose |
|---|---|---|---|
| **Relationship Manager** | `rm_user` | `rm123` | Full access: Product Studio, Assessment, Stress Ladder, Auto-Repair, RM Notes, Audit Trail |
| **Customer** | `cust_user` | `cust123` | Customer view: Rupee Impact, Simple Breakdown, Historical Twin, Teach-Back Check, PDF Download |
| **Auditor / Compliance** | `audit_user` | `audit123` | Read-only compliance audit trail, regulatory reports, and mathematical verification logs |

---

## 📁 Architecture & Directory Structure

```
structuraai/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI application, routing, auth & static mount
│   │   ├── schemas.py           # Pydantic data schemas & validators
│   │   ├── auth.py              # Role-based JWT/token authentication
│   │   ├── alerts.py            # Deterministic risk alert engine
│   │   ├── audit.py             # SQLite immutable audit storage
│   │   ├── engines/             # Pure deterministic financial math
│   │   │   ├── payoff.py        # Exact payoff curves & formulas
│   │   │   ├── suitability.py   # Multi-factor rule evaluator
│   │   │   ├── portfolio.py     # Portfolio concentration & impact
│   │   │   ├── twin.py          # Historical rolling window similarity
│   │   │   ├── stress.py        # Stress ladder & macroeconomic regimes
│   │   │   ├── teachback.py     # Deterministic comprehension verification
│   │   │   ├── historical.py    # Rolling replay engine
│   │   │   ├── monte_carlo.py   # Stochastic tail risk simulation
│   │   │   ├── breaking_point.py# Vulnerability threshold scanner
│   │   │   └── repair.py        # Constraint-satisfaction auto-repair
│   │   ├── extraction/          # Term-sheet text extraction
│   │   ├── rag/                 # Regulatory & product knowledge retrieval
│   │   └── services/            # Explanation generation & PDF reporting
│   └── requirements.txt
├── frontend/
│   └── index.html               # Premium interactive Single-Page Application (Plotly.js + Tailwind)
├── data/
│   ├── samples/                 # Sample customers, products, and portfolios
│   └── market/                  # Historical price series (NIFTY50, USDINR, etc.)
└── scripts/                     # Market data fetchers and test utilities
```

---

## 🛡️ Regulatory Compliance & Grounding

- **SEBI / RBI Aligned**: Tailored to structured product disclosure guidelines.
- **Zero Hallucination Guarantee**: All numbers displayed in explanations or RM memos must directly reconcile with engine outputs.
- **Complete Replayability**: Any past assessment can be audited and mathematically re-executed from the immutable SQLite audit record.
