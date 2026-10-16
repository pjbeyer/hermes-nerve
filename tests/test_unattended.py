"""Unattended (cron) session semantics for the Nerve gate.

Nerve fails toward HUMAN approval on provider failure, and ask-only maps a BLOCK verdict to
approval. Both presume a human exists. In a cron session that is fail-to-nobody: the run
stalls or fails and nobody sees the escalation. `HERMES_CRON_SESSION` appeared nowhere in this
repository and no code read any session-type variable.

These tests cover the detection rule (both signals, prefix only), the policy, and the
precedence rule that matters most: in plain enforce mode an affirmative danger verdict still
hard-blocks in unattended context.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hermes_nerve import engine, gate
from hermes_nerve.unattended import (
    CRON_SESSION_ENV_VAR,
    DEFAULT_POLICY,
    POLICY_ENV_VAR,
    UnattendedPolicy,
    is_unattended,
    policy_from_env,
    resolve_escalation,
)


def _result(value: str, confidence: float = 0.95, probabilities: dict | None = None):
    return engine.DecisionResult(
        value,
        confidence,
        probabilities if probabilities is not None else {"ALLOW": 0.99, "APPROVAL": 0.005, "BLOCK": 0.005},
        "jev-test",
        1.0,
        "x",
    )


# --------------------------------------------------------------------------- detection


class DetectionTests(unittest.TestCase):
    def test_prefix_detects_cron_task_ids(self) -> None:
        for task_id in ("cron:nightly-sync:run-7", "cron:", "cron:job"):
            self.assertTrue(is_unattended(task_id, {}), task_id)

    def test_substring_and_near_misses_are_not_unattended(self) -> None:
        # A substring match would exempt an interactive session whose id merely contains
        # "cron", which is a silent hole in the direction of "allowed".
        for task_id in (None, "", "interactive-session", "session-cron-like", "cron",
                        "cronish:job", "x:cron:job"):
            self.assertFalse(is_unattended(task_id, {}), repr(task_id))

    def test_env_var_trueish_detects_unattended(self) -> None:
        for value in ("1", "true", "TRUE", "yes", "on", " true "):
            self.assertTrue(is_unattended(None, {CRON_SESSION_ENV_VAR: value}), value)

    def test_env_var_anything_else_is_attended(self) -> None:
        for value in ("", "0", "false", "no", "off", "maybe", "2", "cron"):
            self.assertFalse(is_unattended(None, {CRON_SESSION_ENV_VAR: value}), value)

    def test_either_signal_suffices(self) -> None:
        self.assertTrue(is_unattended("cron:j:r", {}))
        self.assertTrue(is_unattended(None, {CRON_SESSION_ENV_VAR: "1"}))
        self.assertTrue(is_unattended("interactive", {CRON_SESSION_ENV_VAR: "1"}))
        self.assertFalse(is_unattended("interactive", {}))

    def test_never_raises(self) -> None:
        for task_id in (1, [], {}, object(), None):
            self.assertFalse(is_unattended(task_id, {}))


# --------------------------------------------------------------------------- policy


class PolicyTests(unittest.TestCase):
    def test_default_is_record(self) -> None:
        self.assertIs(DEFAULT_POLICY, UnattendedPolicy.RECORD)
        self.assertIs(policy_from_env({}), UnattendedPolicy.RECORD)

    def test_policy_is_configurable(self) -> None:
        for value in ("record", "block", "allow", "BLOCK", " Record "):
            self.assertIs(policy_from_env({POLICY_ENV_VAR: value}),
                          UnattendedPolicy(value.strip().lower()))

    def test_an_unreadable_policy_falls_back_to_the_default(self) -> None:
        for value in ("", "nonsense", "true", "1"):
            self.assertIs(policy_from_env({POLICY_ENV_VAR: value}), DEFAULT_POLICY)

    def test_attended_context_always_escalates(self) -> None:
        for policy in UnattendedPolicy:
            self.assertFalse(resolve_escalation(unattended=False, policy=policy).proceed)

    def test_record_proceeds(self) -> None:
        self.assertTrue(resolve_escalation(unattended=True, policy=UnattendedPolicy.RECORD).proceed)

    def test_block_does_not_proceed(self) -> None:
        self.assertFalse(resolve_escalation(unattended=True, policy=UnattendedPolicy.BLOCK).proceed)

    def test_allow_proceeds(self) -> None:
        self.assertTrue(resolve_escalation(unattended=True, policy=UnattendedPolicy.ALLOW).proceed)

    def test_configure_accepts_a_policy_and_rejects_nonsense(self) -> None:
        gate.configure(unattended_policy="block")
        self.assertIs(gate.unattended_policy(), UnattendedPolicy.BLOCK)
        gate.configure(unattended_policy="nonsense")
        # An unreadable value falls back to the default rather than to something arbitrary.
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIs(gate.unattended_policy(), DEFAULT_POLICY)
        gate.configure(unattended_policy=None)


# --------------------------------------------------------------------------- through the gate


class GateEscalationTests(unittest.TestCase):
    """Every escalation that presumes a human must be policy-aware."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.events = Path(self._td.name) / "gate-events.jsonl"
        patcher = mock.patch.dict(
            os.environ,
            {"HERMES_NERVE_GATE_EVENTS": str(self.events)},
            clear=False,
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop(POLICY_ENV_VAR, None)
        os.environ.pop(CRON_SESSION_ENV_VAR, None)
        gate.configure(mode="enforce", dest_allowlist=None, unattended_policy="record")
        self.addCleanup(lambda: gate.configure(mode="off", dest_allowlist=None, unattended_policy=None))

    def _rows(self) -> list[dict]:
        if not self.events.is_file():
            return []
        return [json.loads(line) for line in self.events.read_text().splitlines()]

    def _with_verdict(self, result, task_id):
        original = gate.evaluate_tool_call
        gate.evaluate_tool_call = lambda **kwargs: result
        try:
            return gate.pre_tool_call("terminal", {"command": "make build"}, task_id)
        finally:
            gate.evaluate_tool_call = original

    # --- escalation: APPROVAL verdict
    def test_approval_verdict_suppressed_in_cron_and_recorded(self) -> None:
        out = self._with_verdict(_result("APPROVAL"), "cron:job:run")
        self.assertIsNone(out, "the escalation should be suppressed, not emitted")
        rows = [r for r in self._rows() if r.get("action") == "unattended-suppressed"]
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["unattended"])
        self.assertTrue(rows[0]["would_escalate"])
        self.assertEqual(rows[0]["unattended_policy"], "record")

    def test_approval_verdict_escalates_interactively(self) -> None:
        out = self._with_verdict(_result("APPROVAL"), "interactive-1")
        self.assertIsNotNone(out)
        self.assertEqual(out["action"], "approve")

    def test_approval_verdict_hard_blocks_under_block_policy(self) -> None:
        gate.configure(mode="enforce", unattended_policy="block")
        out = self._with_verdict(_result("APPROVAL"), "cron:job:run")
        self.assertIsNotNone(out)
        self.assertEqual(out["action"], "approve")

    # --- escalation: low confidence
    def test_low_confidence_suppressed_in_cron(self) -> None:
        out = self._with_verdict(_result("ALLOW", confidence=0.10), "cron:job:run")
        self.assertIsNone(out)
        rows = [r for r in self._rows() if r.get("action") == "unattended-suppressed"]
        self.assertEqual(rows[0]["reason"], "nerve:low-confidence")

    # --- escalation: low p(ALLOW)
    def test_low_allow_probability_suppressed_in_cron(self) -> None:
        out = self._with_verdict(
            _result("ALLOW", probabilities={"ALLOW": 0.50, "APPROVAL": 0.50}), "cron:job:run"
        )
        self.assertIsNone(out)
        rows = [r for r in self._rows() if r.get("action") == "unattended-suppressed"]
        self.assertEqual(rows[0]["reason"], "nerve:low-allow-probability")

    # --- escalation: provider failure
    def test_provider_failure_suppressed_in_cron(self) -> None:
        def _boom(**kwargs):
            raise RuntimeError("provider down")

        original = gate.evaluate_tool_call
        gate.evaluate_tool_call = _boom
        try:
            out = gate.pre_tool_call("terminal", {"command": "make build"}, "cron:job:run")
        finally:
            gate.evaluate_tool_call = original
        self.assertIsNone(out, "fail-to-human became fail-to-nobody in cron")
        rows = [r for r in self._rows() if r.get("action") == "unattended-suppressed"]
        self.assertEqual(rows[0]["reason"], "nerve:provider-unavailable")

    def test_provider_failure_still_fails_to_human_interactively(self) -> None:
        def _boom(**kwargs):
            raise RuntimeError("provider down")

        original = gate.evaluate_tool_call
        gate.evaluate_tool_call = _boom
        try:
            out = gate.pre_tool_call("terminal", {"command": "make build"}, "interactive-1")
        finally:
            gate.evaluate_tool_call = original
        self.assertIsNotNone(out)
        self.assertEqual(out["rule_key"], "nerve:provider-unavailable")

    # --- precedence: an affirmative danger verdict still blocks
    def test_enforce_block_still_hard_blocks_in_cron(self) -> None:
        # The policy governs escalations, not verdicts. A gate that affirmatively judged the
        # call dangerous must still block, because that is a judgement rather than a request
        # for a person.
        out = self._with_verdict(_result("BLOCK"), "cron:job:run")
        self.assertIsNotNone(out)
        self.assertEqual(out["action"], "block")

    def test_enforce_block_still_hard_blocks_under_record_and_allow_policies(self) -> None:
        for policy in ("record", "allow"):
            gate.configure(mode="enforce", unattended_policy=policy)
            out = self._with_verdict(_result("BLOCK"), "cron:job:run")
            self.assertIsNotNone(out, policy)
            self.assertEqual(out["action"], "block", policy)

    def test_ask_only_block_is_an_escalation_so_the_policy_applies(self) -> None:
        # Under ask-only a BLOCK is by configuration an escalation rather than a block, so it
        # is subject to the policy like any other escalation.
        gate.configure(mode="ask-only", unattended_policy="record")
        out = self._with_verdict(_result("BLOCK"), "cron:job:run")
        self.assertIsNone(out)
        rows = [r for r in self._rows() if r.get("action") == "unattended-suppressed"]
        self.assertEqual(len(rows), 1)

    def test_ask_only_block_still_escalates_interactively(self) -> None:
        gate.configure(mode="ask-only", unattended_policy="record")
        out = self._with_verdict(_result("BLOCK"), "interactive-1")
        self.assertIsNotNone(out)
        self.assertEqual(out["action"], "approve")

    # --- a clean allow is untouched
    def test_a_clean_allow_is_not_an_escalation(self) -> None:
        out = self._with_verdict(_result("ALLOW"), "cron:job:run")
        self.assertIsNone(out)
        self.assertEqual([r for r in self._rows() if r.get("action") == "unattended-suppressed"], [])

    def test_env_var_signal_alone_suppresses(self) -> None:
        with mock.patch.dict(os.environ, {CRON_SESSION_ENV_VAR: "1"}, clear=False):
            out = self._with_verdict(_result("APPROVAL"), None)
        self.assertIsNone(out)

    def test_a_session_id_merely_containing_cron_is_still_attended(self) -> None:
        out = self._with_verdict(_result("APPROVAL"), "my-cron-ish-session")
        self.assertIsNotNone(out)

    def test_shadow_and_advisory_are_unaffected(self) -> None:
        # advisory returns before any escalation logic; the policy has nothing to suppress.
        gate.configure(mode="advisory", unattended_policy="block")
        self.assertIsNone(self._with_verdict(_result("APPROVAL"), "cron:job:run"))

    def test_rule_keys_stay_stable_and_free_of_measured_values(self) -> None:
        # rule_key is the approval-cache grain: a key carrying a float would mint a new key on
        # every call and fragment it. The numbers belong in the message.
        out = self._with_verdict(_result("ALLOW", confidence=0.10), "interactive-1")
        self.assertEqual(out["rule_key"], "nerve:low-confidence")
        self.assertIn("0.100", out["message"])

    def test_report_counts_the_suppressed_action(self) -> None:
        self._with_verdict(_result("APPROVAL"), "cron:job:run")
        summary = gate.report(self.events)
        self.assertGreaterEqual(summary["by_action"].get("unattended-suppressed", 0), 1)


if __name__ == "__main__":
    unittest.main()
