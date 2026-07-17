# Methodology Profile v1.2.0

The default profile is stored at `methodology/recovery-profile-v1.2.0.json`.

## Formula

Each 1–10 positive capacity scale is normalized with `(value - 1) / 9`. Impact and pressure buffers use `(10 - value) / 9`. Action readiness reaches full value at four distinct actions. Constraint manageability averages controllability values: controllable `1.0`, influence `0.65`, unknown `0.4`, limited `0.25`; no listed constraints defaults to `1.0`.

The weighted component values are summed and rounded half-up to one decimal place. Default thresholds are stable `75`, focused support `55`, and fragile `35`.

## Interpretation

The score is a summary of recorded conditions. Component scores and their explanations are primary. The composite must not be interpreted as character, diagnosis, predicted success, or employee performance.

## Configuration

A custom profile must identify its profile ID and version, use `weighted-components-v1`, include every component, total exactly 100 weight points, and use descending thresholds within 0–100.
