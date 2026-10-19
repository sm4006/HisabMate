# HisabMate dashboard

This is the React dashboard layer for HisabMate. It reads and writes through the
local Python API, which delegates financial operations to the deterministic ledger.

## Run locally

Start the backend from the repository root first:

```powershell
$env:HISABMATE_DATABASE = "data\hisabmate.sqlite3"
python -m src.api
```

Then, in a second terminal:

```powershell
Set-Location .\frontend
npm install
npm run dev
```

Vite serves the frontend on port 5174 by default. The frontend calls
`http://127.0.0.1:8000/api` by default. To use another local
API address, set `VITE_API_BASE` before starting Vite.

The backend creates the SQLite schema on first start but does not seed sample
customers or transactions. The dashboard therefore shows empty, zero-valued
ledger state until real records are added.
