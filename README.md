# HisabMate

HisabMate is a local-first AI-assisted bahi-khata for Indian microbusinesses.
The Python backend owns validation, integer-paise calculations, SQLite
persistence, idempotency, and CSV export. The React frontend is a local
dashboard and review workflow.

## Requirements

- Python 3.10+ (Python 3.13+ is the target documented in the PRD)
- Node.js and npm
- Optional: [Ollama](https://ollama.com/) for natural-language transaction
  proposals

No Python package installation is required: the backend uses the standard
library. Frontend dependencies are declared in
[frontend/package.json](./frontend/package.json).

## Installation

From the repository root:

```powershell
Set-Location .\frontend
npm install
Set-Location ..
```

The backend creates the SQLite schema automatically on first start. It does
not seed customers or transactions.

## Ollama setup

Install Ollama separately, start its local service, and install the configured
model:

```powershell
ollama pull llama3.2:3b
```

HisabMate uses `llama3.2:3b` by default through
`http://localhost:11434`. Override the model or endpoint when needed:

```powershell
$env:OLLAMA_MODEL = "llama3.2:3b"
$env:OLLAMA_HOST = "http://localhost:11434"
```

The normal Python test suite does not require Ollama. Model output is treated
as a proposal only and is validated by Python before a user-confirmed ledger
write.

## Run locally

Start the backend from the repository root:

```powershell
$env:HISABMATE_DATABASE = "data\hisabmate.sqlite3"
python -m src.api
```

Start the frontend in a second terminal:

```powershell
Set-Location .\frontend
npm run dev
```

The frontend runs at `http://127.0.0.1:5174/` by default and calls the API at
`http://127.0.0.1:8000/api`. Set `VITE_API_BASE` before `npm run dev` to use a
different local API address.

For a different business-local timezone:

```powershell
$env:HISABMATE_TIMEZONE = "Asia/Kolkata"
```

## Current features

- Local SQLite customer records and deterministic outstanding balances.
- Credit and payment transactions stored as integer paise.
- Rupee/paise input validation with exact two-decimal handling.
- Append-only corrections with audit references.
- Persistent idempotency for confirmed transaction submissions.
- Local Ollama transaction proposals with strict response validation.
- Explicit confirmation before ledger writes.
- Customer-specific ledgers filtered by customer ID.
- Daily Hisab filtered by business date, customer, transaction type, and search
  text.
- Transaction-history CSV export using the active filters.
- Loading, empty, validation, offline, and API-error states in the frontend.

## Tests and build

Run the Python suite from the repository root:

```powershell
python -m unittest discover -s tests -v
```

Compile Python sources:

```powershell
python -m compileall -q src tests
```

Build the frontend:

```powershell
Set-Location .\frontend
npm run build
```

Check patch whitespace:

```powershell
Set-Location ..
git diff --check
```

## CSV export

The transaction-history and Daily Hisab pages export the currently selected
date, customer, transaction-type, and search filters through:

```text
GET /api/transactions.csv
```

The CSV contains transaction date, customer, transaction type, decimal rupee
amount, remarks, and transaction ID. Monetary calculations remain integer
paise internally. The current schema has no remarks/description column, so
`remarks` is exported blank rather than guessed. Text fields are escaped when
they begin with spreadsheet formula characters.

## Known limitations

- Contact details and opening balances are not represented in the current
  SQLite schema.
- Free-text transaction remarks are not stored, so search covers customer
  names and controlled transaction labels only.
- Payment reminders, CSV customization, bank integrations, and multi-user
  accounts are outside this release.
- No frontend unit/E2E test framework is configured; browser workflows have
  been manually exercised against disposable local services.
- Ollama must already be installed and running for live interpretation.
