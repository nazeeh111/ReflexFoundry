---
name: reflexfoundry
description: Inspect repeated low-risk coding decisions with local ReflexFoundry outcome evidence when the user requests ReflexFoundry test-scope or source-retrieval advice.
---

Use the installed `reflex` CLI in the current repository. Read `reflex specs` before constructing a request. This skill supplies explicit advisory decisions; it does not intercept Codex internals.

1. Ask for consent before recording project-specific inputs unless the user already explicitly authorized collection. Record only bounded task summaries, relative changed paths, and optional symbol names. Never export private conversations, hidden reasoning, credentials, complete source code, or arbitrary tool output.
2. Use a task-local JSON request with `spec` and `inputs`. For `test-scope-v1`, choices are `focused` and `full`; original full validation is the fallback. For `context-route-v1`, choices are `symbol` and `search`; repository search is the fallback. Context retrieval has a separate public-source coverage study. Supplied experimental policies must satisfy the same evaluation and shadow gates; source coverage does not establish autonomous coding benefit.
3. Run `reflex decide request.json --workspace .reflex`. Read the JSON result. In shadow mode, preserve the original workflow and inspect the candidate only. If fallback is true, use the original workflow. A recommendation never grants tool permissions or changes required project test gates.
4. Execute tools through Codex's normal native permissions and tools. Never use this model for approvals, credentials, destructive actions, security decisions, final test waivers, or submitting work.
5. Record independent verification with `reflex outcome REQUEST_ID --success --duration-ms NUMBER --consent --candidate-verified (use --failure for a failed candidate)`. Judge the recommended candidate's outcome, not whether the fallback succeeded. Missing independent grading is not success.
6. Evaluation and shadow observation do not authorize deployment. Deployment requires the user's explicit opt-in, a passing held-out report, and verified shadow outcomes. If the CLI blocks deployment, show its reasons and keep the original workflow.

Example request:
```json
{"spec":"test-scope-v1","inputs":{"summary":"Fix display formatting in a private helper","changed_files":["labels.py"]}}
```

For authorized event exports, `codex exec --json` supplies documented observable actions. Do not automatically ingest that stream: use the documented adapter to extract allowlisted command names only, review/redact it, and explicitly consent to any decision records. No private Codex session files are read.
