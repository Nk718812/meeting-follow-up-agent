"""Executive Meeting Follow-Up Agent.

A dependency-free local web server and a deliberately small OpenAI API client.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).parent
OPENAI_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-5-mini"

EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "decisions": {"type": "array", "items": {"type": "string"}},
        "action_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "task": {"type": "string"},
                    "owner": {"type": "string"},
                    "deadline": {"type": "string"},
                },
                "required": ["task", "owner", "deadline"],
                "additionalProperties": False,
            },
        },
        "unresolved_questions": {"type": "array", "items": {"type": "string"}},
        "clarifications": {"type": "array", "items": {"type": "string"}},
        "follow_up_email": {"type": "string"},
    },
    "required": [
        "decisions",
        "action_items",
        "unresolved_questions",
        "clarifications",
        "follow_up_email",
    ],
    "additionalProperties": False,
}

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "passed": {"type": "boolean"},
        "feedback": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["passed", "feedback"],
    "additionalProperties": False,
}

EXTRACTION_INSTRUCTIONS = """You extract a faithful executive meeting follow-up.
Use only facts explicitly stated in the supplied notes. Never invent or silently infer a
decision, commitment, owner, or deadline. A suggestion is not a decision or action.
For every action without an explicitly assigned owner use exactly 'Unassigned'; for
every action without an explicitly stated deadline use exactly 'Not specified'. Put
ambiguities in clarifications as concise requests for clarification. Draft a concise
follow-up email based only on the extraction and include a reminder to review it.

Resolve the meeting chronologically before producing action_items. Group statements
that refer to the same underlying task into one action item; never output competing or
duplicate versions of that task as definitive commitments. A later statement supersedes
an earlier owner or deadline only when it clearly establishes an accepted new
commitment. A request, proposal, possibility, attempted reassignment, or statement that
someone else will do the work is not acceptance by that person unless the notes support
their acceptance. When conflicting statements leave the current owner unresolved, use
exactly 'Unassigned'. When they leave the current deadline unresolved, use exactly
'Not specified'. Describe each material conflict in unresolved_questions and/or
clarifications, including what must be confirmed. Do not preserve an earlier owner or
deadline as definitive merely because it was once agreed if later discussion makes the
current commitment genuinely unclear."""

JUDGE_INSTRUCTIONS = """You are an independent accuracy judge. Compare the proposed
extraction with the original notes. Fail it if it contains unsupported claims, invented
owners/deadlines, treats suggestions as commitments, or misses important explicit
decisions/actions/questions. Feedback must be specific, actionable, and grounded only
in the notes. Explicitly trace statements about the same task over time. Fail the draft
if contradictory or superseded versions appear as duplicate definitive action items; if
an unresolved owner or deadline is shown definitively instead of as 'Unassigned' or
'Not specified'; if a proposed reassignment is treated as accepted without support; or
if a material conflict is not surfaced for clarification. A later statement may replace
an earlier one only when it clearly establishes a new commitment. Do not rewrite the
extraction."""


class ConfigurationError(RuntimeError):
    """Raised when required local configuration is absent."""


class ModelError(RuntimeError):
    """Raised when the model API cannot return usable structured output."""


def _model_call(instructions: str, input_text: str, schema: dict[str, Any], name: str) -> dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ConfigurationError("OPENAI_API_KEY is not set. See README.md for setup instructions.")

    payload = {
        "model": os.getenv("OPENAI_MODEL", DEFAULT_MODEL),
        "instructions": instructions,
        "input": input_text,
        "text": {"format": {"type": "json_schema", "name": name, "strict": True, "schema": schema}},
    }
    request = urllib.request.Request(
        OPENAI_URL,
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise ModelError(f"OpenAI API returned HTTP {exc.code}: {detail[:500]}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ModelError(f"Could not reach the OpenAI API: {exc}") from exc

    output_text = result.get("output_text")
    if not output_text:
        for item in result.get("output", []):
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    output_text = content.get("text")
                    break
    if not output_text:
        raise ModelError("The OpenAI API response did not contain structured output.")
    try:
        return json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise ModelError("The OpenAI API returned invalid JSON.") from exc


def analyze_meeting(notes: str) -> dict[str, Any]:
    """Run extraction, independent judging, and conditional revision."""
    notes = notes.strip()
    if not notes:
        raise ValueError("Meeting notes cannot be empty.")
    if len(notes) > 100_000:
        raise ValueError("Meeting notes must be 100,000 characters or fewer.")

    extraction = _model_call(EXTRACTION_INSTRUCTIONS, notes, EXTRACTION_SCHEMA, "meeting_extraction")
    judge_input = f"ORIGINAL MEETING NOTES:\n{notes}\n\nPROPOSED EXTRACTION:\n{json.dumps(extraction)}"
    judgment = _model_call(JUDGE_INSTRUCTIONS, judge_input, JUDGE_SCHEMA, "quality_judgment")

    revised = False
    if not judgment["passed"]:
        revision_instructions = EXTRACTION_INSTRUCTIONS + "\nRevise the draft using all judge feedback. Return a complete corrected result."
        revision_input = (
            f"ORIGINAL MEETING NOTES:\n{notes}\n\nDRAFT:\n{json.dumps(extraction)}"
            f"\n\nJUDGE FEEDBACK:\n{json.dumps(judgment['feedback'])}"
        )
        extraction = _model_call(revision_instructions, revision_input, EXTRACTION_SCHEMA, "revised_meeting_extraction")
        revised = True

    extraction["quality_check"] = {"passed_initially": judgment["passed"], "revised": revised}
    return extraction


class AppHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/":
            self._send_bytes(ROOT.joinpath("static/index.html").read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/static/styles.css":
            self._send_bytes(ROOT.joinpath("static/styles.css").read_bytes(), "text/css; charset=utf-8")
        elif self.path == "/static/app.js":
            self._send_bytes(ROOT.joinpath("static/app.js").read_bytes(), "text/javascript; charset=utf-8")
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/analyze":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 150_000:
                raise ValueError("Request is too large.")
            payload = json.loads(self.rfile.read(length))
            result = analyze_meeting(payload.get("notes", ""))
            self._send_json(HTTPStatus.OK, result)
        except (ValueError, json.JSONDecodeError) as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except ConfigurationError as exc:
            self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": str(exc)})
        except ModelError as exc:
            self._send_json(HTTPStatus.BAD_GATEWAY, {"error": str(exc)})

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        self._send_bytes(json.dumps(payload).encode(), "application/json", status)

    def _send_bytes(self, body: bytes, content_type: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format % args}")


def main() -> None:
    port = int(os.getenv("PORT", "8000"))
    server = ThreadingHTTPServer(("127.0.0.1", port), AppHandler)
    print(f"Executive Meeting Follow-Up Agent running at http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")


if __name__ == "__main__":
    main()
