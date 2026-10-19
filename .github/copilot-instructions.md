# HisabMate Copilot Instructions

- Keep financial calculations deterministic.
- User-facing amounts support rupees and paise; store and calculate all monetary values internally as integer paise.
- Never use floats for financial arithmetic.
- Never allow the LLM to write directly to the database.
- Validate all model output before use.
- Keep ledger data local.
- Add tests for every new core behaviour.
- Do not add features outside the current task.
