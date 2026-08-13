# Executive Meeting Follow-Up Agent

A small academic prototype that turns pasted meeting notes into decisions, action items, unresolved questions, and a draft follow-up email. It uses an independent second model call to check the first extraction before showing results.

## Setup and run

You need Python 3.10+ and an OpenAI API key. No Python packages are required.

1. Create an API key in the OpenAI platform dashboard.
2. In a terminal, set it for the current session (do not paste it into this repository):
   ```bash
   export OPENAI_API_KEY="your-api-key-here"
   ```
3. Optional: select a model. The default is `gpt-5-mini`:
   ```bash
   export OPENAI_MODEL="gpt-5-mini"
   ```
4. Start the app:
   ```bash
   python3 app.py
   ```
5. Visit <http://127.0.0.1:8000>, paste notes, and select **Analyze Meeting**.

API usage is billed to the account associated with the key. The key stays on the server and is never sent to the browser.

## Workflow

1. **Extraction:** the server sends the notes to the OpenAI Responses API with a strict JSON schema and rules against guessing. Missing owners become `Unassigned`; missing deadlines become `Not specified`.
2. **Quality check:** a separate call receives the original notes and proposed extraction. It checks support, omissions, assignment accuracy, and whether suggestions were mistaken for commitments.
3. **Revision:** when the judge fails the draft, a third call creates a complete corrected extraction using the original notes and the judge's feedback.
4. **Final output:** the browser renders the structured result and draft email, with a human-review warning.

The quality judge is model-based, so it reduces rather than eliminates errors. A human must review the output before relying on or sending it.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

The tests mock model calls, so they do not require an API key or incur charges.
