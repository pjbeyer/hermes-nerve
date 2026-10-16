# Nerve v0.2.1.2 verification receipt

> **Historical stable-release evidence.** This receipt verifies v0.2.1.2 only. It does not verify the current development checkout, and it does not verify the latest stable release, which is **v0.3.1** (`main` identifies as `0.3.2.dev0`). For any current build, use the exact commit plus its GitHub Actions result, or run `python scripts/verify_release.py` locally.

## Build target

- Baseline commit: `4feea5ef45aeb301622f18175ed4cf2e068b99bd` (v0.2.1.1).
- Version target: `0.2.1.2`.
- Patch scope: bounded automatic context curation, complete fail-open containment, anchor idempotence, accurate shadow telemetry, and direct-TypeSafe evidence documentation.

## Verified in the isolated candidate

- Full unit suite: **83/83 PASS**.
- Python bytecode compile: **PASS**.
- Release-equivalent version/registration/schema/trace assertions: **PASS**.
- Registered public surface remains **8 tools**, **7 hook names**, **8 hook callbacks**.
- Preserved vNext implementation trace remains exactly **1,119** sequential requirement IDs with unique verification IDs.
- The literal `scripts/verify_release.py` entrypoint could not run in the minimal MegaMCP runner because PyYAML is absent; the verifier's substantive assertions were rerun independently without modifying the verifier.

## Focused 0.2.1.2 verification

- Exactly 48 candidates remain within the public curation contract.
- 49, 60, and 851 candidate sessions select only 48 per automatic boundary.
- Jev curation failure falls back without escaping into the host turn.
- Jev curation plus fallback failure returns the original messages.
- Existing `NERVE_CONTEXT_ANCHOR` results are not re-curated or nested.
- Unrecoverable evidence consumes no automatic semantic provider capacity.
- Shadow proposals do not increment applied-compaction telemetry.
- Shadow failures are observable while remaining fail-open.
- 48 items fan out to at most 12 semantic assessment requests.

## Preserved release invariants

The candidate retains the v0.2.1 repeated-failure loop breaker/control leases, bounded `nerve_stats`, explicit rehydration, and the v0.2.1.1 deferred schema, self-observation suppression, receipt-backed provenance, and direct TypeSafe wire-contract coverage.

## External live evidence

Issue #1 contains an independent successful direct-TypeSafe account smoke against v0.2.1.1: `transport=typesafe-system-one`, provider `TypeSafe`, model `jev-1.13.0`, verified request/receipt provenance, `ok=true`, and about 299 ms latency.

That evidence belongs to the v0.2.1.1 transport path. Unless the v0.2.1.2 candidate is explicitly rerun with a real TypeSafe credential, this build does not claim a new credentialed live direct-account validation.
