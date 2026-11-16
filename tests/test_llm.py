"""Model client: retries, cost accounting, the spend log and the hard stop."""

from __future__ import annotations

import json
from types import SimpleNamespace

import anthropic
import httpx2
import openai
import pytest

from browser_agent.harness.llm import (
    AnthropicProvider,
    AssistantMessage,
    BudgetExceededError,
    LLMConfig,
    ModelError,
    OpenAIProvider,
    Pricing,
    SpendLedger,
    ToolCall,
    ToolMessage,
    TransientModelError,
    Usage,
    UserMessage,
    estimate_tokens,
    parse_arguments,
)
from browser_agent.harness.tools import TOOLS

from fakes import PRICING, make_client, reply

# -- pricing ------------------------------------------------------------------


def test_cost_prices_each_kind_of_token():
    usage = Usage(
        input_tokens=1_000_000,
        cached_input_tokens=2_000_000,
        cache_write_tokens=400_000,
        output_tokens=100_000,
    )

    # 1.0 + 2 * 0.1 + 0.4 * 1.25 + 0.1 * 10
    assert PRICING.cost(usage) == pytest.approx(2.7)
    assert usage.total_tokens == 3_500_000


def test_cache_prices_default_to_the_input_price():
    usage = Usage(cached_input_tokens=1_000_000, cache_write_tokens=1_000_000)

    assert Pricing(input=3.0, output=15.0).cost(usage) == pytest.approx(6.0)


# -- ledger -------------------------------------------------------------------


def test_every_call_is_logged_with_its_cost(tmp_path):
    usage = Usage(input_tokens=5000, cached_input_tokens=1000, output_tokens=200)
    client, _, ledger, _ = make_client(tmp_path, [reply(usage=usage)])

    completion = client.labelled(run="smoke", task_id=7).complete("system", [UserMessage("hi")], [])

    expected = (5000 * 1.0 + 1000 * 0.1 + 200 * 10.0) / 1_000_000
    assert completion.cost_usd == pytest.approx(expected)
    lines = (tmp_path / "results" / "spend.jsonl").read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[0])
    assert len(lines) == 1
    assert entry["run"] == "smoke"
    assert entry["task_id"] == 7
    assert entry["model"] == "fake-model"
    assert entry["usage"] == {
        "input_tokens": 5000,
        "cached_input_tokens": 1000,
        "cache_write_tokens": 0,
        "output_tokens": 200,
    }
    assert entry["cost_usd"] == pytest.approx(expected)
    assert ledger.total_usd == pytest.approx(expected)


def test_spend_carries_over_between_runs(tmp_path):
    first = SpendLedger(tmp_path, budget_usd=1.0)
    first.record({"run": "a", "usage": Usage(10, 0, 0, 1).__dict__, "cost_usd": 0.4})
    first.record({"run": "b", "usage": Usage(20, 0, 0, 2).__dict__, "cost_usd": 0.3})

    second = SpendLedger(tmp_path, budget_usd=1.0)

    assert second.total_usd == pytest.approx(0.7)
    second.check(0.3)
    with pytest.raises(BudgetExceededError):
        second.check(0.31)


def test_spend_summary_lists_runs_and_the_total(tmp_path):
    ledger = SpendLedger(tmp_path, budget_usd=5.0)
    usage = {
        "input_tokens": 100,
        "cached_input_tokens": 50,
        "cache_write_tokens": 0,
        "output_tokens": 7,
    }
    ledger.record({"run": "smoke", "usage": usage, "cost_usd": 0.25})
    ledger.record({"run": "smoke", "usage": usage, "cost_usd": 0.25})

    ledger.write_summary()

    text = (tmp_path / "spend.md").read_text(encoding="utf-8")
    assert "| smoke | 2 | 300 | 14 | 0.5000 |" in text
    assert "Total: $0.5000 of the $5.00 cap." in text


def test_call_is_refused_before_it_can_pass_the_cap(tmp_path):
    client, provider, ledger, _ = make_client(tmp_path, [reply()], budget_usd=0.05)

    # The reserve for the output alone is 8192 tokens * $10 per million = $0.08.
    with pytest.raises(BudgetExceededError):
        client.complete("system", [UserMessage("hi")], [])

    assert provider.calls == []
    assert ledger.total_usd == 0
    assert not (tmp_path / "results" / "spend.jsonl").exists()


def test_reserve_uses_the_configured_output_limit(tmp_path):
    client, provider, _, _ = make_client(
        tmp_path, [reply()], budget_usd=0.05, max_output_tokens=1000
    )

    client.complete("system", [UserMessage("hi")], [])

    assert len(provider.calls) == 1


def test_estimate_is_on_the_high_side():
    messages = [UserMessage("a" * 3000), ToolMessage("id", "b" * 3000)]

    # 6000 characters of plain text are about 1500 tokens; the estimate must not be below.
    assert estimate_tokens("", messages, []) >= 2000


# -- retries ------------------------------------------------------------------


def test_transient_errors_are_retried_with_growing_waits(tmp_path):
    client, provider, ledger, sleeps = make_client(
        tmp_path, [TransientModelError("rate limited"), TransientModelError("503"), reply()]
    )

    completion = client.complete("system", [UserMessage("hi")], [])

    assert completion.attempts == 3
    assert len(provider.calls) == 3
    assert len(sleeps) == 2
    assert 1.0 <= sleeps[0] <= 2.0
    assert 2.0 <= sleeps[1] <= 4.0
    # Failed attempts cost nothing; only the successful call is logged.
    assert ledger.total_usd == pytest.approx(completion.cost_usd)


def test_retries_give_up(tmp_path):
    client, provider, _, sleeps = make_client(
        tmp_path, [TransientModelError("down")] * 3, max_retries=2
    )

    with pytest.raises(TransientModelError):
        client.complete("system", [UserMessage("hi")], [])

    assert len(provider.calls) == 3
    assert len(sleeps) == 2


def test_fatal_errors_are_not_retried(tmp_path):
    client, provider, _, sleeps = make_client(tmp_path, [ModelError("bad request"), reply()])

    with pytest.raises(ModelError):
        client.complete("system", [UserMessage("hi")], [])

    assert len(provider.calls) == 1
    assert sleeps == []


# -- tool-call parsing --------------------------------------------------------


def test_parse_arguments():
    assert parse_arguments('{"ref": 3}') == {"ref": 3}
    assert parse_arguments("") == {}
    assert parse_arguments('{"ref": ') is None
    assert parse_arguments("[1, 2]") is None


# -- providers, with fake SDK clients -------------------------------------------


class _Recorder:
    def __init__(self, result):
        self.result = result
        self.request = None

    def create(self, **request):
        self.request = request
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _openai_response():
    message = SimpleNamespace(
        content="",
        tool_calls=[
            SimpleNamespace(id="c1", function=SimpleNamespace(name="click", arguments='{"ref": 4}'))
        ],
    )
    usage = SimpleNamespace(
        prompt_tokens=1200,
        completion_tokens=30,
        prompt_tokens_details=SimpleNamespace(cached_tokens=1000, cache_write_tokens=None),
    )
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason="tool_calls")], usage=usage
    )


def _openai_provider(result, **kwargs):
    recorder = _Recorder(result)
    client = SimpleNamespace(chat=SimpleNamespace(completions=recorder))
    return OpenAIProvider(client, "some-model", **kwargs), recorder


HISTORY = [
    UserMessage("Task: x"),
    AssistantMessage("", (ToolCall("c0", "click", {"ref": 1}, '{"ref": 1}'),)),
    ToolMessage("c0", "Clicked [1]."),
]


def test_openai_request_and_reply():
    provider, recorder = _openai_provider(_openai_response())

    result = provider.complete("be brief", HISTORY, TOOLS, 500)

    request = recorder.request
    assert request["model"] == "some-model"
    assert request["parallel_tool_calls"] is False
    assert request["max_completion_tokens"] == 500
    assert request["messages"][0] == {"role": "system", "content": "be brief"}
    assert request["messages"][2]["tool_calls"][0] == {
        "id": "c0",
        "type": "function",
        "function": {"name": "click", "arguments": '{"ref": 1}'},
    }
    assert request["messages"][3] == {
        "role": "tool",
        "tool_call_id": "c0",
        "content": "Clicked [1].",
    }
    assert all(tool["function"]["strict"] is True for tool in request["tools"])
    assert result.tool_calls == (ToolCall("c1", "click", {"ref": 4}, '{"ref": 4}'),)
    # Cached tokens are part of prompt_tokens and must not be counted twice.
    assert result.usage == Usage(input_tokens=200, cached_input_tokens=1000, output_tokens=30)


def test_openai_minimal_mode_drops_the_newer_fields():
    provider, recorder = _openai_provider(_openai_response(), minimal=True)

    provider.complete("s", HISTORY, TOOLS, 500)

    assert "parallel_tool_calls" not in recorder.request
    assert recorder.request["max_tokens"] == 500
    assert "strict" not in recorder.request["tools"][0]["function"]


def _status_error(module, name, status):
    request = httpx2.Request("POST", "http://model.test/v1")
    response = httpx2.Response(status, request=request)
    return getattr(module, name)("failed", response=response, body=None)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (_status_error(openai, "RateLimitError", 429), TransientModelError),
        (_status_error(openai, "InternalServerError", 503), TransientModelError),
        (
            openai.APITimeoutError(request=httpx2.Request("POST", "http://model.test/v1")),
            TransientModelError,
        ),
        (_status_error(openai, "BadRequestError", 400), ModelError),
    ],
)
def test_openai_errors_map_to_retryable_or_fatal(error, expected):
    provider, _ = _openai_provider(error)

    with pytest.raises(ModelError) as caught:
        provider.complete("s", HISTORY, TOOLS, None)

    assert type(caught.value) is expected


def _anthropic_provider(result, **kwargs):
    recorder = _Recorder(result)
    return AnthropicProvider(SimpleNamespace(messages=recorder), "claude-test", **kwargs), recorder


def _anthropic_response():
    content = [
        SimpleNamespace(type="thinking", thinking="", signature="sig"),
        SimpleNamespace(type="text", text="Opening the menu."),
        SimpleNamespace(type="tool_use", id="t1", name="click", input={"ref": 9}),
    ]
    usage = SimpleNamespace(
        input_tokens=300,
        cache_read_input_tokens=4000,
        cache_creation_input_tokens=50,
        output_tokens=80,
    )
    return SimpleNamespace(content=content, usage=usage, stop_reason="tool_use")


def test_anthropic_request_and_reply():
    provider, recorder = _anthropic_provider(_anthropic_response())
    history = [*HISTORY, UserMessage("continue")]

    result = provider.complete("be brief", history, TOOLS, None)

    request = recorder.request
    assert request["system"] == "be brief"
    assert request["max_tokens"] == 16_000
    assert request["tool_choice"] == {"type": "auto", "disable_parallel_tool_use": True}
    assert "cache_control" not in request
    assert all(tool["strict"] is True for tool in request["tools"])
    assert all(tool["input_schema"]["additionalProperties"] is False for tool in request["tools"])
    assert [m["role"] for m in request["messages"]] == ["user", "assistant", "user", "user"]
    assert request["messages"][1]["content"] == [
        {"type": "tool_use", "id": "c0", "name": "click", "input": {"ref": 1}}
    ]
    assert request["messages"][2]["content"] == [
        {"type": "tool_result", "tool_use_id": "c0", "content": "Clicked [1].", "is_error": False}
    ]
    assert result.text == "Opening the menu."
    assert result.tool_calls[0].arguments == {"ref": 9}
    assert result.usage == Usage(300, 4000, 50, 80)


def test_anthropic_turn_is_replayed_unchanged():
    """Thinking blocks only survive if the provider's own content goes back as it came."""
    response = _anthropic_response()
    provider, recorder = _anthropic_provider(response)
    first = provider.complete("s", [UserMessage("go")], TOOLS, None)

    provider.complete(
        "s", [UserMessage("go"), first.message(), ToolMessage("t1", "ok")], TOOLS, None
    )

    assert recorder.request["messages"][1]["content"] is response.content


def test_anthropic_prompt_caching_is_a_switch():
    provider, recorder = _anthropic_provider(_anthropic_response(), prompt_caching=True)

    provider.complete("s", [UserMessage("go")], TOOLS, None)

    assert recorder.request["cache_control"] == {"type": "ephemeral"}


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (_status_error(anthropic, "RateLimitError", 429), TransientModelError),
        (_status_error(anthropic, "InternalServerError", 529), TransientModelError),
        (_status_error(anthropic, "BadRequestError", 400), ModelError),
    ],
)
def test_anthropic_errors_map_to_retryable_or_fatal(error, expected):
    provider, _ = _anthropic_provider(error)

    with pytest.raises(ModelError) as caught:
        provider.complete("s", [UserMessage("go")], TOOLS, None)

    assert type(caught.value) is expected


# -- configuration ------------------------------------------------------------

ENV = {
    "LLM_API_KEY": "test-key",
    "LLM_MODEL": "some-model",
    "LLM_PRICE_INPUT_PER_MTOK": "2",
    "LLM_PRICE_OUTPUT_PER_MTOK": "8",
    "BUDGET_USD": "5",
}
ALL_VARIABLES = (
    *ENV,
    "LLM_PROVIDER",
    "LLM_BASE_URL",
    "LLM_PRICE_CACHED_INPUT_PER_MTOK",
    "LLM_PRICE_CACHE_WRITE_PER_MTOK",
    "LLM_MAX_OUTPUT_TOKENS",
    "LLM_OPENAI_MINIMAL",
)


@pytest.fixture
def clean_env(monkeypatch):
    for name in ALL_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_config_from_env(clean_env):
    for name, value in ENV.items():
        clean_env.setenv(name, value)
    clean_env.setenv("LLM_PRICE_CACHED_INPUT_PER_MTOK", "0.5")

    config = LLMConfig.from_env()

    assert config.provider == "openai"
    assert config.pricing == Pricing(input=2.0, output=8.0, cached_input=0.5, cache_write=None)
    assert config.budget_usd == 5.0
    assert config.base_url is None
    assert "test-key" not in repr(config)


def test_claude_models_default_to_the_anthropic_provider(clean_env):
    for name, value in {**ENV, "LLM_MODEL": "claude-something"}.items():
        clean_env.setenv(name, value)

    assert LLMConfig.from_env().provider == "anthropic"


def test_missing_settings_are_named(clean_env):
    clean_env.setenv("LLM_MODEL", "some-model")

    with pytest.raises(ModelError) as caught:
        LLMConfig.from_env()

    message = str(caught.value)
    assert "LLM_API_KEY" in message
    assert "LLM_PRICE_INPUT_PER_MTOK" in message
    assert "BUDGET_USD" in message
    assert "LLM_MODEL" not in message
