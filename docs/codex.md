# Codex integration

ReflexFoundry integrates through an explicit skill and a local CLI. Codex keeps its normal tools, repository instructions, permissions, and execution environment. ReflexFoundry sees only records or event exports you deliberately provide.

## Install the skill into a repository

The [official Codex skills documentation](https://developers.openai.com/codex/skills) describes repository skills in `.agents/skills/`. From the repository where you want to use the integration, copy the bundled `integrations/codex/skills/reflexfoundry/` directory to `.agents/skills/reflexfoundry/` and review `SKILL.md`.

Install the Python package into an environment where Codex can invoke `reflex`, then explicitly request `$reflexfoundry`. Installing a skill is not authorization to export private records, execute an action, or deploy a policy. Review proposed skill changes under your normal repository process.

This project does not install global hooks, change Codex settings, intercept model traffic, or read private internal reasoning. The initial integration is a supported skill/CLI workflow, not an automatic runtime hook.

## Ask for a bounded decision

Create `request.json` from observable facts:

```json
{
  "spec": "test-scope-v1",
  "inputs": {
    "summary": "Fix display formatting in the labels module.",
    "changed_files": ["src/labels.py"]
  }
}
```

Run:

```bash
reflex decide request.json --workspace .reflex
```

The result contains an advisory choice and a request identifier. Without a valid active policy, the test-scope fallback is the full suite. In shadow mode the returned choice is also the fallback; the proposed candidate is evidence to inspect separately. A returned `focused` suggestion means the next bounded check, never permission to skip mandatory final validation.

The equivalent context-retrieval request uses `context-route-v1`, a summary, optional relative changed-file paths, and an optional `symbol` string. Its choices are `symbol` and `search`, with `search` as fallback. The first release does not claim trained or experimentally validated delegation for context retrieval.

Inputs allow only `summary`, `changed_files`, and `symbol`, under the spec's byte budget. File paths must be relative and stay within the repository. Permission decisions, credential operations, destructive actions, and security approvals are outside both catalogs.

## Observe only what you choose to share

Add `authorized: true`, a stable decision `id`, an opaque repository identifier, and the actually selected choice to an observation record. Ingest it with:

```bash
reflex observe decision.json --workspace .reflex --consent
```

Review records before sharing them. Do not export full transcripts or command arguments to obtain training data. Common-pattern redaction reduces exposure but cannot identify every secret or personal identifier.

An observation of a choice is not an outcome label. Independent outcomes require actual checks of the declared task success criterion. Where only one action has been observed, do not invent the unchosen action's result. The initial controlled benchmark executes every candidate so it can compare them honestly.

## Inspect supported event exports

If you separately choose to export documented Codex command events, the summarizer accepts that local file:

```bash
reflex codex-events authorized-events.jsonl --consent
```

It summarizes supported observable events without retaining command arguments. It does not access hidden state, manufacture candidate outcomes, or automatically train a policy. Inspect its output and the current implementation before adopting an export process. See the [official noninteractive Codex documentation](https://developers.openai.com/codex/noninteractive) for supported event output.

## Shadow evidence must check the proposal

After training and evaluating a policy in the same workspace:

```bash
reflex shadow --workspace .reflex --policy models/policy-v1
reflex decide request.json --workspace .reflex
```

Record the returned request identifier. If the model produced an eligible proposal, separately execute that proposed validation scope through Codex's normal authorized tools. Independently check whether its accept/reject result agrees with the task's complete public contract. Merely running the fallback successfully does not verify the proposed shortcut.

Only after that check, use the real identifier and measured duration:

```bash
reflex outcome REQUEST_ID --workspace .reflex \
  --success --duration-ms MEASURED_MS --consent --candidate-verified
```

Use `--failure` when the independently checked candidate fails the criterion. `--candidate-verified` is a declaration about a completed check, not a request to run a grader. Never set it for an abstained or untested proposal. Evidence remains local user-supplied data; the CLI cannot prove an external check happened.

Promotion requires the held-out gate, explicit opt-in, and at least thirty eligible, independently checked shadow proposals with distinct input digests for the current artifact and shadow epoch. Repeated identical inputs cannot meet that count. Distinct hashes are only a minimum check: related variants may still share one underlying task and are not independent evidence. Policies with rejected evidence may still be inspected in shadow, but cannot deploy.

```bash
reflex deploy --workspace .reflex --policy models/policy-v1 \
  --opt-in --max-decisions 100
```

Expected rejection is part of the workflow. Changing the model, tokenizer, configuration or decision catalog invalidates its bindings. Budget exhaustion, observed regressions, runtime failures, or monitored drift trigger fallback or rollback according to the lifecycle checks.

## Return to the original workflow

```bash
reflex rollback --workspace .reflex
```

Keep independent final validation in Codex and the repository's normal CI. ReflexFoundry must never become the sole authority for permissions or security-sensitive approvals.
