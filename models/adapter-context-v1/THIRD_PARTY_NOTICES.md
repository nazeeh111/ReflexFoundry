# Third-party notices


License observations below were checked against the linked upstream files on
26 October 2026. Dependencies and model weights retain their own licenses;
ReflexFoundry's license does not relicense them. Distribution must retain any
notices required by the exact versions actually included.

| Project or material | License and attribution | Use and redistribution boundary |
| --- | --- | --- |
| [Laya weights](https://huggingface.co/convaiinnovations/laya) | The model card declares Apache-2.0. Convai Innovations. | Downloaded checkpoints are separate artifacts. Record their repository/revision and training provenance. A trained derivative must identify its base and preserve applicable model notices and license. Do not assume every model on a hosting service has this license. |
| [Laya-MLX](https://github.com/mizorewww/laya-mlx) | [Apache-2.0](https://github.com/mizorewww/laya-mlx/blob/main/LICENSE), with [NOTICE](https://github.com/mizorewww/laya-mlx/blob/main/NOTICE). Copyright 2026 laya-mlx contributors. Its NOTICE attributes Laya and its architecture references. | Optional Apple Silicon runtime. Preserve its NOTICE when redistributing derived software. Its upstream compatibility statements do not establish parity for an arbitrary trained checkpoint. |

Base model: `convaiinnovations/laya` revision `7b928d828b7b0e022f929d9bd2e44165aa270148`.
The complete Apache-2.0 model license is in [LICENSE](LICENSE).
Training used Laya source commit `b9fe351ce81e2d974bca2bf219c1e4030c0a05ea` and Laya-MLX source commit `ddaf014cf3bd6733ce11219750b150df42ffc86e`. The exact base model revision is also recorded in the adapter manifest.
