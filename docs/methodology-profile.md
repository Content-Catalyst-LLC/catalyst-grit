# Methodology Profile v1.5.0

The default profile is stored at `methodology/recovery-profile-v1.5.0.json` and identified as `cg-recovery-conditions@1.5.0`.

The weighted component calculation remains stable for longitudinal compatibility. v1.5.0 adds a learning layer around the existing condition map and recovery plan. That layer does not change the recovery score, infer personality, diagnose health, or predict future performance.

## Learning-loop method

The engine:

1. normalizes the user-authored retrospective;
2. reports retrospective completion without inventing missing content;
3. derives candidate patterns only from explicit recorded values;
4. attaches every pattern to exact JSON source paths and evidence values;
5. exposes an adaptation candidate as a proposal, not a command;
6. applies user review decisions to accept, reject, or correct candidates; and
7. preserves uncertainty and interpretation limits in the canonical record.

Project-level pattern aggregation occurs only in the private persistence layer. It counts recurring source-linked observations across records and retains the contributing record and revision IDs. A repeated condition remains a reviewable project observation; it is never converted into a trait or employee rating.

## System-change method

A system-change record must link to at least one source recovery record. It captures the proposed change, owner, expected benefit, pilot dates, review result, and decision history. Decisions are `proposed`, `piloting`, `adopt`, `revise`, `defer`, or `retire`. Events are append-only so a later decision does not rewrite the original proposal or evidence.
