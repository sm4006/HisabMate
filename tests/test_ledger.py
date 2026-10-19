import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path

from src.ledger import (
    CustomerNotFoundError,
    Ledger,
    OverpaymentError,
    ValidationError,
    amount_to_paise,
    format_paise,
)


class LedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self.database.close()
        self.database_path = Path(self.database.name)
        self.ledger = Ledger(self.database_path)
        self.customer = self.ledger.create_customer("Asha Kirana")

    def tearDown(self) -> None:
        self.ledger.close()
        self.database_path.unlink(missing_ok=True)

    def test_customer_creation_and_listing(self) -> None:
        self.assertEqual(self.ledger.list_customers(), [self.customer])

    def test_credit_entry_increases_balance(self) -> None:
        self.ledger.record_credit(self.customer.id, 10_000)
        self.assertEqual(self.ledger.get_balance(self.customer.id), 10_000)

    def test_rupee_amounts_are_stored_as_exact_paise(self) -> None:
        credit = self.ledger.record_credit(self.customer.id, "₹250.50")
        self.assertEqual(credit.amount_paise, 25_050)
        self.assertEqual(self.ledger.get_balance(self.customer.id), 25_050)

        second_credit = self.ledger.record_credit(self.customer.id, "1,299.99")
        self.assertEqual(second_credit.amount_paise, 129_999)
        self.assertEqual(self.ledger.get_balance(self.customer.id), 155_049)

        payment = self.ledger.record_payment(self.customer.id, "1,299.99")
        self.assertEqual(payment.amount_paise, 129_999)
        self.assertEqual(self.ledger.get_balance(self.customer.id), 25_050)

    def test_whole_rupees_and_paise_formatting(self) -> None:
        self.assertEqual(amount_to_paise("250"), 25_000)
        self.assertEqual(format_paise(129_999), "₹1,299.99")
        self.assertEqual(format_paise(25_000), "₹250.00")

    def test_partial_payment_reduces_balance(self) -> None:
        self.ledger.record_credit(self.customer.id, 10_000)
        self.ledger.record_payment(self.customer.id, 3_500)
        self.assertEqual(self.ledger.get_balance(self.customer.id), 6_500)

    def test_full_payment_clears_balance(self) -> None:
        self.ledger.record_credit(self.customer.id, 10_000)
        self.ledger.record_payment(self.customer.id, 10_000)
        self.assertEqual(self.ledger.get_balance(self.customer.id), 0)

    def test_invalid_transactions_are_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            self.ledger.record_credit(self.customer.id, 0)
        with self.assertRaises(ValidationError):
            self.ledger.record_payment(self.customer.id, 1.5)
        with self.assertRaises(CustomerNotFoundError):
            self.ledger.record_credit(999, 100)
        self.assertEqual(self.ledger.list_transactions(), [])

    def test_invalid_rupee_amounts_and_precision_are_rejected(self) -> None:
        for amount in ("0", "-1", "₹-1", "250.555", "1,29.99", "not-money"):
            with self.subTest(amount=amount):
                with self.assertRaises(ValidationError):
                    self.ledger.record_credit(self.customer.id, amount)

        for amount in (0, -1):
            with self.subTest(amount=amount):
                with self.assertRaises(ValidationError):
                    self.ledger.record_credit(self.customer.id, amount)

    def test_overpayment_is_rejected_without_saving(self) -> None:
        self.ledger.record_credit(self.customer.id, 1_000)
        with self.assertRaises(OverpaymentError):
            self.ledger.record_payment(self.customer.id, 1_001)
        self.assertEqual(self.ledger.get_balance(self.customer.id), 1_000)
        self.assertEqual(len(self.ledger.list_transactions()), 1)

    def test_overpayment_policy_is_reject_and_preserve_balance(self) -> None:
        self.ledger.record_credit(self.customer.id, "₹10.00")

        with self.assertRaisesRegex(OverpaymentError, "exceeds the outstanding balance"):
            self.ledger.record_payment(self.customer.id, "₹10.01")

        self.assertEqual(self.ledger.get_balance(self.customer.id), 1_000)
        self.assertEqual(len(self.ledger.list_transactions()), 1)

    def test_correction_preserves_history_and_updates_balance(self) -> None:
        original = self.ledger.record_credit(self.customer.id, 1_000)
        corrected = self.ledger.correct_transaction(original.id, 1_500)

        self.assertEqual(self.ledger.get_balance(self.customer.id), 1_500)
        history = self.ledger.list_transactions()
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0].amount_paise, 1_000)
        self.assertEqual(history[1].id, corrected.id)
        self.assertEqual(history[1].correction_of, original.id)

    def test_correction_cannot_create_negative_balance(self) -> None:
        original = self.ledger.record_credit(self.customer.id, 1_000)
        self.ledger.record_payment(self.customer.id, 600)

        with self.assertRaises(ValidationError):
            self.ledger.correct_transaction(original.id, 500)

        self.assertEqual(self.ledger.get_balance(self.customer.id), 400)
        self.assertEqual(len(self.ledger.list_transactions()), 2)

    def test_database_transaction_rolls_back_failed_operation(self) -> None:
        with self.assertRaises(OverpaymentError):
            self.ledger.record_payment(self.customer.id, 1)
        connection = sqlite3.connect(self.database_path)
        count = connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        connection.close()
        self.assertEqual(count, 0)

    def test_transactions_and_balances_persist_after_backend_restart(self) -> None:
        self.ledger.record_credit(self.customer.id, "₹250.50", date.today().isoformat())
        self.ledger.close()

        restarted = Ledger(self.database_path)
        try:
            self.assertEqual(restarted.get_balance(self.customer.id), 25_050)
            self.assertEqual(len(restarted.list_transactions(self.customer.id)), 1)
        finally:
            restarted.close()

    def test_customer_records_are_isolated(self) -> None:
        other = self.ledger.create_customer("Bina Kirana")
        self.ledger.record_credit(self.customer.id, 1_000)
        self.ledger.record_credit(other.id, 2_000)
        self.ledger.record_payment(self.customer.id, 400)

        self.assertEqual(self.ledger.get_balance(self.customer.id), 600)
        self.assertEqual(self.ledger.get_balance(other.id), 2_000)
        self.assertEqual(len(self.ledger.list_transactions(self.customer.id)), 2)
        self.assertEqual(len(self.ledger.list_transactions(other.id)), 1)


if __name__ == "__main__":
    unittest.main()
