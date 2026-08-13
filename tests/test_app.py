import json
import os
import unittest
from unittest.mock import patch

import app


class AnalyzeMeetingTests(unittest.TestCase):
    def setUp(self):
        self.extraction = {
            "decisions": ["Launch was approved."],
            "action_items": [{"task": "Create plan", "owner": "Unassigned", "deadline": "Not specified"}],
            "unresolved_questions": [], "clarifications": [], "follow_up_email": "Please review this draft.",
        }

    def test_empty_notes_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "cannot be empty"):
            app.analyze_meeting("  ")

    @patch("app._model_call")
    def test_passed_judgment_uses_two_calls(self, model_call):
        model_call.side_effect = [self.extraction.copy(), {"passed": True, "feedback": []}]
        result = app.analyze_meeting("The launch was approved.")
        self.assertEqual(model_call.call_count, 2)
        self.assertFalse(result["quality_check"]["revised"])

    @patch("app._model_call")
    def test_failed_judgment_triggers_revision(self, model_call):
        revised = self.extraction | {"decisions": []}
        model_call.side_effect = [self.extraction.copy(), {"passed": False, "feedback": ["Unsupported decision"]}, revised]
        result = app.analyze_meeting("Launch was only suggested.")
        self.assertEqual(model_call.call_count, 3)
        self.assertTrue(result["quality_check"]["revised"])
        self.assertEqual(result["decisions"], [])

    def test_missing_api_key_has_clear_error(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(app.ConfigurationError, "OPENAI_API_KEY"):
                app._model_call("instructions", "input", {}, "test")


if __name__ == "__main__":
    unittest.main()
