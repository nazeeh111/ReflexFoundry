# Bounded Codex coding trial

Two actual agent repairs passed independent verification. The planned paired
study is incomplete because native host initialization and approval controls
blocked two planned observations. There are no complete comparable pairs and no
estimated benefit.

| Planned run | Arm | CLI wall time | Result |
| --- | --- | ---: | --- |
| 1 | Original | 1.212 s | Host initialization denied before coding tools; exit 1 |
| 2 | Shadow | 60.787 s | Repaired, independent checks passed; advisory fell back |
| 3 | Shadow | Not launched | Automatic approval review rejected launch and scoped retry |
| 4 | Original | 45.253 s | Repaired, independent checks passed |

Runs 2 and 4 each produced the exact original `itertoolz.py` bytes, SHA-256
`93e4d79bc7c6d68250657846454303ba95c0694c9ef165cb7a8e0bdf150711c6`.
Each independently passed the focused test, the full suite (192 passed, 1
skipped), and the public contract grader. Each had nine observable command
events. The shadow run had four leading allowlisted Python commands; original
had three. Command counts do not independently prove the commands' arguments.
The final answers report executing the required focused and full checks, while
the harness separately verifies the completed candidate.

CLI plus independent check durations were 67.390 s for shadow run 2 and
49.163 s for original run 4. These sums exclude checkout preparation and artifact
writing; individual independent durations are in each result JSON. The two
successful observations are from different planned pairs and are not a paired
timing estimate.

Run 2 returned `full`, `fallback: true`, with reason `local policy unavailable
or changed: ValueError`. The real model artifact changed during the parent's
separate final evaluation after the trial state was frozen. The frozen policy
bound `bffdf6c3...`, while a post-run library check measured `e3d2d654...` and
returned `_binding_valid: false`. See `binding-observation.json`. The trial
did not alter the model. This demonstrates safe binding refusal, not trained
policy inference or model quality.

The initial host-denied run used the normal outer sandbox. The successful
runs used explicitly reviewed host launches so Codex could initialize, retaining
the child's native `--sandbox workspace-write`. Run 3's first host-launch request
was rejected over possible runtime/policy artifact egress. An inventory
(`approval-provenance.json`) established generated/public release provenance and
synthetic benchmark metadata before one scoped retry through the same review
control. The retry was rejected because the reviewer did not accept
assistant-reported user authorization. No alternative route was used. Exact
reasons and the required scoped user authorization are in `blocked-03.json`.
Only three CLI processes started, below the four-process maximum. Actual launch
order was 1, 2, 4. No runtime/model changes or additional trials followed.

This is a feasibility study of actual autonomous repairs on public Toolz code.
It is separate from the scripted candidate-patch validation benchmark.

The predeclared task changes `first(seq)` so it skips the first item. Codex
receives the documented contract and must repair the source, then run the
normal focused official test and the full official suite. Each invocation gets
a fresh disposable checkout at Toolz commit
`451af60dec590a6010e2babdbf391ea8f815122f`. The clean full suite passes and the
mutant fails both the official focused test and a separately written public
contract grader. Tests and unrelated source files must remain unchanged.

The planned order is original, shadow, shadow, original, giving two paired
repeats with reversed arm order. Four CLI invocations are the maximum, including
permission failures, with a 180-second process timeout and a short shutdown
grace period. No model or reasoning-effort settings are overridden. Existing
configured CLI access is used without inspecting or changing credentials. The
inherited provider/model configuration is not audited. Successful-run stderr
contains a WebSocket upgrade error at a loopback endpoint, followed by successful
execution, so this evidence does not establish the upstream hosting route.

Both arms have the same repair prompt and required validation commands. The
shadow arm additionally reads the packaged ReflexFoundry skill, constructs an
honest task request, and invokes the local CLI with `--backend torch` before
validation. Its state is copied from the lead's real policy and report, points
to the real absolute `models/adapted-v1` path, and enters shadow mode through the
normal lifecycle function. Runtime source is snapshotted. No guards are weakened.
Policy abstention, domain refusal, binding failure or native sandbox refusal are
valid observable results. Deployment remains withheld and full validation stays
mandatory in both arms.

`scripts/codex_trial.py` performs the study. After each Codex process exits, the
harness independently runs the official focused test, full suite, and a public
contract grader. It saves candidate source bytes and SHA-256 hashes. The grader
checks strings, lists containing None, iterator consumption, generator input,
and empty-input StopIteration. It lives outside the agent's disposable checkout.

Event lines are processed in memory and discarded. No raw event stream,
reasoning, command arguments, tool output transcript, or private session files
are saved. Allowed evidence consists of exact task prompts, final answers,
observable command-name counts, CLI exit/errors, public source candidates,
independent check output, and the explicitly supplied policy artifacts. CLI
stderr is retained for initialization/permission diagnostics.

See `manifest.json` for pins, preflight results, runtime hashes and copied policy
binding. Each `run-NN/result.json` contains measured wall time and independently
verified results. `summary.json` contains descriptive paired timing differences
only for complete successful pairs. Its paired list is empty for this incomplete
study. The unpaired successful-run times above cannot support an arm comparison.

This is one task repeated twice, not a diverse task evaluation. Host load,
configured model behavior, startup, caches and arm order can change timing.
Neither a faster run nor all passing repairs would establish causal superiority,
general reliability, or permission to deploy the policy. Agent-reported checks
are distinct from the independent checks recorded by the harness.

The CLI's documented JSON output and final-message mechanism are described in
[OpenAI's non-interactive mode documentation](https://learn.chatgpt.com/docs/non-interactive-mode).
