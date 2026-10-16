# Upstream tracking

This repository is a fork of [`keeltrace/hermes-nerve`](https://github.com/keeltrace/hermes-nerve).
It exists to develop a small set of augmentations and, where they are general, offer them
upstream. It is not a redistribution.

## Baseline

| | |
|---|---|
| Upstream repository | `https://github.com/keeltrace/hermes-nerve` |
| Baseline commit | `d3f3990f9b5c61a72818aa2c1006e70873b7e570` |
| Baseline date | 2026-10-02 |
| Baseline subject | docs: update stable release status to v0.3.1 (#58) |
| License | MIT (see `LICENSE`) |
| Requires Python | `>=3.10` |
| Runtime dependencies | none (release verification uses PyYAML) |
| Declared stable release | `v0.3.1` (tag `3de7d949`) |
| `main` version | `0.3.2.dev0` |

## Remotes

```
origin    https://github.com/pjbeyer/hermes-nerve.git     (this fork)
upstream  https://github.com/keeltrace/hermes-nerve.git   (the project)
```

## Stable-versus-main decision

**Forked from `main`, not from the stable tag `v0.3.1`.** Reasons, in order:

1. Every augmentation targets the Action Gate. `main` carries the current gate code
   including ask-only mode and the tri-state criteria this work extends. `v0.3.1` is
   described by the project as a maintenance release that deliberately excludes ask-only,
   so forking stable would mean re-deriving the surface under change.
2. Upstream development happens on `main`. A contribution against a maintenance tag would
   need rebasing onto `main` before it could be reviewed.
3. The expected reason *not* to fork `main` did not hold up. The evaluation recorded
   genuine completion-handoff regressions on `main`; they do not reproduce here. See below.

`main` is therefore the baseline and carries **no** augmentation. Each augmentation is a
separate commit on a branch named `aug/<topic>`, rebased onto `upstream/main`.

## Local baseline verification

Recorded on macOS 26.7.1 (arm64). The suite is run as upstream's `CONTRIBUTING.md`
specifies, and the result below is the measured one, not the CI claim.

### Python 3.13.16, project virtual environment

| gate | command | result |
|---|---|---|
| tests | `python -m unittest discover -s tests` | `Ran 332 tests`, `FAILED (failures=6)`, rc 1 |
| tests (pytest runner) | `python -m pytest tests -q` | `6 failed, 341 passed in 11.58s`, rc 1 |
| compile | `python -m compileall -q .` | rc 0 |
| release metadata | `python scripts/verify_release.py` | `PASS ... rc=0` |

### The six failures

All six are the same defect and it is a **macOS path-normalization bug**, not a logic bug:

```
AssertionError: PosixPath('/private/var/folders/z7/.../new')
           != PosixPath('/var/folders/z7/.../new')
```

`tests/test_core.py` builds a profile path under `tempfile.TemporaryDirectory()`, then
compares it against `infer_profile_home_from_path()`, which calls
`Path.resolve(strict=False)`. On macOS `/var` is a symlink to `/private/var`, so `resolve()`
returns the `/private`-prefixed real path while the test expects the un-resolved one.

Affected tests, all in `test_core.ProvenanceAndLedgerTests`:

- `test_profile_report_home_infers_named_profile_from_plugin_path` (line 924)
- `test_profile_report_home_uses_deepest_profile_inside_profile_scratch` (line 933)
- `test_profile_report_home_ignores_nested_vendor_profiles_directory` (line 942)
- `test_profile_report_home_ignores_unmarked_nested_dot_hermes_profile` (line 951)
- `test_profile_report_home_accepts_existing_fresh_default_root_profile` (line 968)
- `test_profile_report_home_accepts_marked_alternate_root_profile` (line 977)

These are the six the original evaluation described as portability failures. They are
reproducible, they are the majority of the red, and they are a test-side defect: the
production code is doing the right thing by resolving.

### What did NOT reproduce

The evaluation recorded, against this same commit, `8 failures, 3 errors`, including
"2 failures + 1 error genuine completion-handoff regressions reproducing in isolation"
(`tests/test_terminal_handoff_dev9.py` at lines 157, 168, 349) and "2 errors
environment-specific: ContextEngine tests ... fail inside the Hermes venv".

Re-measured here, none of those five reproduce:

| recorded | re-measured | method |
|---|---|---|
| 2 failures + 1 error in `test_terminal_handoff_dev9` | `Ran 14 tests ... OK` | run alone, and after `test_core` in the same process |
| 2 errors in `test_context_engine_directory_loader` | `Ran 2 tests ... OK` | run alone |
| an error in `test_git_workspace` | not stable | seen once in 2 runs under a Hermes virtualenv, absent in the other and in isolation |

Two honest qualifications, because "it passes for me" is not the same as "it is not a
defect":

- The handoff tests pass **with `agent` importable and without it**, so the earlier red was
  not a missing-dependency artifact. Whatever produced it, it is not present at this commit
  in this environment.
- The single `test_git_workspace` error was seen exactly once in two runs and never in
  isolation. An intermittent failure is a real finding, not a non-finding. It is recorded
  as intermittent and un-reproduced rather than as either a defect or a clean pass.

The net effect on the fork: the case for forking from `main` rather than the stable tag is
stronger than the evaluation assumed, and the "genuine regressions on main" finding should
not be carried forward as established fact. It is not reproduced.

## Release-documentation drift (confirmed)

| document | claims | actual stable | state |
|---|---|---|---|
| `README.md` | stable release is `v0.3.1` | `v0.3.1` | current |
| `CHANGELOG.md` | `## Unreleased - 0.3.2.dev0`, then `## 0.3.0` | `v0.3.1` | **no section for the declared stable release** |
| `BUILD_VERIFICATION.txt` | `v0.2.2` | `v0.3.1` | stale |
| `VERIFICATION.md` | `v0.2.1.2` / `v0.2.2` | `v0.3.1` | stale |

`BUILD_VERIFICATION.txt` also concedes in its own text that the full suite was not used as
release evidence, which is consistent with the red suite being invisible at release time.

## Update procedure

Prefer a rebase over a merge, so upstream history stays linear and the augmentation set
stays a readable patch series.

```sh
git fetch upstream --prune --tags
git checkout main
git merge --ff-only upstream/main          # main is always exactly upstream
git push origin main
```

Then, for each augmentation branch:

```sh
git checkout aug/<topic>
git rebase upstream/main                   # resolve, then re-run the gates below
```

Re-run the full gate set after every rebase. Note that upstream's suite is red on macOS at
the baseline, so "the suite passes" is not available as the pass criterion here. The
criterion is: the six macOS path failures are still the only failures.

### Exercising the procedure

Exercised once at fork creation: `git fetch upstream --prune --tags` succeeded, `main` was
confirmed `--ff-only`-able against `upstream/main` (both at `d3f3990`), and a no-op rebase
of the baseline commit onto `upstream/main` reported `up to date`.

## Divergence inventory

The augmentation branches form a **stacked series**: each builds on the one above it, so the
tip of the last branch contains all of them. Only `aug/dest-trust` branches directly from
`main`. This is deliberate while the work is unreleased; before proposing anything upstream,
each branch is rebased onto `upstream/main` independently and offered as its own pull request,
since a stack cannot be reviewed as one change.

| branch | tip | change | upstreamable |
|---|---|---|---|
| `main` | `0d0252a` | This file, plus the shared gate augmentation contract under `docs/upstream/`. | No. Fork bookkeeping. |
| `aug/dest-trust` | `bacfef5` | Compute destination trust in code and supply it to the decision engine. | Yes. General. |
| `aug/unattended` | `9d349e6` | Detect unattended (cron) sessions and stop emitting escalations that presume a human. | Yes. General. |
| `aug/macos-path-tests` | `b14e959` | Correct the six macOS-failing profile-path tests, and reconcile `CHANGELOG.md`, `BUILD_VERIFICATION.txt` and `VERIFICATION.md` with the declared stable release. | Yes. Test-side portability fix plus documentation fix. |

Still to do, not yet on a branch: publish the labelled corpus and methodology behind the
shipped thresholds. Upstreamable only if that data can be produced honestly.

The shared contract is byte-identical in both forks at every branch tip that contains it
(`sha256 20f7cc6a18cea0b8...`). Both contracts were revised once, and the revision is carried
inside the destination-trust commit rather than as a separate documentation commit, so the
two forks hold the same text at the same point in the series.

Nothing in this fork hardcodes an installation-specific host, path or credential. The
destination allowlist is operator configuration with no shipped default.

## Why this fork has an update discipline

The failure this file exists to prevent is concrete and was observed on this machine: a
catalog-installed plugin with no `.git` directory fell 36 commits behind upstream while
local fixes were re-implemented by hand, so upstream improvements and local fixes had to be
reconciled twice. Nerve's own README warns that catalog installs are SHA-pinned and lag
`main`, which is the same failure waiting to happen. A fork that is not rebased on a
schedule silently becomes that again.

## Contributing back

Upstream's rules are in `CONTRIBUTING.md`. The ones that shaped the augmentations here:

- Contract-first: a new contract or recipe needs explicit allowed outputs, criteria for
  every output, deterministic policy around confidence and failure, a privacy
  classification of state fields, and fixtures for ambiguous and adversarial cases.
- For a bug fix: reproduce the defect first, add a regression test at the narrowest public
  seam, make the smallest root-cause fix, rerun the full offline suite, and keep
  provider/live claims separate from wire-contract verification.
- Avoid silently increasing provider fan-out, weakening fail-open behavior, or making
  unrecoverable evidence less protected.
- Disclose AI assistance and state what was independently verified.
