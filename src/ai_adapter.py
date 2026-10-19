"""Safe adapter for extracting transaction proposals from local Ollama."""

from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Callable
from urllib import error, request
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.ledger import ValidationError, amount_to_paise


class AIAdapterError(Exception):
    """Base class for local AI adapter failures."""


class OllamaUnavailableError(AIAdapterError):
    """Raised when Ollama cannot be reached or reports an unavailable model."""


class OllamaTimeoutError(AIAdapterError):
    """Raised when Ollama does not respond before the configured timeout."""


class MalformedModelResponseError(AIAdapterError):
    """Raised when Ollama returns invalid or unsafe structured output."""


@dataclass(frozen=True)
class TransactionProposal:
    """A validated proposal; it is not a ledger transaction."""

    intent: str | None
    customer_name: str | None
    amount_paise: int | None
    transaction_date: str | None
    missing_information: tuple[str, ...]
    ambiguous: bool
    clarification_required: bool
    confirmation_required: bool = True


_INTENTS = frozenset(("credit", "payment"))
_DEFAULT_ENDPOINT = "http://localhost:11434"
_DEFAULT_MODEL = "llama3.2:3b"
_Urlopen = Callable[..., Any]


class OllamaAdapter:
    """Extract proposals from Ollama without accessing the ledger."""

    def __init__(
        self,
        model_name: str | None = None,
        endpoint: str | None = None,
        timeout: float = 15.0,
        urlopen: _Urlopen = request.urlopen,
        timezone_name: str | None = None,
        reference_date: date | None = None,
    ) -> None:
        self.model_name = model_name or os.getenv("OLLAMA_MODEL", _DEFAULT_MODEL)
        self.endpoint = (endpoint or os.getenv("OLLAMA_HOST", _DEFAULT_ENDPOINT)).rstrip(
            "/"
        )
        self.timeout = timeout
        self._urlopen = urlopen
        self.timezone_name = timezone_name or os.getenv(
            "HISABMATE_TIMEZONE", "Asia/Kolkata"
        )
        self.reference_date = reference_date

    def extract_proposal(self, message: str) -> TransactionProposal:
        if not isinstance(message, str) or not message.strip():
            raise MalformedModelResponseError("Message must be a non-empty string")

        payload = json.dumps(
            {
                "model": self.model_name,
                "prompt": self._prompt(message),
                "stream": False,
                "format": "json",
                "options": {"temperature": 0},
            }
        ).encode("utf-8")
        http_request = request.Request(
            f"{self.endpoint}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with self._urlopen(http_request, timeout=self.timeout) as response:
                response_body = response.read()
        except (TimeoutError, socket.timeout) as exc:
            raise OllamaTimeoutError("Timed out while contacting Ollama") from exc
        except error.HTTPError as exc:
            if exc.code in (404, 503):
                raise OllamaUnavailableError(
                    "Ollama model or service is unavailable"
                ) from exc
            raise OllamaUnavailableError("Ollama returned an HTTP error") from exc
        except (error.URLError, ConnectionError, OSError) as exc:
            raise OllamaUnavailableError("Ollama is unavailable") from exc

        return self._parse_response(response_body, message)

    @staticmethod
    def _prompt(message: str) -> str:
        return f"""
Extract a bookkeeping transaction proposal from this user message:
{message}

Return JSON with exactly these fields:
{{
  "intent": "credit" or "payment" or null,
  "customer_name": string or null,
  "amount_text": only the numeric rupee/paise amount, such as "500" or "250.50", or null,
  "date_text": an explicitly stated ISO date or relative date word, or null,
  "missing_information": array of strings,
  "ambiguous": boolean
}}

Do not infer or invent a customer, amount, intent, balance, or transaction detail.
Do not calculate paise or outstanding balances. Preserve the amount exactly as stated.
Do not include words such as "rupaye", "rupees", or "paise" in amount_text.
Preserve explicitly named customers in customer_name.
Mark ambiguous true when clarification is needed.

Example:
Input: Ramesh ne 500 rupaye diye
Output: {{"intent":"payment","customer_name":"Ramesh","amount_text":"500","date_text":null,"missing_information":[],"ambiguous":false}}
""".strip()

    def _parse_response(
        self, response_body: bytes, source_message: str
    ) -> TransactionProposal:
        try:
            envelope = json.loads(response_body.decode("utf-8"))
            model_output = envelope["response"]
            data = json.loads(model_output) if isinstance(model_output, str) else model_output
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise MalformedModelResponseError(
                "Ollama returned malformed structured output"
            ) from exc

        if not isinstance(data, dict):
            raise MalformedModelResponseError("Model output must be a JSON object")
        required = {
            "intent",
            "customer_name",
            "amount_text",
            "missing_information",
            "ambiguous",
        }
        allowed = required | {"date_text"}
        if not required.issubset(data) or not set(data).issubset(allowed):
            raise MalformedModelResponseError("Model output has an invalid schema")

        intent = data["intent"]
        customer_name = data["customer_name"]
        amount_text = data["amount_text"]
        date_text = data.get("date_text")
        missing = data["missing_information"]
        ambiguous = data["ambiguous"]
        if intent is not None and (
            not isinstance(intent, str) or intent not in _INTENTS
        ):
            raise MalformedModelResponseError("Model returned an invalid transaction intent")
        if customer_name is not None and (
            not isinstance(customer_name, str) or not customer_name.strip()
        ):
            raise MalformedModelResponseError("Model returned an invalid customer name")
        if amount_text is not None and (
            not isinstance(amount_text, str) or not amount_text.strip()
        ):
            raise MalformedModelResponseError("Model returned an invalid amount")
        if date_text is not None and (
            not isinstance(date_text, str) or not date_text.strip()
        ):
            raise MalformedModelResponseError("Model returned an invalid date")
        if not isinstance(missing, list) or not all(
            isinstance(item, str) and item.strip() for item in missing
        ):
            raise MalformedModelResponseError("Model returned invalid missing information")
        if not isinstance(ambiguous, bool):
            raise MalformedModelResponseError("Model returned an invalid ambiguity flag")

        amount_paise = None
        if amount_text is not None:
            try:
                amount_paise = amount_to_paise(amount_text)
            except ValidationError as exc:
                raise MalformedModelResponseError(
                    "Model returned an invalid or imprecise amount"
                ) from exc

        missing_information = list(dict.fromkeys(missing))
        if customer_name is not None and customer_name.casefold() not in source_message.casefold():
            customer_name = None
            ambiguous = True
            if "customer_name" not in missing_information:
                missing_information.append("customer_name")
        if intent is None and "intent" not in missing_information:
            missing_information.append("intent")
        if customer_name is None and "customer_name" not in missing_information:
            missing_information.append("customer_name")
        if amount_paise is None and "amount" not in missing_information:
            missing_information.append("amount")
        transaction_date = None
        if date_text is not None:
            transaction_date, date_is_ambiguous = _resolve_transaction_date(
                date_text,
                timezone_name=self.timezone_name,
                reference_date=self.reference_date,
            )
            if date_is_ambiguous:
                ambiguous = True
                if "date" not in missing_information:
                    missing_information.append("date")
        clarification_required = ambiguous or bool(missing_information)

        return TransactionProposal(
            intent=intent,
            customer_name=customer_name.strip() if customer_name else None,
            amount_paise=amount_paise,
            transaction_date=transaction_date,
            missing_information=tuple(missing_information),
            ambiguous=ambiguous,
            clarification_required=clarification_required,
        )


def _resolve_transaction_date(
    date_text: str,
    *,
    timezone_name: str,
    reference_date: date | None,
) -> tuple[str | None, bool]:
    normalized = date_text.strip().lower()
    try:
        local_date = reference_date or datetime.now(ZoneInfo(timezone_name)).date()
    except ZoneInfoNotFoundError as exc:
        raise MalformedModelResponseError("Unknown local timezone") from exc

    try:
        return date.fromisoformat(normalized).isoformat(), False
    except ValueError:
        pass
    if normalized in ("today", "aaj"):
        return local_date.isoformat(), False
    if normalized == "yesterday":
        return (local_date - timedelta(days=1)).isoformat(), False
    if normalized == "tomorrow":
        return (local_date + timedelta(days=1)).isoformat(), False
    if normalized in ("kal", "parson"):
        return None, True
    raise MalformedModelResponseError("Model returned an unsupported date")
