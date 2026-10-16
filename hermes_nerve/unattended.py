"""Unattended (cron) session semantics for the Nerve gate.

Nerve's gate fails toward HUMAN approval on provider failure, and ask-only maps a BLOCK
verdict to approval. Both presume a human exists. In a cron session that is fail-to-nobody:
the run stalls or fails, and nobody ever sees the escalation.

Implements Contract 2 of the shared augmentation contract in
`docs/upstream/gate-augmentation-contract-v1.md`, with the same detection rule and policy
names as the sibling fork.

Detection is deliberately narrow. Either signal is sufficient:

- the task id starts with ``cron:``, or
- ``HERMES_CRON_SESSION`` is set to a true-ish value.

The task-id test is a **prefix** match, never a substring match. A substring match would
exempt an interactive session whose id merely contains ``cron``, which is a silent hole in
the direction of "allowed", so the contract forbids it.

The policy governs escalations that presume a human. It does **not** govern an affirmative
danger verdict: in plain enforce mode a BLOCK still hard-blocks in unattended context, because
that is a judgement rather than a request for a person. Under ask-only, a BLOCK is *by
configuration* an escalation rather than a block, so it is subject to the policy like any
other escalation. Both directions are covered by tests.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum

#: The environment variable Hermes exports for a cron run.
CRON_SESSION_ENV_VAR = "HERMES_CRON_SESSION"

#: The task-id namespace a cron run uses.
CRON_TASK_ID_PREFIX = "cron:"

_TRUEISH = frozenset({"1", "true", "yes", "on"})


class UnattendedPolicy(StrEnum):
    """What the gate does with an escalation when no human is present."""

    #: Do not escalate; continue. The escalation is already recorded in the gate event.
    RECORD = "record"
    #: Hard-block. For installations that prefer broken automation over an unreviewed action.
    BLOCK = "block"
    #: Continue with no record of the suppressed escalation. The weakest option.
    ALLOW = "allow"


#: The default. It satisfies both halves of the requirement: automation keeps working, and the
#: escalation is already written to the durable gate-event stream for an operator to review.
DEFAULT_POLICY = UnattendedPolicy.RECORD

POLICY_ENV_VAR = "HERMES_NERVE_UNATTENDED_POLICY"


def is_unattended(task_id: object = None, environ: object = None) -> bool:
    """Whether this call is running with no human to answer an escalation.

    ``environ`` exists so callers and tests can supply a mapping instead of the process
    environment; it defaults to ``os.environ``.
    """
    if isinstance(task_id, str) and task_id.startswith(CRON_TASK_ID_PREFIX):
        return True
    env = os.environ if environ is None else environ
    raw = ""
    if hasattr(env, "get"):
        value = env.get(CRON_SESSION_ENV_VAR, "")
        raw = value if isinstance(value, str) else ""
    return raw.strip().lower() in _TRUEISH


def policy_from_env(environ: object = None) -> UnattendedPolicy:
    """The configured policy, or the default. An unreadable value never raises."""
    env = os.environ if environ is None else environ
    raw = ""
    if hasattr(env, "get"):
        value = env.get(POLICY_ENV_VAR, "")
        raw = value if isinstance(value, str) else ""
    candidate = raw.strip().lower()
    for policy in UnattendedPolicy:
        if policy.value == candidate:
            return policy
    return DEFAULT_POLICY


@dataclass(frozen=True)
class UnattendedOutcome:
    """What the gate decided to do with a would-be escalation."""

    #: True when the call may proceed without a human.
    proceed: bool
    #: The policy that was applied.
    policy: UnattendedPolicy


def resolve_escalation(
    *,
    unattended: bool,
    policy: UnattendedPolicy = DEFAULT_POLICY,
) -> UnattendedOutcome:
    """Apply the unattended policy to an escalation that presumes a human.

    Call only for escalations. A caller holding an affirmative danger verdict must not route
    it through here: in plain enforce mode that verdict blocks regardless of this policy.
    """
    if not unattended:
        return UnattendedOutcome(proceed=False, policy=policy)
    if policy is UnattendedPolicy.BLOCK:
        return UnattendedOutcome(proceed=False, policy=policy)
    return UnattendedOutcome(proceed=True, policy=policy)
