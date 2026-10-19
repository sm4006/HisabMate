import json
import unittest
from datetime import date
from unittest.mock import Mock

from src.ai_adapter import (
    MalformedModelResponseError,
    OllamaAdapter,
    OllamaTimeoutError,
    OllamaUnavailableError,
)


class FakeResponse:
    def __init__(self, body: object) -> None:
        self.body = json.dumps(body).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


def response_for(proposal: object) -> FakeResponse:
    return FakeResponse({"response": json.dumps(proposal)})


class OllamaAdapterTests(unittest.TestCase):
    def adapter_for(self, response: FakeResponse) -> OllamaAdapter:
        return OllamaAdapter(
            model_name="test-model",
            endpoint="http://ollama.test",
            urlopen=Mock(return_value=response),
        )

    def test_valid_transaction_extracts_integer_paise(self) -> None:
        adapter = self.adapter_for(
            response_for(
                {
                    "intent": "credit",
                    "customer_name": "Asha",
                    "amount_text": "₹250.50",
                    "missing_information": [],
                    "ambiguous": False,
                }
            )
        )

        proposal = adapter.extract_proposal("Asha ko 250.50 ka udhaar")

        self.assertEqual(proposal.intent, "credit")
        self.assertEqual(proposal.customer_name, "Asha")
        self.assertEqual(proposal.amount_paise, 25_050)
        self.assertFalse(proposal.clarification_required)
        self.assertTrue(proposal.confirmation_required)

    def test_default_model_is_llama32(self) -> None:
        adapter = OllamaAdapter(urlopen=Mock())
        self.assertEqual(adapter.model_name, "llama3.2:3b")

    def test_requested_hinglish_messages_preserve_clarification_safety(self) -> None:
        cases = [
            (
                "Ramesh ne 500 rupaye diye",
                {"intent": "payment", "customer_name": "Ramesh", "amount_text": "500",
                 "missing_information": [], "ambiguous": False},
                ("payment", "Ramesh", 50_000, False),
            ),
            (
                "Suresh ko 1200 ka maal diya",
                {"intent": "credit", "customer_name": "Suresh", "amount_text": "1200",
                 "missing_information": [], "ambiguous": False},
                ("credit", "Suresh", 120_000, False),
            ),
            (
                "500 diye",
                {"intent": "payment", "customer_name": None, "amount_text": "500",
                 "missing_information": ["customer_name"], "ambiguous": True},
                ("payment", None, 50_000, True),
            ),
            (
                "Mohan ka 2000 baaki hai",
                {"intent": None, "customer_name": "Mohan", "amount_text": None,
                 "missing_information": ["intent", "amount"], "ambiguous": True},
                (None, "Mohan", None, True),
            ),
        ]
        for message, model_output, expected in cases:
            with self.subTest(message=message):
                proposal = self.adapter_for(response_for(model_output)).extract_proposal(message)
                self.assertEqual(
                    (proposal.intent, proposal.customer_name, proposal.amount_paise,
                     proposal.clarification_required),
                    expected,
                )

    def test_incomplete_response_and_invalid_negative_amount_are_rejected(self) -> None:
        incomplete = response_for(
            {
                "intent": "payment",
                "customer_name": "Ramesh",
                "amount_text": "500",
                "missing_information": [],
            }
        )
        with self.assertRaises(MalformedModelResponseError):
            self.adapter_for(incomplete).extract_proposal("Ramesh paid 500")

        negative = response_for(
            {
                "intent": "payment",
                "customer_name": "Ramesh",
                "amount_text": "-500",
                "missing_information": [],
                "ambiguous": False,
            }
        )
        with self.assertRaises(MalformedModelResponseError):
            self.adapter_for(negative).extract_proposal("Ramesh paid -500")

    def test_model_cannot_invent_customer_missing_from_source_message(self) -> None:
        adapter = self.adapter_for(
            response_for(
                {
                    "intent": "payment",
                    "customer_name": "Ramesh",
                    "amount_text": "500",
                    "missing_information": [],
                    "ambiguous": False,
                }
            )
        )
        proposal = adapter.extract_proposal("500 diye")
        self.assertIsNone(proposal.customer_name)
        self.assertTrue(proposal.clarification_required)
        self.assertIn("customer_name", proposal.missing_information)

    def test_missing_information_requires_clarification(self) -> None:
        adapter = self.adapter_for(
            response_for(
                {
                    "intent": None,
                    "customer_name": None,
                    "amount_text": None,
                    "missing_information": [],
                    "ambiguous": True,
                }
            )
        )

        proposal = adapter.extract_proposal("kal ka hisaab likho")

        self.assertTrue(proposal.clarification_required)
        self.assertEqual(
            proposal.missing_information, ("intent", "customer_name", "amount")
        )

    def test_malformed_output_is_rejected(self) -> None:
        adapter = self.adapter_for(FakeResponse({"response": "not-json"}))
        with self.assertRaises(MalformedModelResponseError):
            adapter.extract_proposal("record this")

    def test_unknown_or_malformed_intent_is_rejected(self) -> None:
        for intent in ("refund", [], {"kind": "credit"}):
            with self.subTest(intent=intent):
                adapter = self.adapter_for(
                    response_for(
                        {
                            "intent": intent,
                            "customer_name": "Asha",
                            "amount_text": "100",
                            "missing_information": [],
                            "ambiguous": False,
                        }
                    )
                )
                with self.assertRaises(MalformedModelResponseError):
                    adapter.extract_proposal("Asha paid 100")

    def test_non_object_and_invalid_field_types_are_rejected(self) -> None:
        cases = [
            [],
            {
                "intent": "credit",
                "customer_name": "Asha",
                "amount_text": "100",
                "missing_information": "amount",
                "ambiguous": False,
            },
            {
                "intent": "credit",
                "customer_name": "Asha",
                "amount_text": "100",
                "missing_information": [],
                "ambiguous": "false",
            },
        ]
        for model_output in cases:
            with self.subTest(model_output=model_output):
                adapter = self.adapter_for(response_for(model_output))
                with self.assertRaises(MalformedModelResponseError):
                    adapter.extract_proposal("Asha paid 100")

    def test_invalid_amount_precision_is_rejected(self) -> None:
        adapter = self.adapter_for(
            response_for(
                {
                    "intent": "payment",
                    "customer_name": "Asha",
                    "amount_text": "250.555",
                    "missing_information": [],
                    "ambiguous": False,
                }
            )
        )
        with self.assertRaises(MalformedModelResponseError):
            adapter.extract_proposal("Asha paid 250.555")

    def test_explicit_and_relative_dates_use_reference_date(self) -> None:
        adapter = OllamaAdapter(
            model_name="test-model",
            endpoint="http://ollama.test",
            reference_date=date(2026, 10, 19),
            urlopen=Mock(
                return_value=response_for(
                    {
                        "intent": "payment",
                        "customer_name": "Ramesh",
                        "amount_text": "500",
                        "date_text": "yesterday",
                        "missing_information": [],
                        "ambiguous": False,
                    }
                )
            ),
        )
        proposal = adapter.extract_proposal("Yesterday Ramesh paid 500")
        self.assertEqual(proposal.transaction_date, "2026-10-18")
        self.assertFalse(proposal.clarification_required)

    def test_ambiguous_relative_date_requires_clarification(self) -> None:
        adapter = self.adapter_for(
            response_for(
                {
                    "intent": "payment",
                    "customer_name": "Ramesh",
                    "amount_text": "500",
                    "date_text": "kal",
                    "missing_information": [],
                    "ambiguous": False,
                }
            )
        )
        proposal = adapter.extract_proposal("Kal Ramesh ne 500 diye")
        self.assertIsNone(proposal.transaction_date)
        self.assertTrue(proposal.ambiguous)
        self.assertIn("date", proposal.missing_information)
        self.assertTrue(proposal.clarification_required)

    def test_hinglish_transaction_proposals_use_existing_schema(self) -> None:
        cases = [
            (
                "Ramesh ne 500 diye",
                {
                    "intent": "payment",
                    "customer_name": "Ramesh",
                    "amount_text": "500",
                    "missing_information": [],
                    "ambiguous": False,
                },
                ("payment", "Ramesh", 50_000, False),
            ),
            (
                "Suresh ko 1200 ka maal diya",
                {
                    "intent": "credit",
                    "customer_name": "Suresh",
                    "amount_text": "1200",
                    "missing_information": [],
                    "ambiguous": False,
                },
                ("credit", "Suresh", 120_000, False),
            ),
            (
                "Ramesh ke khate mein 300 jama karo",
                {
                    "intent": "payment",
                    "customer_name": "Ramesh",
                    "amount_text": "300",
                    "missing_information": [],
                    "ambiguous": False,
                },
                ("payment", "Ramesh", 30_000, False),
            ),
            (
                "Mohan ka 2 hazaar baaki hai",
                {
                    "intent": None,
                    "customer_name": "Mohan",
                    "amount_text": None,
                    "missing_information": ["transaction_type"],
                    "ambiguous": True,
                },
                (None, "Mohan", None, True),
            ),
            (
                "Ramesh se 500 lene hain",
                {
                    "intent": None,
                    "customer_name": "Ramesh",
                    "amount_text": "500",
                    "missing_information": ["transaction_type"],
                    "ambiguous": True,
                },
                (None, "Ramesh", 50_000, True),
            ),
            (
                "Kal Ramesh ne 500 diye",
                {
                    "intent": "payment",
                    "customer_name": "Ramesh",
                    "amount_text": "500",
                    "missing_information": ["date"],
                    "ambiguous": True,
                },
                ("payment", "Ramesh", 50_000, True),
            ),
            (
                "500 diye",
                {
                    "intent": "payment",
                    "customer_name": None,
                    "amount_text": "500",
                    "missing_information": [],
                    "ambiguous": True,
                },
                ("payment", None, 50_000, True),
            ),
            (
                "Ramesh ne 500 diye ya 800?",
                {
                    "intent": "payment",
                    "customer_name": "Ramesh",
                    "amount_text": None,
                    "missing_information": ["amount"],
                    "ambiguous": True,
                },
                ("payment", "Ramesh", None, True),
            ),
            (
                "Ramesh ko 5 peti maal diya",
                {
                    "intent": "credit",
                    "customer_name": "Ramesh",
                    "amount_text": None,
                    "missing_information": ["amount"],
                    "ambiguous": True,
                },
                ("credit", "Ramesh", None, True),
            ),
        ]
        for message, model_output, expected in cases:
            with self.subTest(message=message):
                proposal = self.adapter_for(response_for(model_output)).extract_proposal(
                    message
                )
                self.assertEqual(
                    (
                        proposal.intent,
                        proposal.customer_name,
                        proposal.amount_paise,
                        proposal.clarification_required,
                    ),
                    expected,
                )

    def test_unavailable_ollama_is_handled(self) -> None:
        opener = Mock(side_effect=ConnectionError("offline"))
        adapter = OllamaAdapter(urlopen=opener)
        with self.assertRaises(OllamaUnavailableError):
            adapter.extract_proposal("Asha paid 100")

    def test_timeout_is_handled(self) -> None:
        opener = Mock(side_effect=TimeoutError("slow"))
        adapter = OllamaAdapter(urlopen=opener)
        with self.assertRaises(OllamaTimeoutError):
            adapter.extract_proposal("Asha paid 100")

    def test_adapter_only_returns_confirmation_gated_proposal(self) -> None:
        opener = Mock(
            return_value=response_for(
                {
                    "intent": "payment",
                    "customer_name": "Asha",
                    "amount_text": "₹100",
                    "missing_information": [],
                    "ambiguous": False,
                }
            )
        )
        adapter = self.adapter_for(
            response_for(
                {
                    "intent": "payment",
                    "customer_name": "Asha",
                    "amount_text": "₹100",
                    "missing_information": [],
                    "ambiguous": False,
                }
            )
        )
        proposal = adapter.extract_proposal("Asha paid 100")
        self.assertTrue(proposal.confirmation_required)
        self.assertFalse(hasattr(proposal, "save"))
        self.assertFalse(hasattr(proposal, "database_path"))

        adapter_with_spy = OllamaAdapter(urlopen=opener)
        adapter_with_spy.extract_proposal("Asha paid 100")
        opener.assert_called_once()


if __name__ == "__main__":
    unittest.main()
