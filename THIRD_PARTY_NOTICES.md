# Third-party notices

ReflexFoundry is an independent project. It is not affiliated with or endorsed by
OpenAI, Convai Innovations, TypeSafe, Laya Studio, Apple, Google Research or the
other projects listed here. Names identify compatible software and research.

License observations below were checked against the linked upstream files on
26 October 2026. Dependencies and model weights retain their own licenses;
ReflexFoundry's license does not relicense them. Distribution must retain any
notices required by the exact versions actually included.

| Project or material | License and attribution | Use and redistribution boundary |
| --- | --- | --- |
| [Laya](https://github.com/NandhaKishorM/laya) | [Apache-2.0](https://github.com/NandhaKishorM/laya/blob/main/LICENSE). Developed by Convai Innovations and Laya contributors. | Typed decision runtime and training foundation. Preserve its license and applicable notices for any redistributed source or derivative artifacts. Mark modified upstream source files if any are included. |
| [Laya weights](https://huggingface.co/convaiinnovations/laya) | The model card declares Apache-2.0. Convai Innovations. | Downloaded checkpoints are separate artifacts. Record their repository/revision and training provenance. A trained derivative must identify its base and preserve applicable model notices and license. Do not assume every model on a hosting service has this license. |
| [Laya-MLX](https://github.com/mizorewww/laya-mlx) | [Apache-2.0](https://github.com/mizorewww/laya-mlx/blob/main/LICENSE), with [NOTICE](https://github.com/mizorewww/laya-mlx/blob/main/NOTICE). Copyright 2026 laya-mlx contributors. Its NOTICE attributes Laya and its architecture references. | Optional Apple Silicon runtime. Preserve its NOTICE when redistributing derived software. Its upstream compatibility statements do not establish parity for an arbitrary trained checkpoint. |
| [stuntd](https://github.com/bladedevoff/stuntd) | [Apache-2.0](https://github.com/bladedevoff/stuntd/blob/main/LICENSE). | Related work reviewed for per-site learning and deployment lifecycle. Attribution is for research context; inclusion here does not imply its code is bundled. |
| [jevals](https://github.com/openlayer-ai/jevals) | [MIT](https://github.com/openlayer-ai/jevals/blob/main/LICENSE). Copyright 2026 jevals contributors. | Related work reviewed for typed evaluations. Retain MIT copyright and permission text if substantial source is copied. |
| [ReflexBench](https://github.com/brida-ai/reflexbench) | [Apache-2.0](https://github.com/brida-ai/reflexbench/blob/main/LICENSE) for Brida-authored code, documentation and fixtures. Its [third-party policy](https://github.com/brida-ai/reflexbench/blob/main/THIRD_PARTY.md) distinguishes external datasets/models. | Methodological reference. No general permission to redistribute all datasets mentioned in its benchmarks is inferred. |
| [Codex](https://github.com/openai/codex) | [Apache-2.0](https://github.com/openai/codex/blob/main/LICENSE). OpenAI and contributors. | External supported integration target. Codex account access and hosted services have separate terms. An integration does not redistribute Codex or transfer authority over native permissions. |
| [PaperVizAgent](https://github.com/google-research/papervizagent) | [Apache-2.0](https://github.com/google-research/papervizagent/blob/main/LICENSE). Google Research and contributors. | Investigated as a diagram tool. Not required by the free local workflow. No claim that it generated project media. |
| [Jev](https://laya.studio/glossary/jev) | Closed hosted service described by a third-party glossary; no open-weight license was established. | Optional comparator only if separately enabled and authorized. No weights or hosted-service access are bundled; no service fees are assumed authorized. |

The papers cited in [research.md](docs/research.md) are referenced and summarized,
not relicensed or redistributed as full text. Repository source licenses do not
automatically apply to paper PDFs, hosted services, external datasets, trademarks
or every model checkpoint.

Before adding a new bundled model, dataset, copied source file, font or media
asset, record its origin, immutable version where possible, license and required
notice. Keep original benchmark measurements distinct from third-party reports.

## Executed external holdout smoke study

The six-task public-repository mutation study uses Toolz at commit `451af60dec590a6010e2babdbf391ea8f815122f` (https://github.com/pytoolz/toolz) and Funcy at commit `a876c7e1cf11e7c746e91fce4632ebfa93865428` (https://github.com/Suor/funcy), both BSD-3-Clause. Retained small source snippets and mutation anchors are attributed to their respective authors; full upstream notices accompany the executed evidence under `benchmarks/public-repos-v1/licenses/`. Neither project endorses ReflexFoundry. Full upstream source checkouts are not redistributed here.

Training used Laya source commit `b9fe351ce81e2d974bca2bf219c1e4030c0a05ea` and Laya-MLX source commit `ddaf014cf3bd6733ce11219750b150df42ffc86e`. The exact base model revision is recorded in the adapter manifest. The training extra pins Laya by Git commit because this source's declared 0.4.16 version was unavailable on PyPI when verified.
