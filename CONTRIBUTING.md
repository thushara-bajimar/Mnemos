# Contributing to Mnemos

## Development setup

```bash
git clone <repo> && cd Mnemos
cd backend && python -m pip install -r requirements.txt && cd ..
cd frontend && npm install && cd ..
```

Run the backend (`python -m uvicorn app.main:app --reload --port 8000` from `backend/`) and the
frontend (`npm run dev` from `frontend/`) in two terminals.

## Ground rules

1. **Explainability.** Every new decision rule, route or ranking factor must add a human-readable
   reason or signal, so that the UI can show *why*.
2. **Memory is data.** Never execute, template or follow memory content. New context renderers must
   use `safety.escape_for_context`.
3. **Privacy.** New tables or copies of memory content must be handled in
   `ForgettingService.delete_ids`, `presence()` and `physical_scan`, and covered by a test proving
   that deletion reaches them.
4. **No silent overwrite.** Changes to facts go through UPDATE (supersede) or a conflict, never an
   in-place overwrite without a revision.
5. **Honest numbers.** Never hard-code benchmark results. Label estimates (see `core/tokenizer.py`).
6. **No secrets in code.** Configuration comes only from `MNEMOS_*` environment variables.

## Tests

* Backend: `cd backend && python -m pytest -q`. Every behaviour change needs a test. If your change
  touches a capability covered by the evaluation lab, add or adjust a scenario in
  `app/evaluation/scenarios.py`; scenarios must stay at 30 or more, and all must pass.
* Frontend: `cd frontend && npm test && npx tsc -b && npx vite build`.

## Code style

* Python: type hints, small functions, docstrings on modules and services, parameterised SQL only.
* TypeScript: strict mode; loading and error states for every API call; no unused locals.

## Commits and pull requests

* Write descriptive commit messages ("Forgetting: scrub handover packages and re-seal checksum").
* Put one logical change in each commit, and run all tests before pushing.
* Pull requests should explain the behaviour change, the tests added, and any effect on the
  documentation or evaluation numbers. If results change, regenerate `docs/results/latest_eval.json`
  and the PDFs with `python scripts/build_pdfs.py`.

## Adding a storage strategy

1. Implement `add`, `remove`, `contains` and `search` in `app/stores/stores.py`.
2. Wire it into `engine.py`, `router.py`, `retrieval.py` (with a weight) and `forgetting.py`
   (removal and presence).
3. Add a benchmark class in `app/evaluation/storage_bench.py`.

## Adding an agent integration

Use the `ToolGateway` protocol (`POST /api/tools/invoke`) rather than private APIs. Register the
agent through `POST /api/agents/register`. See `agents/node_agent.mjs`.
