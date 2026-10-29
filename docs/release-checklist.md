# Release verification

This is a maintainer checklist, not a claim that a release has already passed. Record the exact commit, artifact hashes and links for the version being released. The initial `0.1.0` is intended as an experimental prerelease.

## Source and installation

- Inspect repository status and preserve unrelated work before assembling the release.
- Confirm the license, required attribution, version, supported Python versions and package metadata.
- Run Ruff, mypy and the meaningful test suite against the final source.
- Build the wheel and source archive. Install the wheel in a fresh environment with no source-tree import path.
- Run `reflex --version`, `reflex specs`, the small benchmark, discovery and Lab export from the clean install.
- Verify optional runtime versions and the actual local model-loading path separately. A core-only installation does not verify training or GPU inference.
- Inspect package contents for the Lab assets and any required integration instructions. Confirm linked files ship through the documented installation route.

## Research and model evidence

- Preserve the base model revision, upstream versions, training configuration, training-data provenance and adapter/checkpoint hashes.
- Confirm training rows never overlap calibration, promotion or locked test groups. Keep task variants together and distinguish exact-input deduplication from semantic independence.
- Preserve executed candidate outcomes, independent grader code, repeated timings, inference outputs, startup timings and the final evaluation report.
- Compare against original workflow, a strong deterministic heuristic, always-focused, trained always-delegation, selective delegation and ordinary Laya when actually run.
- Account for artifact-integrity screening and model loading on each modeled request. State explicitly whether interpreter startup, imports and full CLI/agent process time were measured. Label warm inference separately and distinguish summed stage costs from directly timed complete workflows.
- Publish rejection reasons, failures, fallback overhead and negative results. Do not claim monetary or energy savings from wall time alone.
- Derive every numerical chart from the preserved executed report. Retain plot sources and record the report hash.
- Label generated fixtures, controlled mutations and real-repository tasks accurately. Do not imply broad coding-task generalization from a fixture study.
- Include only redistributable model artifacts, with base attribution, license, config and reconstruction instructions. Verify the reconstructed policy actually loads and preserves relevant calibration.

## Lifecycle and Codex

- Check actual CLI parsing of all documented commands, including subcommand placement of `--workspace`.
- Verify fallback for no policy, malformed predictions, order instability, truncation, exceeded budget and inference failure.
- Verify refused deployment for rejected evidence, changed artifacts and insufficient shadow evidence.
- Check that shadow verification requires the eligible proposal itself, not the returned fallback's success.
- Verify bounded opt-in, unique outcome reporting, monitor-triggered rollback and explicit rollback history.
- Exercise the skill through supported Codex interactions without hidden hooks, transcript scraping or credential access. Record the precise integration checks and any live-trial limits.

## Presentation and privacy

- Render the current Lab from the final report. Inspect desktop and narrow layouts, empty/error states, keyboard interactions, record filters and evidence details.
- Inspect the actual README, diagrams and screenshots against the implementation. Validate local links and public destinations.
- Inspect release files and exported HTML for private paths, personal records, secrets, caches and temporary data.
- If delivering a video, use the actual Lab or CLI and executed evidence. Verify duration, dimensions, a full decode, readable holds and representative transition frames. Preserve editable source and asset provenance.

## Public verification

- Confirm the authenticated account and intended public repository `nazeeh111/ReflexFoundry`.
- Publish the reviewed source and appropriate topics. Source publication, CI configuration and passing remote CI are different states.
- Inspect remote CI at the exact published revision; report failed or unavailable checks honestly.
- Create the versioned prerelease with accurate limitations, installation instructions, evidence and permissible artifacts.
- Download release assets to a fresh destination, verify hashes and contents, and test the documented install/reconstruction route.
- Fetch the public repository, README and release unauthenticated where possible. Verify their visibility and links.
- Report the actual public repository and release URLs, exact checks, and unmet objective requirements. A local checkout or successful upload command alone is insufficient.
