import tempfile
import unittest
from datetime import date
from pathlib import Path

from src.api import ApiError, LedgerService
from src.ledger import Ledger


class StubAdapter:
    def extract_proposal(self, _message: str):
        return type(
            "Proposal",
            (),
            {
                "intent": "credit",
                "customer_name": "Asha",
                "amount_paise": 25_050,
                "transaction_date": None,
                "missing_information": (),
                "ambiguous": False,
                "clarification_required": False,
                "confirmation_required": True,
            },
        )()


class LedgerServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        handle = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        handle.close()
        self.path = Path(handle.name)
        self.ledger = Ledger(self.path)
        self.service = LedgerService(self.ledger, StubAdapter())
        self.customer = self.ledger.create_customer("Asha")

    def tearDown(self) -> None:
        self.ledger.close()
        self.path.unlink(missing_ok=True)

    def test_customers_dashboard_and_transactions_use_real_ledger_data(self) -> None:
        today = date.today().isoformat()
        self.ledger.record_credit(self.customer.id, 25_050, today)
        self.ledger.record_payment(self.customer.id, 5_050, today)

        customers = self.service.customers()
        dashboard = self.service.dashboard()

        self.assertEqual(customers[0]["balance_paise"], 20_000)
        self.assertEqual(dashboard["outstanding_paise"], 20_000)
        self.assertEqual(dashboard["received_today_paise"], 5_050)
        self.assertEqual(len(self.service.transactions()), 2)

    def test_transactions_can_be_filtered_by_customer_id(self) -> None:
        other = self.ledger.create_customer("Bina")
        self.ledger.record_credit(self.customer.id, 10_000)
        self.ledger.record_credit(other.id, 20_000)

        transactions = self.service.transactions(self.customer.id)

        self.assertEqual(len(transactions), 1)
        self.assertEqual(transactions[0]["customer_id"], self.customer.id)
        self.assertEqual(transactions[0]["amount_paise"], 10_000)

    def test_customer_balances_and_histories_are_isolated(self) -> None:
        other = self.ledger.create_customer("Bina")
        self.ledger.record_credit(self.customer.id, 30_000)
        self.ledger.record_payment(self.customer.id, 10_000)
        self.ledger.record_credit(other.id, 50_000)

        self.assertEqual(self.ledger.get_balance(self.customer.id), 20_000)
        self.assertEqual(self.ledger.get_balance(other.id), 50_000)
        self.assertEqual(len(self.service.transactions(self.customer.id)), 2)
        self.assertEqual(len(self.service.transactions(other.id)), 1)

    def test_transaction_history_filters_date_and_type_and_totals(self) -> None:
        other = self.ledger.create_customer("Bina")
        self.ledger.record_credit(self.customer.id, 30_000, "2026-10-18")
        self.ledger.record_payment(self.customer.id, 10_000, "2026-10-19")
        self.ledger.record_credit(other.id, 50_000, "2026-10-19")

        history = self.service.transaction_history(
            self.customer.id, "2026-10-19", "payment"
        )

        self.assertEqual(history["transaction_count"], 1)
        self.assertEqual(history["received_paise"], 10_000)
        self.assertEqual(history["credit_paise"], 0)
        self.assertEqual(history["transactions"][0]["customer_id"], self.customer.id)

    def test_empty_transaction_history_has_zero_totals(self) -> None:
        history = self.service.transaction_history(transaction_date="2026-10-20")

        self.assertEqual(history["transaction_count"], 0)
        self.assertEqual(history["received_paise"], 0)
        self.assertEqual(history["credit_paise"], 0)
        self.assertEqual(history["transactions"], [])

    def test_transaction_search_filters_customer_name_and_type(self) -> None:
        other = self.ledger.create_customer("Bina")
        self.ledger.record_credit(self.customer.id, 30_000, "2026-10-19")
        self.ledger.record_payment(self.customer.id, 10_000, "2026-10-19")
        self.ledger.record_credit(other.id, 50_000, "2026-10-19")

        customer_results = self.service.transaction_history(search="asha")
        payment_results = self.service.transaction_history(search="payment received")

        self.assertEqual(len(customer_results["transactions"]), 2)
        self.assertEqual(len(payment_results["transactions"]), 1)
        self.assertEqual(payment_results["received_paise"], 10_000)

    def test_csv_export_contains_filtered_real_ledger_data_and_escaped_text(self) -> None:
        formula_customer = self.ledger.create_customer("=Formula Customer")
        self.ledger.record_credit(self.customer.id, 12_999, "2026-10-19")
        self.ledger.record_credit(formula_customer.id, 1_000, "2026-10-19")

        content = self.service.export_csv(transaction_date="2026-10-19")

        self.assertIn("transaction_date,customer,transaction_type,amount_rupees", content)
        self.assertIn("2026-10-19,Asha,Credit given,129.99,,1", content)
        self.assertIn("'=Formula Customer", content)
        self.assertIn("remarks", content.splitlines()[0])

    def test_save_requires_confirmation_and_prevents_duplicate_proposal(self) -> None:
        payload = {
            "proposal_id": "proposal-1",
            "confirmed": False,
            "intent": "credit",
            "customer_id": self.customer.id,
            "amount_paise": 25_050,
        }
        with self.assertRaises(ApiError):
            self.service.save_transaction(payload)
        self.assertEqual(self.ledger.list_transactions(), [])

        payload["confirmed"] = True
        saved = self.service.save_transaction(payload)
        self.assertEqual(saved["amount_paise"], 25_050)
        retried = self.service.save_transaction(payload)
        self.assertEqual(retried, saved)
        self.assertEqual(len(self.ledger.list_transactions()), 1)

    def test_idempotency_survives_backend_restart(self) -> None:
        payload = {
            "proposal_id": "persistent-proposal",
            "confirmed": True,
            "intent": "credit",
            "customer_id": self.customer.id,
            "amount_paise": 25_050,
        }
        saved = self.service.save_transaction(payload)
        self.ledger.close()

        restarted_ledger = Ledger(self.path)
        try:
            restarted_service = LedgerService(restarted_ledger, StubAdapter())
            self.assertEqual(restarted_service.save_transaction(payload), saved)
            self.assertEqual(len(restarted_ledger.list_transactions()), 1)
        finally:
            restarted_ledger.close()

    def test_same_transaction_details_with_different_keys_are_separate(self) -> None:
        payload = {
            "confirmed": True,
            "intent": "credit",
            "customer_id": self.customer.id,
            "amount_paise": 25_050,
        }
        first = self.service.save_transaction({**payload, "proposal_id": "proposal-a"})
        second = self.service.save_transaction({**payload, "proposal_id": "proposal-b"})

        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(len(self.ledger.list_transactions()), 2)

    def test_reusing_key_for_different_details_is_rejected(self) -> None:
        payload = {
            "proposal_id": "conflicting-proposal",
            "confirmed": True,
            "intent": "credit",
            "customer_id": self.customer.id,
            "amount_paise": 25_050,
        }
        self.service.save_transaction(payload)

        with self.assertRaises(ApiError):
            self.service.save_transaction({**payload, "amount_paise": 30_000})
        self.assertEqual(len(self.ledger.list_transactions()), 1)

    def test_save_rejects_ambiguous_invalid_date_and_overpayment(self) -> None:
        base = {
            "proposal_id": "proposal-2",
            "confirmed": True,
            "intent": "payment",
            "customer_id": self.customer.id,
            "amount_paise": 100,
            "missing_information": ["date"],
            "ambiguous": False,
        }
        with self.assertRaises(ApiError):
            self.service.save_transaction(base)

        base["missing_information"] = []
        base["transaction_date"] = "not-a-date"
        with self.assertRaises(ApiError):
            self.service.save_transaction(base)

        base["transaction_date"] = "2026-10-18"
        with self.assertRaises(ApiError):
            self.service.save_transaction(base)
        self.assertEqual(self.ledger.list_transactions(), [])

    def test_edited_proposal_details_are_validated_and_saved(self) -> None:
        proposal = self.service.interpret("Asha ko 250.50 ka udhaar")
        self.assertEqual(proposal["amount_paise"], 25_050)

        saved = self.service.save_transaction(
            {
                "proposal_id": "edited-proposal",
                "confirmed": True,
                "intent": "credit",
                "customer_id": self.customer.id,
                "amount_paise": 12_500,
                "transaction_date": "2026-10-19",
            }
        )
        self.assertEqual(saved["amount_paise"], 12_500)
        self.assertEqual(self.ledger.get_balance(self.customer.id), 12_500)

    def test_invalid_customer_amount_and_intent_never_report_success(self) -> None:
        base = {
            "proposal_id": "invalid-request",
            "confirmed": True,
            "customer_id": self.customer.id,
            "amount_paise": 100,
        }
        for changes in (
            {"customer_id": 999},
            {"amount_paise": 0},
            {"intent": "refund"},
        ):
            with self.subTest(changes=changes):
                payload = {**base, "intent": "credit", **changes}
                with self.assertRaises(ApiError):
                    self.service.save_transaction(payload)
                self.assertEqual(self.ledger.list_transactions(), [])

    def test_interpret_returns_confirmation_gated_proposal(self) -> None:
        proposal = self.service.interpret("Asha ko 250.50 ka udhaar")
        self.assertEqual(proposal["amount_paise"], 25_050)
        self.assertTrue(proposal["confirmation_required"])


if __name__ == "__main__":
    unittest.main()
