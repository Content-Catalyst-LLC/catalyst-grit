# Recovery Planning and Action Management — v1.4.0

Catalyst Grit turns a recovery record into an executable plan without converting the plan into a performance rating.

## Action contract

Each normalized action has a stable `action_key`, title, status, owner, target date, planning horizon, expected effect, required support, dependencies, effort, urgency, completion evidence, reassessment trigger, blocked reason, and escalation path.

Supported statuses are `planned`, `in_progress`, `blocked`, `completed`, `paused`, `deferred`, and `cancelled`. A blocked action requires a reason describing the missing support or dependency. A completed action requires evidence. These requirements prevent status changes from becoming untraceable assertions.

## Executable plan view

`findings.recovery_plan` provides:

- the smallest recoverable next step;
- actions grouped into 24-hour, 72-hour, 7-day, and longer-term horizons;
- internal and unresolved external dependencies;
- continue, reduce-scope, pause, delegate, or escalate decisions;
- a dated checkpoint, success signal, and reassessment trigger;
- blocker and escalation logs;
- changed assumptions and non-punitive review signals;
- compatibility defaults applied to older records.

At least one action must have an owner and every plan must have a dated checkpoint. Older imports without those values receive explicit defaults listed in `compatibility_defaults`.

## Persistence and history

Migration 003 enriches persisted actions and adds append-only `action_events`, `blockers`, and `reassessments`. Action status changes never erase prior events. A reassessment generates a new canonical record revision, compares the prior and current plan, carries unresolved work forward, and can complete the associated checkpoint.

Past-target and blocked states are support signals. They are not lateness scores, character judgments, employee ratings, or automated performance findings.
