"""Unit tests for app/intelligence/tension.py."""

from unittest.mock import MagicMock

from app.intelligence.tension import describe, describe_stub
from app.services.resource import GoalTension, ResourceTension


def _tension(
    time_ratio: float = 0.7,
    recovery_ratio: float = 0.6,
    attention_count: int = 2,
    goals: list | None = None,
) -> ResourceTension:
    time_env = 62.0
    tss_env = 320.0
    return ResourceTension(
        time_envelope_hours=time_env,
        recovery_envelope_tss=tss_env,
        total_committed_time_hours=time_env * time_ratio,
        total_committed_tss=tss_env * recovery_ratio,
        time_ratio=time_ratio,
        recovery_ratio=recovery_ratio,
        attention_count=attention_count,
        goals=goals or [],
    )


# ── describe_stub ──────────────────────────────────────────────────────────────

def test_stub_headroom_time():
    result = describe_stub(_tension(time_ratio=0.5))
    assert "headroom" in result.lower()


def test_stub_tight_time():
    result = describe_stub(_tension(time_ratio=0.9))
    assert "tight" in result.lower() or "tightly" in result.lower()


def test_stub_over_committed_time():
    result = describe_stub(_tension(time_ratio=1.2))
    assert "over-committed" in result.lower()


def test_stub_over_committed_recovery():
    result = describe_stub(_tension(recovery_ratio=1.05))
    assert "over-committed" in result.lower()


def test_stub_high_attention():
    result = describe_stub(_tension(attention_count=6))
    assert "high" in result.lower()


def test_stub_no_attention_no_mention():
    result = describe_stub(_tension(attention_count=0))
    assert "open items" not in result


def test_stub_returns_string():
    assert isinstance(describe_stub(_tension()), str)
    assert len(describe_stub(_tension())) > 0


# ── describe ───────────────────────────────────────────────────────────────────

def test_describe_no_client_uses_stub():
    t = _tension(time_ratio=0.5)
    result = describe(t, client=None)
    assert isinstance(result, str)
    assert len(result) > 0


def test_describe_with_client_calls_claude():
    client = MagicMock()
    client.messages.create.return_value.content = [MagicMock(text="You are over-committed.")]
    result = describe(_tension(), client)
    assert result == "You are over-committed."
    client.messages.create.assert_called_once()


def test_describe_strips_whitespace():
    client = MagicMock()
    client.messages.create.return_value.content = [MagicMock(text="  response  ")]
    assert describe(_tension(), client) == "response"


def test_describe_falls_back_on_api_error():
    client = MagicMock()
    client.messages.create.side_effect = Exception("timeout")
    result = describe(_tension(time_ratio=1.3), client)
    assert "over-committed" in result.lower()


def test_describe_prompt_includes_tension_numbers():
    client = MagicMock()
    client.messages.create.return_value.content = [MagicMock(text="ok")]
    describe(_tension(time_ratio=0.8, recovery_ratio=0.9, attention_count=4), client)
    prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "62" in prompt
    assert "320" in prompt
    assert "4" in prompt
