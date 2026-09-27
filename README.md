# Nirikshan

**AI-Powered MPLADS Risk Intelligence & Investigation Platform**
Team Nirikshan — Smart India Hackathon 2026 · Problem Statement **SIH26102** (MoSPI)

Nirikshan scans MPLADS (Members of Parliament Local Area Development Scheme) work and transaction data, scores every work for investigation priority, and shows an officer *exactly why* a work was flagged — using transparent rules, peer comparison, and machine-learning anomaly detection. It does not accuse anyone of fraud; it prioritises cases and hands officers the evidence to decide.

---

## The Problem

- MoSPI's **eSAKSHI** portal is purely a system of record — it tracks fund flow and shows dashboards, but does no analysis.
- **CAG audits** are manual, slow, and only cover a small sample of works.
- No purpose-built, deployed solution for MPLADS anomaly detection currently exists.

## What Nirikshan Does

```
MPLADS Data
     ↓
Data Cleaning & Validation
     ↓
Work + Transaction Records
     ↓
┌───────────────────────────┐
│    NIRIKSHAN ANALYTICS     │
├───────────────────────────┤
│  Rule Engine                │
│  Peer Benchmarking          │
│  Isolation Forest (ML)      │
└───────────────────────────┘
     ↓
Composite Risk Score → Risk Band
     ↓
Explainable Evidence
     ↓
Officer Investigation
(Review / Request Documents / Escalate / Close)
```

## Features

### 1. Rule Engine (transparent, explainable)
Four predefined checks on every work's financial data — each one traceable to "this triggered because X exceeded Y":

| Rule | Checks | Threshold |
|------|--------|-----------|
| R001 | Transaction concentration | 50% |
| R002 | Vendor concentration | 60% |
| R003 | Transaction fragmentation | 20 transactions |
| R004 | Large single transaction | ₹10 lakh |

### 2. Peer Benchmarking
Compares each work's expenditure against thousands of comparable MPLADS works — median, amount ratio, percentile rank — to surface statistical outliers.

### 3. Isolation Forest (ML anomaly detection)
Unsupervised model trained on seven combined features (total disbursed, transaction count, transaction concentration, unique vendor count, primary vendor share, amount ratio to peer median, percentile rank) to catch unusual *combinations* of factors no single rule was written to detect.

### 4. Composite Risk Score
Rule Score + Peer Benchmark + Isolation Forest → a single 0–100 investigation-priority score and risk band (e.g. Critical, High, Medium, Low). **This is a priority score, not a fraud verdict.**

### 5. Evidence & Traceability
- Financial, vendor, and transaction-pattern signal panels
- Full transaction history with source-row references, so every result traces back to the underlying data

### 6. Officer Workspace (human-in-the-loop)
AI detects → AI explains → human investigates → human decides. Officers log a name/comment and choose: **Reviewed · Request Documents · Escalate · Close Investigation** — all recorded as an auditable Investigation Activity log.

### 7. Honest gaps, stated openly
Delay Prediction is intentionally marked **Unavailable** — the current dataset lacks sufficient historical completion-outcome data to train a responsible supervised model, so Nirikshan reports this rather than fabricating a guess.

## Tech Stack

- **Backend / ML:** Python, scikit-learn (Isolation Forest)
- **App layer:** Node.js
- **Database:** PostgreSQL
- **Tooling:** VS Code + GitHub Copilot (structured prompt sequencing for rapid prototyping)
- **Docs:** Generated programmatically via the `docx` Node.js library, verified with LibreOffice

## Data

Built on the real MPLADS dataset (State, MP name, Constituency, Allocated Amount) as the backbone, with synthetic augmentation for missing work-level fields not present in the source data.

## Project Status

- Working prototype with all features above implemented
- ⚠️ Known formatting issue: some decimal ratios (e.g. `0.12`, `0.60`) render with a ₹ symbol instead of as percentages/multiples — fix pending before demo
- ⚠️ Isolation Forest training/scoring needs a final end-to-end confirmation pass (not just implied in the UI)

## Documentation

- `SIH26102_MPLADS_Solution_Design.md` — full 36-section solution design
- 7-page feature explainer (Word doc) — for judges and teammates
- 6-slide SIH presentation deck

## Team

**Team Nirikshan** — 6 members, Smart India Hackathon 2026, Problem Statement SIH26102 (MoSPI).

---

*Nirikshan does not make fraud determinations. It prioritises cases and provides explainable evidence so that authorised officers can make informed decisions.*
