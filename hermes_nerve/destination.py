"""Destination trust: which host a tool call sends data to, computed in code.

Nerve's tri-state criteria route "externally visible" to APPROVAL rather than BLOCK, which
is the right structural answer to the false-positive class: routine egress becomes a prompt,
not a kill. But it is uncalibrated, so whether the engine actually verdicts `git push` as
APPROVAL (safe, noisy) or BLOCK (which needs ask-only to survive) is unmeasured. Supplying
the destination as a code-computed fact removes that ambiguity rather than relying on the
model's reading of the criteria.

Implements Contract 1 of the shared augmentation contract in
`docs/upstream/gate-augmentation-contract-v1.md`. The field names, the null semantics and the
host grammar are fixed by that contract and are shared with the kit.

Three fields are computed; **two are transmitted**:

- `dest_host`: the normalized destination hostname, or None. Computed, kept local for the
  gate event, never sent to the decision engine.
- `dest_known`: whether a destination could be determined at all. Sent.
- `dest_allowlisted`: whether that host is on the operator's allowlist, or None. Sent.

`dest_host` is excluded from the state on purpose. Nerve already transmits redacted tool
arguments, so it would not be a new exposure here, but the measured separation comes from
the allowlist verdict rather than the hostname, so sending it buys no accuracy and one wire
shape across both forks is the point of the contract.

Tri-state polarity is inverted relative to a hazard flag, and this is deliberate:
`dest_allowlisted` is a permission, so unknown (None) must be read as **not permitted**.
An empty or unreadable allowlist therefore yields None for every call, never False: an empty
allowlist is the absence of a policy, not a deny-list.

The extractor is conservative in the direction that cannot suppress a warning. More than one
distinct host in a call yields unknown, never the friendly one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

#: The three fields this module computes. Fixed by the shared contract.
DEST_HOST = "dest_host"
DEST_KNOWN = "dest_known"
DEST_ALLOWLISTED = "dest_allowlisted"

#: The fields that go into the engine state. `dest_host` is not among them.
WIRE_FIELDS: tuple[str, ...] = (DEST_KNOWN, DEST_ALLOWLISTED)

#: Longest host this module will report. Matches the kit's bound and the shared contract.
MAX_HOST_CHARS = 64

_HOST_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
_HOST_RE = re.compile(rf"^(?:{_HOST_LABEL})(?:\.{_HOST_LABEL})*$")
_IPV4_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")

_URL_SCHEMES = ("http://", "https://", "ssh://", "git://", "git+ssh://", "ftp://", "ftps://")

#: `scp`-style remote, `user@host:path`. The leading `user@` distinguishes this from a Windows
#: drive path, which has no `@`. No whitespace and exactly one `@`, so a shell line naming
#: several files cannot match.
_SCP_RE = re.compile(r"^[A-Za-z0-9._-]+@([A-Za-z0-9.-]+):[^\s@]*$")

_QUOTES = "\"'`"

#: Argument keys that name a destination, in the order they are tried.
_URL_KEYS = ("url", "uri", "endpoint", "host", "dest", "destination", "target_url", "webhook")
#: Argument keys holding a command line.
_COMMAND_KEYS = ("command", "cmd", "script", "shell_command")


@dataclass(frozen=True)
class Destination:
    """Tri-state destination trust for one tool call."""

    host: str | None
    known: bool
    allowlisted: bool | None

    def as_state(self) -> dict[str, bool | None]:
        """The wire fields: the two flags, never the host."""
        return {DEST_KNOWN: self.known, DEST_ALLOWLISTED: self.allowlisted}

    def as_event(self) -> dict[str, str | bool | None]:
        """Every field including the host, for the local gate event."""
        return {DEST_HOST: self.host, DEST_KNOWN: self.known, DEST_ALLOWLISTED: self.allowlisted}


UNKNOWN = Destination(host=None, known=False, allowlisted=None)


def normalize_host(value: object) -> str | None:
    """A hostname, lowercased and validated, or None if it is not one.

    Strips a scheme, userinfo, port, path, query and fragment. Never truncates: a host too
    long to report returns None, because a shortened host is a different host.
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if "://" in text:
        text = text.split("://", 1)[1]
    if "@" in text:
        text = text.rsplit("@", 1)[1]
    if text.startswith("["):  # bracketed IPv6 is a documented v2 candidate, not guessed at
        return None
    for sep in ("/", "?", "#"):
        text = text.split(sep, 1)[0]
    if ":" in text:
        head, _, tail = text.partition(":")
        if tail.isdigit():
            text = head
        else:
            return None
    text = text.rstrip(".").lower()
    if not text or len(text) > MAX_HOST_CHARS:
        return None
    if _IPV4_RE.match(text):
        return text if all(int(part) <= 255 for part in text.split(".")) else None
    if not _HOST_RE.match(text):
        return None
    if "." not in text:
        # A single label is not a public destination; `localhost` is loopback, and reporting
        # it would let an allowlist entry cover it.
        return None
    return text


def host_matches(host: str, entry: str) -> bool:
    """Label-boundary match, so `github.com` covers `api.github.com` and not `notgithub.com`."""
    candidate = entry.strip().strip(".").lower()
    if not candidate:
        return False
    subject = host.lower()
    return subject == candidate or subject.endswith("." + candidate)


def is_allowlisted(host: str, allowlist: frozenset[str]) -> bool | None:
    """Whether *host* is on *allowlist*, or None when there is no policy to apply."""
    if not allowlist:
        return None
    return any(host_matches(host, entry) for entry in allowlist)


def _host_from_token(token: str) -> str | None:
    text = token.strip(_QUOTES)
    lowered = text.lower()
    for scheme in _URL_SCHEMES:
        if lowered.startswith(scheme):
            return normalize_host(text)
    if "://" in text:
        return None  # a scheme this module does not treat as egress, for example file://
    scp = _SCP_RE.match(text)
    if scp:
        return normalize_host(scp.group(1))
    return None


def _iter_strings(value: Any, depth: int = 0) -> list[str]:
    """Every string in a nested argument structure, bounded."""
    if depth > 6:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        out: list[str] = []
        for item in value.values():
            out.extend(_iter_strings(item, depth + 1))
        return out
    if isinstance(value, (list, tuple)):
        out = []
        for item in value:
            out.extend(_iter_strings(item, depth + 1))
        return out
    return []


def hosts_in_command(command: str) -> set[str]:
    """Every host named by a command line."""
    hosts: set[str] = set()
    for token in command.split():
        host = _host_from_token(token)
        if host is not None:
            hosts.add(host)
    return hosts


def resolve_destination(
    *,
    tool_name: str = "",
    args: Any = None,
    allowlist: frozenset[str] = frozenset(),
) -> Destination:
    """Compute destination trust for one tool call. Pure; never raises.

    Exactly one distinct host must be determined for `dest_known` to be True. A call naming
    two hosts is reported as unknown rather than as whichever host looks friendly, so a decoy
    cannot talk the gate out of a warning.
    """
    try:
        hosts: set[str] = set()
        if isinstance(args, dict):
            for key in _COMMAND_KEYS:
                value = args.get(key)
                if isinstance(value, str) and value.strip():
                    hosts |= hosts_in_command(value)
            for key in _URL_KEYS:
                value = args.get(key)
                if isinstance(value, str) and value.strip():
                    host = normalize_host(value)
                    if host is not None:
                        hosts.add(host)
        if not hosts:
            # Fall back to scanning the whole structure for a URL-shaped string. This is what
            # catches a destination in a tool this module has no key list for.
            for text in _iter_strings(args):
                host = _host_from_token(text) if text.startswith(_URL_SCHEMES) else None
                if host is not None:
                    hosts.add(host)
        if len(hosts) != 1:
            return UNKNOWN
        host = next(iter(hosts))
        return Destination(host=host, known=True, allowlisted=is_allowlisted(host, allowlist))
    except Exception:  # a bug here must mean unknown, never a wrong host or a False
        return UNKNOWN
