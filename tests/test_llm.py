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
    CallOptions,
    LLMConfig,
    ModelError,
    OpenAIProvider,
    Part,
    Pricing,
    Reply,
    ResponseCache,
    SpendLedger,
    ToolCall,
    ToolMessage,
    TransientModelError,
    Usage,
    UserMessage,
    estimate_tokens,
    parse_arguments,
    section_chars,
    section_tokens,
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
        "reasoning_tokens": 0,
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


def test_two_ledgers_on_one_log_see_each_other_and_share_the_cap(tmp_path):
    """Two runs at the same time: what one spends counts against the cap of both."""
    first = SpendLedger(tmp_path, budget_usd=1.0)
    second = SpendLedger(tmp_path, budget_usd=1.0)
    usage = dict.fromkeys(
        ("input_tokens", "cached_input_tokens", "cache_write_tokens", "output_tokens"), 0
    )
    entry = {"run": "a", "usage": usage, "cost_usd": 0.4}

    first.record(entry)
    second.record({**entry, "run": "b"})

    assert first.total_usd == pytest.approx(0.8)
    assert second.total_usd == pytest.approx(0.8)
    with pytest.raises(BudgetExceededError) as caught:
        first.check(reserve_usd=0.3)
    assert "spent $0.8000 of $1.00" in str(caught.value)
    first.write_summary()
    assert "Total: $0.8000 of the $1.00 cap." in (tmp_path / "spend.md").read_text("utf-8")


def test_a_line_still_being_written_is_counted_once_it_is_complete(tmp_path):
    ledger = SpendLedger(tmp_path, budget_usd=1.0)
    log = tmp_path / "spend.jsonl"
    log.write_bytes(b'{"cost_usd": 0.25}\n{"cost_usd": 0.5')

    assert ledger.total_usd == pytest.approx(0.25)
    with log.open("ab") as handle:
        handle.write(b"}\n")
    assert ledger.total_usd == pytest.approx(0.75)


# -- retries ------------------------------------------------------------------


def test_transient_errors_are_retried_with_growing_waits(tmp_path):
    client, provider, ledger, sleeps = make_client(
        tmp_path, [TransientModelError("rate limited"), TransientModelError("503"), reply()]
    )

    completion = client.complete("system", [UserMessage("hi")], [])

    assert completion.attempts == 3
    assert completion.retry_errors == ("rate limited", "503")
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

    with pytest.raises(TransientModelError) as caught:
        client.complete("system", [UserMessage("hi")], [])

    assert len(provider.calls) == 3
    assert len(sleeps) == 2
    # The error says how often the request was sent, for the event log.
    assert caught.value.attempts == 3


def test_fatal_errors_are_not_retried(tmp_path):
    client, provider, _, sleeps = make_client(tmp_path, [ModelError("bad request"), reply()])

    with pytest.raises(ModelError):
        client.complete("system", [UserMessage("hi")], [])

    assert len(provider.calls) == 1
    assert sleeps == []


# -- prompt sections ----------------------------------------------------------


def _conversation():
    """Task and first page, one finished step, then the current page as the tail."""
    return [
        UserMessage([Part("task", "T" * 100), Part("observation", "o" * 900)]),
        AssistantMessage("", (ToolCall("c1", "click", {"ref": 1}, "x" * 95),)),
        ToolMessage("c1", [Part("observation", "p" * 600), Part("status", "s" * 50)]),
    ]


def test_sections_count_only_the_last_message_as_the_current_page():
    chars = section_chars("S" * 300, _conversation(), [])

    assert chars == {
        "system": 300,
        "tools": 0,
        "task": 100,
        # The first page is history by now; so is the call (name + arguments).
        "history": 900 + 5 + 95,
        "observation": 600,
        "notes": 0,
        "status": 50,
    }


def test_section_tokens_share_out_the_measured_prompt():
    tokens = section_tokens({"system": 300, "history": 600, "observation": 100}, 500)

    assert tokens == {"system": 150, "history": 300, "observation": 50}
    assert section_tokens({"system": 0}, 500) == {"system": 0}


def test_each_call_logs_its_token_split_and_sections(tmp_path):
    usage = Usage(input_tokens=400, cached_input_tokens=1500, cache_write_tokens=100)
    client, _, _, _ = make_client(tmp_path, [reply(usage=usage)])

    completion = client.complete("S" * 300, _conversation(), [])

    entry = json.loads((tmp_path / "results" / "spend.jsonl").read_text(encoding="utf-8"))
    assert entry["usage"]["input_tokens"] == 400
    assert entry["usage"]["cached_input_tokens"] == 1500
    assert entry["usage"]["cache_write_tokens"] == 100
    assert entry["sections"] == completion.sections
    assert sum(entry["sections"].values()) == pytest.approx(2000, abs=3)
    assert entry["sections"]["history"] > entry["sections"]["observation"] > 0


# -- call options and the response cache ------------------------------------------


def test_the_client_passes_its_settings_to_the_provider(tmp_path):
    client, provider, _, _ = make_client(
        tmp_path, [reply()], max_output_tokens=900, parallel_tools=True, effort="low"
    )

    client.labelled(run="smoke", task_id=7).complete("s", [UserMessage("hi")], [])

    assert provider.calls[0]["options"] == CallOptions(
        max_output_tokens=900,
        cache_key="browser-agent-smoke-7",
        parallel_tools=True,
        effort="low",
    )


def test_a_cached_reply_costs_nothing_and_makes_no_call(tmp_path):
    cache = ResponseCache(tmp_path / "cache")
    answer = reply(text="done")
    first_client, first_provider, _, _ = make_client(tmp_path, [answer], cache=cache)
    paid = first_client.complete("system", _conversation(), [])

    second_client, second_provider, ledger, _ = make_client(tmp_path, [], cache=cache)
    free = second_client.complete("system", _conversation(), [])

    assert len(first_provider.calls) == 1
    assert second_provider.calls == []
    assert free.reply == paid.reply
    assert free.from_cache
    assert not paid.from_cache
    assert free.cost_usd == 0
    assert ledger.total_usd == pytest.approx(paid.cost_usd)
    lines = (tmp_path / "results" / "spend.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["from_response_cache"] for line in lines] == [False, True]


def test_a_different_request_is_not_served_from_the_cache(tmp_path):
    cache = ResponseCache(tmp_path / "cache")
    client, provider, _, _ = make_client(tmp_path, [reply(text="a"), reply(text="b")], cache=cache)

    client.complete("system", _conversation(), [])
    changed = [*_conversation()[:-1], ToolMessage("c1", "another page")]
    other = client.complete("system", changed, [])

    assert len(provider.calls) == 2
    assert other.reply.text == "b"
    assert not other.from_cache


def test_the_cache_is_off_unless_given(tmp_path):
    client, provider, _, _ = make_client(tmp_path, [reply(), reply()])

    client.complete("system", _conversation(), [])
    client.complete("system", _conversation(), [])

    assert len(provider.calls) == 2


def test_cached_replies_keep_their_tool_calls(tmp_path):
    cache = ResponseCache(tmp_path / "cache")
    call = ToolCall("c9", "click", {"ref": 4}, '{"ref": 4}')
    stored = Reply("", (call,), Usage(10, 20, 0, 5), "tool_calls")

    cache.put("k", stored)

    assert cache.get("k") == stored
    assert cache.get("missing") is None


# -- tool-call parsing --------------------------------------------------------


def test_parse_arguments():
    assert parse_arguments('{"ref": 3}') == {"ref": 3}
    assert parse_arguments("") == {}
    assert parse_arguments('{"ref": ') is None
    assert parse_arguments("[1, 2]") is None


# -- providers, with fake SDK clients -------------------------------------------


class _Recorder:
    """Stands in for an SDK endpoint: records requests, returns the queued results."""

    def __init__(self, *results):
        self.results = list(results)
        self.requests = []

    @property
    def request(self):
        return self.requests[-1]

    def create(self, **request):
        self.requests.append(request)
        result = self.results.pop(0) if len(self.results) > 1 else self.results[0]
        if isinstance(result, Exception):
            raise result
        return result


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


def _openai_provider(*results, **kwargs):
    recorder = _Recorder(*results)
    client = SimpleNamespace(chat=SimpleNamespace(completions=recorder))
    return OpenAIProvider(client, "some-model", **kwargs), recorder


HISTORY = [
    UserMessage("Task: x", section="task"),
    AssistantMessage("", (ToolCall("c0", "click", {"ref": 1}, '{"ref": 1}'),)),
    ToolMessage("c0", "Clicked [1]."),
    UserMessage(
        [Part("observation", "Current page:\n[5] button"), Part("status", "Step 2 of 30.")]
    ),
]
PLAIN = CallOptions()


def test_openai_request_and_reply():
    provider, recorder = _openai_provider(_openai_response())
    options = CallOptions(max_output_tokens=500, cache_key="task-7", effort="low")

    result = provider.complete("be brief", HISTORY, TOOLS, options)

    request = recorder.request
    assert request["model"] == "some-model"
    assert request["parallel_tool_calls"] is False
    assert request["max_completion_tokens"] == 500
    assert request["prompt_cache_key"] == "task-7"
    assert request["reasoning_effort"] == "low"
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
    assert request["messages"][4] == {
        "role": "user",
        "content": "Current page:\n[5] button\n\nStep 2 of 30.",
    }
    assert all(tool["function"]["strict"] is True for tool in request["tools"])
    assert result.tool_calls == (ToolCall("c1", "click", {"ref": 4}, '{"ref": 4}'),)
    # Cached tokens are part of prompt_tokens and must not be counted twice.
    assert result.usage == Usage(input_tokens=200, cached_input_tokens=1000, output_tokens=30)


def test_openai_leaves_out_what_was_not_asked_for():
    provider, recorder = _openai_provider(_openai_response())

    provider.complete("s", HISTORY, TOOLS, PLAIN)

    assert "prompt_cache_key" not in recorder.request
    assert "reasoning_effort" not in recorder.request
    assert "max_completion_tokens" not in recorder.request


def test_an_empty_assistant_turn_is_still_a_valid_message():
    history = [UserMessage("go"), AssistantMessage(""), UserMessage("Reply with a tool call.")]
    openai_provider, openai_recorder = _openai_provider(_openai_response())
    anthropic_provider, anthropic_recorder = _anthropic_provider(_anthropic_response())

    openai_provider.complete("s", history, TOOLS, PLAIN)
    anthropic_provider.complete("s", history, TOOLS, PLAIN)

    assert openai_recorder.request["messages"][2] == {"role": "assistant", "content": ""}
    assert anthropic_recorder.request["messages"][1]["content"] == [
        {"type": "text", "text": "(no reply)"}
    ]


def test_openai_minimal_mode_drops_the_newer_fields():
    provider, recorder = _openai_provider(_openai_response(), minimal=True)

    provider.complete("s", HISTORY, TOOLS, CallOptions(500, "task-7", True, "low"))

    request = recorder.request
    assert request["max_tokens"] == 500
    assert "strict" not in request["tools"][0]["function"]
    for field in ("parallel_tool_calls", "prompt_cache_key", "reasoning_effort"):
        assert field not in request


def _status_error(module, name, status):
    request = httpx2.Request("POST", "http://model.test/v1")
    response = httpx2.Response(status, request=request)
    return getattr(module, name)("failed", response=response, body=None)


def test_openai_retries_with_effort_none_when_a_request_is_rejected():
    """gpt-6-luna on this API takes function tools only with reasoning_effort "none"."""
    rejected = _status_error(openai, "BadRequestError", 400)
    provider, recorder = _openai_provider(rejected, _openai_response())
    options = CallOptions(500, "task-7", False, "low")

    result = provider.complete("s", HISTORY, TOOLS, options)
    later = provider.complete("s", HISTORY, TOOLS, options)

    assert result.tool_calls[0].name == "click"
    # Reported with the call in which it happened, and only there.
    assert result.fallbacks == ("effort_downgraded: low -> none",)
    assert later.fallbacks == ()
    first, second, third = recorder.requests
    assert first["reasoning_effort"] == "low"
    # Only the effort changed; strict tools and the cache key are still there.
    assert second["reasoning_effort"] == "none"
    assert second["prompt_cache_key"] == "task-7"
    assert second["tools"][0]["function"]["strict"] is True
    # It stays that way afterwards instead of being rejected on every call.
    assert third["reasoning_effort"] == "none"
    assert len(recorder.requests) == 3


def test_openai_then_drops_the_effort_field_and_last_every_optional_field():
    rejected = _status_error(openai, "BadRequestError", 400)
    provider, recorder = _openai_provider(rejected, rejected, rejected, _openai_response())
    options = CallOptions(500, "task-7", False, "low")

    result = provider.complete("s", HISTORY, TOOLS, options)
    assert result.fallbacks == ("effort_downgraded: low -> omitted", "minimal_mode")
    assert provider.complete("s", HISTORY, TOOLS, options).fallbacks == ()

    first, second, third, fourth, fifth = recorder.requests
    assert [r.get("reasoning_effort") for r in (first, second, third)] == ["low", "none", None]
    assert third["prompt_cache_key"] == "task-7"
    for request in (fourth, fifth):
        assert request["max_tokens"] == 500
        assert "strict" not in request["tools"][0]["function"]
        for name in ("prompt_cache_key", "reasoning_effort", "parallel_tool_calls"):
            assert name not in request
    # What the model is shown is the same in every mode.
    assert fourth["messages"] == first["messages"]


def test_openai_reports_the_first_rejection_when_no_mode_works():
    rejected = _status_error(openai, "BadRequestError", 400)
    provider, recorder = _openai_provider(rejected)

    with pytest.raises(ModelError) as caught:
        provider.complete("s", HISTORY, TOOLS, PLAIN)

    assert caught.value.status_code == 400
    # No effort configured: as is, effort "none", then the plain request.
    assert len(recorder.requests) == 3


@pytest.mark.parametrize(
    ("error", "expected", "attempts"),
    [
        (_status_error(openai, "RateLimitError", 429), TransientModelError, 1),
        (_status_error(openai, "InternalServerError", 503), TransientModelError, 1),
        (
            openai.APITimeoutError(request=httpx2.Request("POST", "http://model.test/v1")),
            TransientModelError,
            1,
        ),
        (_status_error(openai, "AuthenticationError", 401), ModelError, 1),
    ],
)
def test_openai_errors_map_to_retryable_or_fatal(error, expected, attempts):
    provider, recorder = _openai_provider(error)

    with pytest.raises(ModelError) as caught:
        provider.complete("s", HISTORY, TOOLS, PLAIN)

    assert type(caught.value) is expected
    assert len(recorder.requests) == attempts


def _anthropic_provider(*results, **kwargs):
    recorder = _Recorder(*results)
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

    result = provider.complete("be brief", HISTORY, TOOLS, CallOptions(effort="low"))

    request = recorder.request
    mark = {"type": "ephemeral"}
    assert request["system"] == [{"type": "text", "text": "be brief", "cache_control": mark}]
    assert request["max_tokens"] == 16_000
    assert request["tool_choice"] == {"type": "auto", "disable_parallel_tool_use": True}
    assert request["output_config"] == {"effort": "low"}
    assert all(tool["strict"] is True for tool in request["tools"])
    assert all(tool["input_schema"]["additionalProperties"] is False for tool in request["tools"])
    assert [m["role"] for m in request["messages"]] == ["user", "assistant", "user", "user"]
    assert request["messages"][0]["content"] == [
        {"type": "text", "text": "Task: x", "cache_control": mark}
    ]
    assert request["messages"][1]["content"] == [
        {"type": "tool_use", "id": "c0", "name": "click", "input": {"ref": 1}}
    ]
    assert request["messages"][2]["content"] == [
        {
            "type": "tool_result",
            "tool_use_id": "c0",
            "content": "Clicked [1].",
            "is_error": False,
            "cache_control": mark,
        }
    ]
    # The tail: one block per part, none of them marked for caching.
    assert request["messages"][3]["content"] == [
        {"type": "text", "text": "Current page:\n[5] button"},
        {"type": "text", "text": "Step 2 of 30."},
    ]
    assert result.text == "Opening the menu."
    assert result.tool_calls[0].arguments == {"ref": 9}
    assert result.usage == Usage(300, 4000, 50, 80)


def test_anthropic_groups_the_results_of_one_turn():
    calls = (ToolCall("a", "type", {}, "{}"), ToolCall("b", "click", {}, "{}"))
    history = [
        UserMessage("Task: x", section="task"),
        AssistantMessage("", calls),
        ToolMessage("a", "Typed."),
        ToolMessage("b", "Clicked."),
        UserMessage("tail"),
    ]
    provider, recorder = _anthropic_provider(_anthropic_response())

    provider.complete("s", history, TOOLS, PLAIN)

    results = recorder.request["messages"][2]["content"]
    assert [block["tool_use_id"] for block in results] == ["a", "b"]
    # One breakpoint at the end of the history, on the last result.
    assert "cache_control" not in results[0]
    assert "cache_control" in results[1]


def test_anthropic_turn_is_replayed_unchanged():
    """Thinking blocks only survive if the provider's own content goes back as it came."""
    response = _anthropic_response()
    provider, recorder = _anthropic_provider(response)
    first = provider.complete("s", [UserMessage("go")], TOOLS, PLAIN)

    history = [UserMessage("go"), first.message(), ToolMessage("t1", "ok"), UserMessage("tail")]
    provider.complete("s", history, TOOLS, PLAIN)

    assert recorder.request["messages"][1]["content"] is response.content


def test_anthropic_drops_the_effort_setting_when_the_model_rejects_it():
    rejected = _status_error(anthropic, "BadRequestError", 400)
    provider, recorder = _anthropic_provider(rejected, _anthropic_response())

    result = provider.complete("s", HISTORY, TOOLS, CallOptions(effort="low"))
    assert result.fallbacks == ("effort_downgraded: low -> omitted",)
    assert provider.complete("s", HISTORY, TOOLS, CallOptions(effort="low")).fallbacks == ()

    first, second, third = recorder.requests
    assert "output_config" in first
    assert "output_config" not in second
    assert "output_config" not in third


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (_status_error(anthropic, "RateLimitError", 429), TransientModelError),
        (_status_error(anthropic, "InternalServerError", 529), TransientModelError),
        (_status_error(anthropic, "BadRequestError", 400), ModelError),
    ],
)
def test_anthropic_errors_map_to_retryable_or_fatal(error, expected):
    provider, recorder = _anthropic_provider(error)

    with pytest.raises(ModelError) as caught:
        provider.complete("s", [UserMessage("go")], TOOLS, PLAIN)

    assert type(caught.value) is expected
    # Without an effort setting there is nothing to drop, so no second attempt.
    assert len(recorder.requests) == 1


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
    "LLM_REASONING_EFFORT",
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
    # Output is capped and reasoning is at its lowest unless .env says otherwise.
    assert config.max_output_tokens == 4096
    assert config.effort == "low"


def test_output_cap_and_effort_can_be_set_in_env(clean_env):
    for name, value in ENV.items():
        clean_env.setenv(name, value)
    clean_env.setenv("LLM_MAX_OUTPUT_TOKENS", "1500")
    clean_env.setenv("LLM_REASONING_EFFORT", "none")

    config = LLMConfig.from_env()

    assert config.max_output_tokens == 1500
    # "none" is a level some models need to be sent; "omit" sends no setting.
    assert config.effort == "none"
    clean_env.setenv("LLM_REASONING_EFFORT", "omit")
    assert LLMConfig.from_env().effort is None


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
