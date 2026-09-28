"""What counts as a *transient* failure when calling OpenRouter - shared by
the chat-completion calls in er.agent.orchestrator and the Decisions call in
er.agent.verifier, so both retry exactly the same things.

Both have been seen in practice, and in both cases the very next calls
succeeded: a chat call whose connection dropped before any reply
(httpx.RemoteProtocolError, "Server disconnected without sending a
response."), and a Jev call that couldn't open a connection in time
(httpx.ConnectTimeout).
"""

from __future__ import annotations

import httpx

# Rate limited, or the gateway / upstream provider failing rather than
# rejecting the request. Anything else - above all a 400 such as "input
# exceeds 8 MB" - fails identically however many times it is sent.
TRANSIENT_STATUSES = frozenset({429, 502, 503, 504})

# Failures before any response exists: nothing was answered, so re-sending is
# the only way to get an answer. ReadTimeout is deliberately absent - the
# remote side was already working for the full timeout, and retrying would
# double the wait on a call that is probably just too big.
TRANSIENT_TRANSPORT: tuple[type[Exception], ...] = (
    httpx.RemoteProtocolError,
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadError,
    httpx.WriteError,
    httpx.PoolTimeout,
)


def is_transient(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in TRANSIENT_STATUSES
    return isinstance(exc, TRANSIENT_TRANSPORT)


def timeout(total_seconds: float, connect_seconds: float) -> httpx.Timeout:
    """A request timeout with a much shorter cap on *connecting*. Connecting to
    openrouter.ai normally takes ~0.07s; a connection that isn't open within a
    few seconds is not going to open, and waiting the full request timeout for
    it (30s for Jev, 90s for chat) just delays the retry that will work."""
    return httpx.Timeout(total_seconds, connect=connect_seconds)


def error_message(response: httpx.Response) -> str | None:
    """The provider's own explanation of an HTTP error. "HTTP 400" alone sent
    the first diagnosis of an oversized request down the wrong path; the body
    said "The total text input size exceeds 8 MB" the whole time."""
    try:
        body = response.json()
    except ValueError:
        text = response.text.strip()
        return text[:300] or None
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict) and error.get("message"):
        return str(error["message"])[:300]
    if isinstance(body, dict) and body.get("message"):
        return str(body["message"])[:300]
    return None
