"""Deterministic, local SQLite ledger engine."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import NamedTuple


class LedgerError(Exception):
    """Base class for ledger errors."""


class ValidationError(LedgerError, ValueError):
    """Raised when input does not satisfy ledger rules."""


class CustomerNotFoundError(LedgerError):
    """Raised when a customer ID does not exist."""


class TransactionNotFoundError(LedgerError):
    """Raised when a transaction ID does not exist."""


class OverpaymentError(LedgerError):
    """Raised when a payment exceeds the outstanding balance."""


class IdempotencyConflictError(LedgerError):
    """Raised when an idempotency key is reused for different transaction data."""


class Customer(NamedTuple):
    id: int
    name: str


class Transaction(NamedTuple):
    id: int
    customer_id: int
    transaction_type: str
    amount_paise: int
    created_at: str
    correction_of: int | None


_RUPEE_AMOUNT_PATTERN = re.compile(
    r"^(?P<whole>(?:\d{1,3}(?:,\d{3})+|\d+))(?P<paise>\.\d{1,2})?$"
)


def amount_to_paise(amount: int | str) -> int:
    """Convert integer paise or a rupee string to positive integer paise.

    Integer inputs are already paise. String inputs are rupee amounts and may
    include a rupee sign, commas, and up to two decimal places.
    """
    if isinstance(amount, bool):
        raise ValidationError("Amount must be positive integer paise or rupees")
    if isinstance(amount, int):
        paise = amount
    elif isinstance(amount, str):
        normalized = amount.strip()
        if normalized.startswith("₹"):
            normalized = normalized[1:].strip()
        match = _RUPEE_AMOUNT_PATTERN.fullmatch(normalized)
        if match is None:
            raise ValidationError(
                "Rupee amount must contain digits and at most two decimal places"
            )
        whole = int(match.group("whole").replace(",", ""))
        decimal = match.group("paise")
        paise = whole * 100 + (int(decimal[1:].ljust(2, "0")) if decimal else 0)
    else:
        raise ValidationError("Amount must be positive integer paise or rupees")

    if paise <= 0:
        raise ValidationError("Amount must be positive")
    return paise


def format_paise(amount_paise: int) -> str:
    """Format positive integer paise as a user-facing rupee amount."""
    if isinstance(amount_paise, bool) or not isinstance(amount_paise, int):
        raise ValidationError("Amount must be an integer number of paise")
    if amount_paise < 0:
        raise ValidationError("Amount cannot be negative")
    rupees, paise = divmod(amount_paise, 100)
    return f"₹{rupees:,}.{paise:02d}"


class Ledger:
    """A local-first ledger whose balances are derived from immutable entries."""

    def __init__(self, database_path: str | Path) -> None:
        self._connection = sqlite3.connect(str(database_path))
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._create_schema()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> Ledger:
        return self

    def __exit__(self, _exc_type: object, _exc_value: object, _traceback: object) -> None:
        self.close()

    def create_customer(self, name: str) -> Customer:
        if not isinstance(name, str) or not name.strip():
            raise ValidationError("Customer name must be a non-empty string")

        normalized_name = name.strip()
        try:
            with self._connection:
                cursor = self._connection.execute(
                    "INSERT INTO customers (name) VALUES (?)",
                    (normalized_name,),
                )
        except sqlite3.IntegrityError as exc:
            raise ValidationError("A customer with that name already exists") from exc
        return Customer(cursor.lastrowid, normalized_name)

    def list_customers(self) -> list[Customer]:
        rows = self._connection.execute(
            "SELECT id, name FROM customers ORDER BY id"
        ).fetchall()
        return [Customer(row["id"], row["name"]) for row in rows]

    def record_credit(
        self, customer_id: int, amount: int | str, transaction_date: str | None = None
    ) -> Transaction:
        return self._record_transaction(
            customer_id, "credit", amount_to_paise(amount), transaction_date
        )

    def record_payment(
        self, customer_id: int, amount: int | str, transaction_date: str | None = None
    ) -> Transaction:
        amount_paise = amount_to_paise(amount)
        with self._connection:
            self._require_customer(customer_id)
            if amount_paise > self.get_balance(customer_id):
                raise OverpaymentError("Payment exceeds the outstanding balance")
            return self._insert_transaction(
                customer_id, "payment", amount_paise, created_at=transaction_date
            )

    def record_idempotently(
        self,
        idempotency_key: str,
        transaction_type: str,
        customer_id: int,
        amount_paise: int,
        transaction_date: str | None = None,
    ) -> Transaction:
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise ValidationError("Idempotency key must be a non-empty string")
        if transaction_type not in ("credit", "payment"):
            raise ValidationError("Unsupported transaction type")
        amount_paise = amount_to_paise(amount_paise)
        fingerprint = json.dumps(
            [transaction_type, customer_id, amount_paise, transaction_date],
            separators=(",", ":"),
        )

        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            existing = self._connection.execute(
                """
                SELECT request_fingerprint, transaction_id
                FROM transaction_idempotency
                WHERE idempotency_key = ?
                """,
                (idempotency_key.strip(),),
            ).fetchone()
            if existing is not None:
                if existing["request_fingerprint"] != fingerprint:
                    raise IdempotencyConflictError(
                        "Idempotency key was already used for different transaction data"
                    )
                row = self._connection.execute(
                    "SELECT * FROM transactions WHERE id = ?",
                    (existing["transaction_id"],),
                ).fetchone()
                if row is None:
                    raise LedgerError("Idempotency record references a missing transaction")
                return self._transaction_from_row(row)

            self._require_customer(customer_id)
            if transaction_type == "payment":
                if amount_paise > self.get_balance(customer_id):
                    raise OverpaymentError("Payment exceeds the outstanding balance")
            transaction = self._insert_transaction(
                customer_id,
                transaction_type,
                amount_paise,
                created_at=transaction_date,
            )
            self._connection.execute(
                """
                INSERT INTO transaction_idempotency
                    (idempotency_key, request_fingerprint, transaction_id)
                VALUES (?, ?, ?)
                """,
                (idempotency_key.strip(), fingerprint, transaction.id),
            )
            return transaction

    def get_balance(self, customer_id: int) -> int:
        self._require_customer(customer_id)
        row = self._connection.execute(
            """
            SELECT COALESCE(SUM(CASE WHEN transaction_type = 'credit'
                                    THEN amount_paise
                                    ELSE -amount_paise END), 0) AS balance
            FROM transactions AS t
            WHERE t.customer_id = ?
              AND NOT EXISTS (
                  SELECT 1 FROM transactions AS replacement
                  WHERE replacement.replaces_transaction_id = t.id
              )
            """,
            (customer_id,),
        ).fetchone()
        return int(row["balance"])

    def list_transactions(self, customer_id: int | None = None) -> list[Transaction]:
        query = """
            SELECT id, customer_id, transaction_type, amount_paise,
                   created_at, replaces_transaction_id
            FROM transactions
        """
        parameters: tuple[int, ...] = ()
        if customer_id is not None:
            self._require_customer(customer_id)
            query += " WHERE customer_id = ?"
            parameters = (customer_id,)
        query += " ORDER BY created_at, id"
        rows = self._connection.execute(query, parameters).fetchall()
        return [
            self._transaction_from_row(row)
            for row in rows
        ]

    def correct_transaction(
        self, transaction_id: int, corrected_amount: int | str
    ) -> Transaction:
        corrected_amount_paise = amount_to_paise(corrected_amount)
        with self._connection:
            row = self._connection.execute(
                "SELECT * FROM transactions WHERE id = ?", (transaction_id,)
            ).fetchone()
            if row is None:
                raise TransactionNotFoundError("Transaction does not exist")
            already_replaced = self._connection.execute(
                "SELECT 1 FROM transactions WHERE replaces_transaction_id = ?",
                (transaction_id,),
            ).fetchone()
            if already_replaced is not None:
                raise ValidationError("Transaction has already been corrected")

            if row["transaction_type"] == "payment":
                balance_without_original = self.get_balance(row["customer_id"]) + row[
                    "amount_paise"
                ]
                if corrected_amount_paise > balance_without_original:
                    raise OverpaymentError(
                        "Corrected payment exceeds the outstanding balance"
                    )
            else:
                balance_without_original = self.get_balance(row["customer_id"]) - row[
                    "amount_paise"
                ]
                if balance_without_original + corrected_amount_paise < 0:
                    raise ValidationError(
                        "Corrected credit cannot make the outstanding balance negative"
                    )
            return self._insert_transaction(
                row["customer_id"],
                row["transaction_type"],
                corrected_amount_paise,
                replaces_transaction_id=transaction_id,
            )

    def _record_transaction(
        self,
        customer_id: int,
        transaction_type: str,
        amount_paise: int,
        transaction_date: str | None = None,
    ) -> Transaction:
        with self._connection:
            self._require_customer(customer_id)
            return self._insert_transaction(
                customer_id, transaction_type, amount_paise, created_at=transaction_date
            )

    def _insert_transaction(
        self,
        customer_id: int,
        transaction_type: str,
        amount_paise: int,
        replaces_transaction_id: int | None = None,
        created_at: str | None = None,
    ) -> Transaction:
        cursor = self._connection.execute(
            """
            INSERT INTO transactions
                (customer_id, transaction_type, amount_paise,
                 replaces_transaction_id, created_at)
            VALUES (?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))
            """,
            (
                customer_id,
                transaction_type,
                amount_paise,
                replaces_transaction_id,
                created_at,
            ),
        )
        row = self._connection.execute(
            "SELECT * FROM transactions WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        return Transaction(
            row["id"],
            row["customer_id"],
            row["transaction_type"],
            row["amount_paise"],
            row["created_at"],
            row["replaces_transaction_id"],
        )

    def _require_customer(self, customer_id: int) -> None:
        row = self._connection.execute(
            "SELECT 1 FROM customers WHERE id = ?", (customer_id,)
        ).fetchone()
        if row is None:
            raise CustomerNotFoundError("Customer does not exist")

    @staticmethod
    def _transaction_from_row(row: sqlite3.Row) -> Transaction:
        return Transaction(
            row["id"],
            row["customer_id"],
            row["transaction_type"],
            row["amount_paise"],
            row["created_at"],
            row["replaces_transaction_id"],
        )

    def _create_schema(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            );
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL REFERENCES customers(id),
                transaction_type TEXT NOT NULL CHECK (
                    transaction_type IN ('credit', 'payment')
                ),
                amount_paise INTEGER NOT NULL CHECK (amount_paise > 0),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                replaces_transaction_id INTEGER REFERENCES transactions(id)
            );
            CREATE TABLE IF NOT EXISTS transaction_idempotency (
                idempotency_key TEXT PRIMARY KEY,
                request_fingerprint TEXT NOT NULL,
                transaction_id INTEGER NOT NULL UNIQUE
                    REFERENCES transactions(id)
            );
            """
        )
