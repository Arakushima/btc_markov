# Protocol index: separate prediction from structural diagnostics

The original combined draft was split on October 3, 2026 at the user's request.

- [Part A: prediction and the single holdout evaluation](protocol_part_a.md) contains the three rolling forecasters, maturity/eligibility rules, scores, paired bootstrap, primary decision, archive fallback, and evaluation gate. Freeze after its implementation and tests pass; target October 5 at the latest.
- [Part B: structural diagnostics](protocol_part_b.md) contains CK, residence times, and Holm. It uses development data only (2020–2023), may finish after Part A freezes, and cannot alter the frozen predictive procedure.

The reason for this order is that predictive evaluation does not require a structural diagnostic to finish or pass. A single predictive freeze must not be delayed by an independent development analysis. The 2023 sample was already used and remains development data. All holdout isolation rules remain in force until Part A's scheduled gate permits evaluation.

The September fallback is now specified in Part A before freezing: if September 2026 monthly archives are unavailable at the October 7 availability check, use outcomes through August 31, origins through August 26, and disclose this in the report. The same interval applies to all three assets. Checksum errors and gaps block evaluation.

See [current status](status.md) for the actual freeze commit and completed validation; do not infer a completed freeze or evaluation from planned dates.
