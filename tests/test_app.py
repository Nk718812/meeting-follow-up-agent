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

    @patch("app._model_call")
    def test_conflicting_commitments_are_consolidated_and_judged(self, model_call):
        """The workflow tells both model roles how to handle the evaluation scenario."""
        conflicting = {
            "decisions": [],
            "action_items": [
                {"task": "Revise campaign budget", "owner": "Rachel", "deadline": "September 12"},
                {"task": "Revise campaign budget", "owner": "Rachel", "deadline": "September 16"},
                {"task": "Contact advertising agency", "owner": "Kevin", "deadline": "Friday"},
            ],
            "unresolved_questions": [],
            "clarifications": [],
            "follow_up_email": "Draft requiring correction.",
        }
        consolidated = {
            "decisions": [],
            "action_items": [
                {"task": "Revise campaign budget", "owner": "Rachel", "deadline": "Not specified"},
                {"task": "Contact advertising agency", "owner": "Unassigned", "deadline": "Not specified"},
            ],
            "unresolved_questions": [
                "Is Rachel's campaign-budget deadline September 12 or September 16?",
                "Did Maria accept responsibility for contacting the advertising agency?",
            ],
            "clarifications": ["Confirm both the revised deadline and agency-contact owner."],
            "follow_up_email": "Please confirm the unresolved assignments and review this draft.",
        }
        feedback = ["Consolidate both tasks and mark their unresolved fields instead of presenting them definitively."]
        model_call.side_effect = [conflicting, {"passed": False, "feedback": feedback}, consolidated.copy()]
        notes = (
            "Rachel agreed to revise the campaign budget by September 12. Later, Rachel said "
            "she needed until September 16, but no new deadline was confirmed. Kevin agreed "
            "to contact the advertising agency by Friday. Later Kevin said Maria would handle "
            "it, but Maria did not confirm."
        )

        result = app.analyze_meeting(notes)

        extraction_instructions = model_call.call_args_list[0].args[0]
        judge_instructions = model_call.call_args_list[1].args[0]
        self.assertIn("same underlying task into one action item", extraction_instructions)
        self.assertIn("attempted reassignment", extraction_instructions)
        self.assertIn("duplicate definitive action items", judge_instructions)
        self.assertIn("'Unassigned'", judge_instructions)
        self.assertEqual(model_call.call_count, 3)
        self.assertIn(feedback[0], model_call.call_args_list[2].args[1])
        self.assertEqual(len(result["action_items"]), 2)
        self.assertEqual(result["action_items"][0]["deadline"], "Not specified")
        self.assertEqual(result["action_items"][1]["owner"], "Unassigned")
        self.assertTrue(result["quality_check"]["revised"])


if __name__ == "__main__":
    unittest.main()
