# AR-TF Scientific Build Type v1

This build type describes deterministic production of a scientific evidence artifact.

External parameters MUST identify source commit, experiment manifest, frozen dataset, registry, folds, scientific configuration, cost model and requested gate set. Resolved dependencies MUST bind immutable digests for every scientific input consumed.

The build MUST fail closed on missing/mismatched lineage, data-integrity failure, leakage, non-reproducibility, missing mandatory gate evidence, or attempted selection-stage holdout/PAPER/TESTNET/LIVE authorization.

Outputs are EvidenceEnvelope JSON, gate adjudication JSON, SLSA provenance statement and, when CI signing is enabled, a Sigstore/Cosign verification bundle. A FROZEN_HOLDOUT_CANDIDATE is not EDGE_VERIFIED and does not authorize execution.
