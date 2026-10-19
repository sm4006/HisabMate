# HisabMate — Product Requirements Document

## 1. Objective

Build a local-first AI bookkeeping application for Indian microbusinesses to record customer credit and payments using natural language in English and Hinglish.

## 2. Target Users

Kirana stores, local retailers, and small service businesses.

## 3. MVP Features

- Create and manage customers.
- Record credit sales and customer payments.
- Calculate outstanding balances deterministically.
- Maintain transaction history and support corrections.
- Display customer-wise outstanding balances.
- Export ledger records to CSV.
- Later: use a local Ollama model to extract transactions from natural-language input.

## 4. Technical Stack

- Python 3.13+
- SQLite
- Ollama with Gemma 3 4B
- Streamlit for the later UI
- Git for version control

## 5. Financial Integrity

- Store monetary values as integer paise.
- Never use floating-point arithmetic for financial calculations.
- Never allow the LLM to calculate or directly modify balances.
- Validate transactions before committing them.
- Preserve an auditable history of corrections.

## 6. Privacy

- Ledger data remains on the local machine.
- No cloud AI API is required.
- Model downloads may require internet access; normal inference should work offline.

## 7. MVP Exclusions

No bank integration, automatic UPI verification, automatic WhatsApp sending, multi-user accounts, or voice transcription in the initial release.

## 8. Acceptance Criteria

- Customers can be created and retrieved.
- Credit and payment entries update balances correctly.
- Invalid transactions are rejected.
- Corrections preserve transaction history.
- CSV exports contain accurate ledger data.
- Automated tests cover normal and failure scenarios.