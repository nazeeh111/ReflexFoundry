# Security and privacy

ReflexFoundry is an experimental local decision tool. Its outputs are advisory. Never use a learned policy as the sole authority for permissions, credential access, destructive operations, security approvals, or other sensitive actions.

## What data enters the tool

Observation requires both `authorized: true` in the supplied record and explicit `--consent`. Inputs use an allowlist: a summary, relative changed-file paths, and an optional symbol. Common credential patterns, email addresses, and home-directory identifiers are redacted. Repository identifiers are hashed during consented ingestion.

Redaction is best effort. It cannot identify every secret, proprietary passage, personal identifier, or sensitive filename. Review records before ingestion and before sharing any workspace or Lab export. Generated benchmark fixtures contain public synthetic examples; that does not make your own observations safe to publish.

ReflexFoundry does not need private transcripts, hidden reasoning, a hosted API key, or access to credential stores. Basic CLI commands and the model-free demo require no network. Optional dependency installation and `download` contact package or model hosts. Downloaded software and weights have their own supply-chain and licensing boundaries.

## Local state and interfaces

Workspace files contain records, predictions, evaluation evidence, policy metadata and deployment history. Keep them in a trusted local directory, excluded from version control unless explicitly reviewed for release. The local Lab server binds to loopback and exposes read-only inspection of that workspace. Do not expose it through a public tunnel or proxy without designing authentication and access controls.

The standalone Lab export is a shareable snapshot. Inspect it before sharing. HTML escaping prevents record text from becoming executable markup, but the export can still reveal the nonsensitive-looking information you chose to include.

Atomic file replacement and workspace locks protect updates. Model, tokenizer, configuration, data and catalog hashes bind evidence to a local artifact version. These checks help detect changed inputs and accidental drift. They are not signatures, access control, sandboxing, or protection against an attacker who can edit the code and evidence files.

Safe tensor model artifacts avoid executable pickle loading in the reconstruction path. Treat all third-party models and software as untrusted until reviewed. Use trusted pinned sources, preserve provenance, and retain applicable notices.

## Deployment boundaries

Deployment requires accepted evaluation evidence, explicit opt-in, verified shadow proposals and a decision budget. Failed outcomes, artifact changes, runtime errors, drift signals and exhausted budgets lead to conservative fallback or rollback under the lifecycle rules. These checks reduce risk; they do not guarantee correctness on arbitrary tasks.

Shadow verification must test the learned candidate itself. A successful fallback is insufficient. Outcome reports are user-supplied observations; the CLI cannot attest that an external grader ran. Keep independent final checks in your agent and CI, and use native permission controls for actual execution.

Do not grant authority by editing local report flags or fabricating successful outcomes. The initial supported catalogs exclude sensitive approval decisions. Adding a catalog requires review, fresh training/evaluation evidence, and an independent success criterion.

## Reporting an issue

Report reproducible vulnerabilities privately through this repository's GitHub security reporting feature when available. If private reporting is unavailable, open a minimal issue requesting a private reporting channel without including exploit details, credentials, private records, or personal information. No guaranteed response time is promised for this experimental project.

For ordinary correctness problems, use a minimal public issue with the version, platform, command and sanitized input. Include enough evidence to distinguish a regression from a pre-existing failure. Never include secret-bearing environment dumps or credential files.
