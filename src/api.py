"""Small local HTTP boundary for the HisabMate frontend."""

from __future__ import annotations

import json
import csv
import io
import os
import sqlite3
from datetime import date, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.ai_adapter import AIAdapterError, OllamaAdapter
from src.ledger import (
    CustomerNotFoundError,
    IdempotencyConflictError,
    Ledger,
    LedgerError,
    OverpaymentError,
    Transaction,
    ValidationError,
    format_paise,
)


class ApiError(Exception):
    def __init__(self, message: str, status: int = HTTPStatus.BAD_REQUEST) -> None:
        super().__init__(message)
        self.status = status


def _validate_date(value: object) -> str:
    if value is None:
        return _business_today()
    if not isinstance(value, str):
        raise ValidationError("transaction_date must be an ISO date")
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValidationError("transaction_date must be an ISO date") from exc


class LedgerService:
    def __init__(self, ledger: Ledger, adapter: OllamaAdapter | None = None) -> None:
        self.ledger = ledger
        self.adapter = adapter or OllamaAdapter()

    def customers(self) -> list[dict[str, Any]]:
        result = []
        for customer in self.ledger.list_customers():
            balance = self.ledger.get_balance(customer.id)
            result.append(
                {
                    "id": customer.id,
                    "name": customer.name,
                    "balance_paise": balance,
                    "balance": format_paise(balance),
                }
            )
        return result

    def create_customer(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = payload.get("name")
        customer = self.ledger.create_customer(name)
        return {"id": customer.id, "name": customer.name, "balance_paise": 0, "balance": "₹0.00"}

    def transactions(
        self,
        customer_id: int | None = None,
        transaction_date: str | None = None,
        transaction_type: str | None = None,
    ) -> list[dict[str, Any]]:
        customers = {customer.id: customer.name for customer in self.ledger.list_customers()}
        result = self.ledger.list_transactions(customer_id)
        if transaction_date is not None:
            result = [item for item in result if item.created_at[:10] == transaction_date]
        if transaction_type is not None:
            result = [item for item in result if item.transaction_type == transaction_type]
        return [self._transaction_json(item, customers) for item in result]

    def transaction_history(
        self,
        customer_id: int | None = None,
        transaction_date: str | None = None,
        transaction_type: str | None = None,
        search: str | None = None,
    ) -> dict[str, Any]:
        transactions = self.transactions(customer_id, transaction_date, transaction_type)
        if search:
            needle = search.casefold().strip()
            transactions = [
                item for item in transactions
                if needle in str(item["customer_name"] or "").casefold()
                or needle in self._transaction_label(item["transaction_type"]).casefold()
            ]
        received = sum(
            item["amount_paise"]
            for item in transactions
            if item["transaction_type"] == "payment"
        )
        credit = sum(
            item["amount_paise"]
            for item in transactions
            if item["transaction_type"] == "credit"
        )
        return {
            "date": transaction_date,
            "transaction_count": len(transactions),
            "received_paise": received,
            "received": format_paise(received),
            "credit_paise": credit,
            "credit": format_paise(credit),
            "transactions": transactions,
        }

    @staticmethod
    def _transaction_label(transaction_type: str) -> str:
        return "Payment received" if transaction_type == "payment" else "Credit given"

    def export_csv(
        self,
        customer_id: int | None = None,
        transaction_date: str | None = None,
        transaction_type: str | None = None,
        search: str | None = None,
    ) -> str:
        transactions = self.transaction_history(
            customer_id, transaction_date, transaction_type, search
        )["transactions"]
        output = io.StringIO(newline="")
        writer = csv.writer(output, lineterminator="\r\n")
        writer.writerow(
            ["transaction_date", "customer", "transaction_type", "amount_rupees",
             "remarks", "transaction_id"]
        )
        for item in transactions:
            writer.writerow(
                [
                    _safe_csv_text(item["created_at"]),
                    _safe_csv_text(item["customer_name"] or ""),
                    _safe_csv_text(self._transaction_label(item["transaction_type"])),
                    f"{item['amount_paise'] // 100}.{item['amount_paise'] % 100:02d}",
                    "",
                    item["id"],
                ]
            )
        return output.getvalue()

    def dashboard(self) -> dict[str, Any]:
        transactions = self.transactions()
        today = _business_today()
        today_transactions = [item for item in transactions if item["created_at"].startswith(today)]
        received = sum(
            item["amount_paise"] for item in today_transactions if item["transaction_type"] == "payment"
        )
        credit = sum(
            item["amount_paise"] for item in today_transactions if item["transaction_type"] == "credit"
        )
        outstanding = sum(item["balance_paise"] for item in self.customers())
        return {
            "customer_count": len(self.customers()),
            "outstanding_paise": outstanding,
            "outstanding": format_paise(outstanding),
            "received_today_paise": received,
            "received_today": format_paise(received),
            "credit_today_paise": credit,
            "credit_today": format_paise(credit),
            "transactions_today": len(today_transactions),
            "transactions": transactions[-10:],
        }

    def interpret(self, message: str) -> dict[str, Any]:
        try:
            proposal = self.adapter.extract_proposal(message)
        except AIAdapterError as exc:
            raise ApiError(str(exc), HTTPStatus.SERVICE_UNAVAILABLE) from exc
        return {
            "intent": proposal.intent,
            "customer_name": proposal.customer_name,
            "amount_paise": proposal.amount_paise,
            "transaction_date": proposal.transaction_date,
            "missing_information": list(proposal.missing_information),
            "ambiguous": proposal.ambiguous,
            "clarification_required": proposal.clarification_required,
            "confirmation_required": proposal.confirmation_required,
        }

    def save_transaction(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("confirmed") is not True:
            raise ApiError("Explicit confirmation is required")
        proposal_id = payload.get("proposal_id")
        if not isinstance(proposal_id, str) or not proposal_id.strip():
            raise ApiError("proposal_id is required")
        intent = payload.get("intent")
        customer_id = payload.get("customer_id")
        amount_paise = payload.get("amount_paise")
        missing = payload.get("missing_information", [])
        if intent not in ("credit", "payment"):
            raise ApiError("A supported transaction intent is required")
        if not isinstance(customer_id, int) or isinstance(customer_id, bool):
            raise ApiError("A customer must be selected")
        if not isinstance(amount_paise, int) or isinstance(amount_paise, bool) or amount_paise <= 0:
            raise ApiError("Amount must be a positive integer number of paise")
        if missing or payload.get("ambiguous") is True:
            raise ApiError("Clarification is required before saving")
        try:
            transaction_date = _validate_date(payload.get("transaction_date"))
        except ValidationError as exc:
            raise ApiError(str(exc)) from exc

        try:
            transaction = self.ledger.record_idempotently(
                proposal_id,
                intent,
                customer_id,
                amount_paise,
                transaction_date,
            )
        except CustomerNotFoundError as exc:
            raise ApiError(str(exc), HTTPStatus.NOT_FOUND) from exc
        except (ValidationError, OverpaymentError) as exc:
            raise ApiError(str(exc), HTTPStatus.UNPROCESSABLE_ENTITY) from exc
        except IdempotencyConflictError as exc:
            raise ApiError(str(exc), HTTPStatus.CONFLICT) from exc
        return self._transaction_json(transaction, {item["id"]: item["name"] for item in self.customers()})

    @staticmethod
    def _transaction_json(transaction: Transaction, customers: dict[int, str]) -> dict[str, Any]:
        return {
            "id": transaction.id,
            "customer_id": transaction.customer_id,
            "customer_name": customers.get(transaction.customer_id),
            "transaction_type": transaction.transaction_type,
            "amount_paise": transaction.amount_paise,
            "amount": format_paise(transaction.amount_paise),
            "created_at": transaction.created_at,
            "correction_of": transaction.correction_of,
        }


class ApiHandler(BaseHTTPRequestHandler):
    service: LedgerService

    def _send(self, status: int, body: dict[str, Any]) -> None:
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        origin = self.headers.get("Origin")
        if origin in ("http://localhost:5174", "http://127.0.0.1:5174"):
            self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_text(
        self, status: int, body: str, content_type: str, disposition: str | None = None
    ) -> None:
        encoded = body.encode("utf-8-sig")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        if disposition:
            self.send_header("Content-Disposition", disposition)
        origin = self.headers.get("Origin")
        if origin in ("http://localhost:5174", "http://127.0.0.1:5174"):
            self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_OPTIONS(self) -> None:
        self._send(HTTPStatus.NO_CONTENT, {})

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/api/health":
                self._send(HTTPStatus.OK, {"ok": True})
            elif parsed.path == "/api/customers":
                self._send(HTTPStatus.OK, {"customers": self.service.customers()})
            elif parsed.path == "/api/transactions":
                customer_id = _customer_id_from_query(parsed.query)
                parameters = parse_qs(parsed.query)
                transaction_date = _date_from_query(parameters)
                transaction_type = _transaction_type_from_query(parameters)
                search = _search_from_query(parameters)
                self._send(HTTPStatus.OK, self.service.transaction_history(
                    customer_id, transaction_date, transaction_type, search
                ))
            elif parsed.path == "/api/transactions.csv":
                customer_id = _customer_id_from_query(parsed.query)
                parameters = parse_qs(parsed.query)
                transaction_date = _date_from_query(parameters)
                transaction_type = _transaction_type_from_query(parameters)
                search = _search_from_query(parameters)
                self._send_text(
                    HTTPStatus.OK,
                    self.service.export_csv(
                        customer_id, transaction_date, transaction_type, search
                    ),
                    "text/csv; charset=utf-8",
                    "attachment; filename=\"hisabmate-transactions.csv\"",
                )
            elif parsed.path == "/api/dashboard":
                self._send(HTTPStatus.OK, self.service.dashboard())
            else:
                self._send(HTTPStatus.NOT_FOUND, {"error": "Not found"})
        except ApiError as exc:
            self._send(exc.status, {"error": str(exc)})
        except CustomerNotFoundError as exc:
            self._send(HTTPStatus.NOT_FOUND, {"error": str(exc)})
        except (sqlite3.Error, LedgerError) as exc:
            self._send(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

    def do_POST(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ApiError("JSON body must be an object")
            if self.path == "/api/customers":
                result = self.service.create_customer(payload)
            elif self.path == "/api/interpret":
                result = self.service.interpret(payload.get("message"))
            elif self.path == "/api/transactions":
                result = self.service.save_transaction(payload)
            else:
                self._send(HTTPStatus.NOT_FOUND, {"error": "Not found"})
                return
            self._send(HTTPStatus.OK, result)
        except ApiError as exc:
            self._send(exc.status, {"error": str(exc)})
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            self._send(HTTPStatus.BAD_REQUEST, {"error": "Invalid JSON request"})
        except (sqlite3.Error, LedgerError) as exc:
            self._send(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

    def log_message(self, _format: str, *_args: object) -> None:
        return


def _customer_id_from_query(query: str) -> int | None:
    values = parse_qs(query).get("customer_id")
    if not values:
        return None
    value = values[0]
    try:
        customer_id = int(value)
    except ValueError as exc:
        raise ApiError("customer_id must be an integer") from exc
    if customer_id <= 0:
        raise ApiError("customer_id must be a positive integer")
    return customer_id


def _business_today() -> str:
    timezone_name = os.getenv("HISABMATE_TIMEZONE", "Asia/Kolkata")
    try:
        return datetime.now(ZoneInfo(timezone_name)).date().isoformat()
    except ZoneInfoNotFoundError as exc:
        raise ApiError("Unknown business timezone") from exc


def _date_from_query(parameters: dict[str, list[str]]) -> str | None:
    values = parameters.get("date")
    if not values or not values[0]:
        return None
    try:
        return date.fromisoformat(values[0]).isoformat()
    except ValueError as exc:
        raise ApiError("date must be an ISO date") from exc


def _transaction_type_from_query(parameters: dict[str, list[str]]) -> str | None:
    values = parameters.get("transaction_type")
    if not values or not values[0]:
        return None
    if values[0] not in ("credit", "payment"):
        raise ApiError("transaction_type must be credit or payment")
    return values[0]


def _search_from_query(parameters: dict[str, list[str]]) -> str | None:
    values = parameters.get("search")
    if not values:
        return None
    search = values[0].strip()
    return search or None


def _safe_csv_text(value: str) -> str:
    if value.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    path = Path(os.getenv("HISABMATE_DATABASE", "data/hisabmate.sqlite3"))
    path.parent.mkdir(parents=True, exist_ok=True)
    ledger = Ledger(path)
    ApiHandler.service = LedgerService(ledger)
    server = HTTPServer((host, port), ApiHandler)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        ledger.close()


if __name__ == "__main__":
    serve()
