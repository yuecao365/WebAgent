"""The OpenAI Responses API adapter, against replies recorded from the real API.

tests/fixtures/responses_api.json holds two consecutive calls of one task at low
effort; responses_api_reasoning.json holds two at high effort, where the model
reasoned. Ids and the encrypted reasoning were replaced by placeholders.
"""

from __future__ import annotations

import copy
import itertools
import json
from types import SimpleNamespace

import httpx2
import openai
import pytest
from openai.types.responses import Response

from browser_agent.harness.events import EventLog
from browser_agent.harness.llm import (
    AssistantMessage,
    CallOptions,
    LLMClient,
    LLMConfig,
    ModelError,
    OpenAIProvider,
    OpenAIResponsesProvider,
    Part,
    Pricing,
    SpendLedger,
    ToolCall,
    ToolMessage,
    TransientModelError,
    Usage,
    UserMessage,
    build_provider,
)
from browser_agent.harness.loop import AgentLoop, LoopConfig
from browser_agent.harness.tools import TOOLS

from fakes import FINISH_OK, PRICING, FakeExecutor, load_fixture


def recorded(name):
    """The exchanges of a fixture, with each response as the SDK's own type."""
    exchanges = load_fixture(name)
    for exchange in exchanges:
        # Dropped when the fixture was scrubbed; the SDK type requires them.
        body = {"tools": [], "metadata": {}, "instructions": None, **exchange["response"]}
        exchange["parsed"] = Response.model_validate(body)
    return exchanges


class Replay:
    """Stands in for the SDK: records requests and returns the queued results."""

    def __init__(self, *results):
        self.results = list(results)
        self.requests = []
        self.responses = self

    def create(self, **request):
        self.requests.append(copy.deepcopy(request))
        result = self.results.pop(0) if len(self.results) > 1 else self.results[0]
        if isinstance(result, Exception):
            raise result
        return result


TASK = UserMessage("Task: Get the grand total of order 000000299.", section="task")
OPTIONS = CallOptions(max_output_tokens=4096, cache_key="browser-agent-r-7", effort="low")


def tail(text, step):
    return UserMessage([Part("observation", text), Part("status", f"Step {step} of 30.")])


def test_a_recorded_tool_call_is_parsed():
    first, _ = recorded("responses_api.json")
    provider = OpenAIResponsesProvider(Replay(first["parsed"]), "gpt-6-luna")

    reply = provider.complete("system", [TASK, tail("page", 1)], TOOLS, OPTIONS)

    assert [(c.id, c.name, c.arguments) for c in reply.tool_calls] == [
        ("call_001", "click", {"ref": 31})
    ]
    assert reply.text == ""
    assert reply.stop_reason == "tool_calls"
    # 1305 input tokens, of which 1302 were written to the cache and none read from it.
    assert reply.usage == Usage(
        input_tokens=3, cached_input_tokens=0, cache_write_tokens=1302, output_tokens=17
    )


def test_cached_input_is_split_out_of_the_recorded_usage():
    _, second = recorded("responses_api.json")
    provider = OpenAIResponsesProvider(Replay(second["parsed"]), "gpt-6-luna")

    reply = provider.complete("system", [TASK, tail("page", 2)], TOOLS, OPTIONS)

    assert reply.usage == Usage(
        input_tokens=3, cached_input_tokens=1174, cache_write_tokens=123, output_tokens=39
    )
    assert reply.tool_calls[0].name == "finish"
    assert json.loads(reply.tool_calls[0].arguments["retrieved_data"]) == [219.40]


def test_reasoning_tokens_are_reported_apart_from_output():
    first, second = recorded("responses_api_reasoning.json")
    provider = OpenAIResponsesProvider(Replay(first["parsed"], second["parsed"]), "gpt-6-luna")

    reply = provider.complete("system", [TASK, tail("page", 1)], TOOLS, OPTIONS)

    assert reply.usage.reasoning_tokens == 40
    assert reply.usage.output_tokens == 60
    # Reasoning is part of the output and priced as output, not on top of it.
    assert reply.usage.total_tokens == 3 + 1330 + 60
    assert PRICING.cost(reply.usage) == pytest.approx((3 * 1.0 + 1330 * 1.25 + 60 * 10.0) / 1e6)


def test_request_shape():
    first, _ = recorded("responses_api.json")
    sdk = Replay(first["parsed"])
    options = CallOptions(900, "browser-agent-r-7", parallel_tools=True, effort="low")

    OpenAIResponsesProvider(sdk, "gpt-6-luna").complete("be brief", [TASK], TOOLS, options)

    request = sdk.requests[0]
    assert request["model"] == "gpt-6-luna"
    assert request["instructions"] == "be brief"
    assert request["reasoning"] == {"effort": "low"}
    assert request["prompt_cache_key"] == "browser-agent-r-7"
    assert request["max_output_tokens"] == 900
    assert request["parallel_tool_calls"] is True
    # Stateless: nothing stored, reasoning returned encrypted for replay.
    assert request["store"] is False
    assert request["include"] == ["reasoning.encrypted_content"]
    assert [tool["name"] for tool in request["tools"]] == [spec.name for spec in TOOLS]
    assert all(tool["type"] == "function" and tool["strict"] is True for tool in request["tools"])
    assert request["input"] == [{"role": "user", "content": TASK.content}]


def test_the_next_request_replays_the_turn_as_the_api_accepted_it():
    """The second recorded request was accepted by the real API; rebuild it exactly."""
    first, second = recorded("responses_api_reasoning.json")
    sdk = Replay(first["parsed"], second["parsed"])
    provider = OpenAIResponsesProvider(sdk, "gpt-6-luna")
    sent = first["request"]["input"]
    task = UserMessage(sent[0]["content"], section="task")
    first_tail = UserMessage(sent[1]["content"])

    reply = provider.complete("system", [task, first_tail], TOOLS, OPTIONS)
    accepted = second["request"]["input"]
    history = [
        task,
        reply.message(),
        ToolMessage(reply.tool_calls[0].id, accepted[3]["output"]),
        UserMessage(accepted[4]["content"]),
    ]
    provider.complete("system", history, TOOLS, OPTIONS)

    assert sdk.requests[1]["input"] == accepted
    kinds = [item.get("type", item.get("role")) for item in accepted]
    assert kinds == ["user", "reasoning", "function_call", "function_call_output", "user"]
    assert accepted[1]["encrypted_content"] == "encrypted-reasoning-1"


def test_history_without_native_items_is_encoded_from_the_neutral_form():
    first, _ = recorded("responses_api.json")
    sdk = Replay(first["parsed"])
    history = [
        TASK,
        AssistantMessage("Looking.", (ToolCall("c1", "click", {"ref": 4}, '{"ref": 4}'),)),
        ToolMessage("c1", "Clicked [4].", is_error=True),
        tail("page", 2),
    ]
    OpenAIResponsesProvider(sdk, "m").complete("s", history, TOOLS, OPTIONS)

    assert sdk.requests[0]["input"][1:4] == [
        {"role": "assistant", "content": "Looking."},
        {"type": "function_call", "call_id": "c1", "name": "click", "arguments": '{"ref": 4}'},
        {"type": "function_call_output", "call_id": "c1", "output": "Clicked [4]."},
    ]


def _status_error(name, status):
    request = httpx2.Request("POST", "http://model.test/v1/responses")
    return getattr(openai, name)(
        "failed", response=httpx2.Response(status, request=request), body=None
    )


def test_a_rejected_reasoning_setting_is_dropped_and_stays_dropped():
    first, _ = recorded("responses_api.json")
    sdk = Replay(_status_error("BadRequestError", 400), first["parsed"])
    provider = OpenAIResponsesProvider(sdk, "plain-model")

    first_reply = provider.complete("s", [TASK], TOOLS, OPTIONS)
    second_reply = provider.complete("s", [TASK], TOOLS, OPTIONS)

    assert ["reasoning" in request for request in sdk.requests] == [True, False, False]
    assert first_reply.fallbacks == ("effort_downgraded: low -> omitted",)
    assert second_reply.fallbacks == ()


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (_status_error("RateLimitError", 429), TransientModelError),
        (_status_error("InternalServerError", 500), TransientModelError),
        (_status_error("AuthenticationError", 401), ModelError),
    ],
)
def test_errors_map_to_retryable_or_fatal(error, expected):
    provider = OpenAIResponsesProvider(Replay(error), "gpt-6-luna")

    with pytest.raises(ModelError) as caught:
        provider.complete("s", [TASK], TOOLS, OPTIONS)

    assert type(caught.value) is expected


def test_accounting_is_the_same_as_for_chat_completions(tmp_path):
    first, _ = recorded("responses_api_reasoning.json")
    provider = OpenAIResponsesProvider(Replay(first["parsed"]), "gpt-6-luna")
    ledger = SpendLedger(tmp_path / "results", 10.0)
    client = LLMClient(
        provider, Pricing(0.10, 0.50, 0.01, 0.125), ledger, "gpt-6-luna", effort="low"
    )

    completion = client.labelled(run="r", task_id=7).complete(
        "S" * 400, [TASK, tail("p" * 800, 1)], TOOLS
    )

    entry = json.loads((tmp_path / "results" / "spend.jsonl").read_text(encoding="utf-8"))
    assert entry["usage"] == {
        "input_tokens": 3,
        "cached_input_tokens": 0,
        "cache_write_tokens": 1330,
        "output_tokens": 60,
        "reasoning_tokens": 40,
    }
    assert entry["cost_usd"] == pytest.approx((3 * 0.10 + 1330 * 0.125 + 60 * 0.50) / 1e6)
    # The section estimate shares out the measured prompt tokens: 3 + 1330.
    assert sum(entry["sections"].values()) == pytest.approx(1333, abs=4)
    assert entry["sections"]["observation"] > entry["sections"]["task"] > 0
    assert completion.sections == entry["sections"]


# -- the layout stays cache-friendly on this API too -------------------------------

SCRIPT = [
    ("click", {"ref": 4}),
    ("write_note", {"text": "order 7 total is 30.50"}),
    ("type", {"ref": 9, "text": "hoodie", "submit": True}),
    ("finish", FINISH_OK),
]


class ScriptedResponses:
    """Replies like the API does: a reasoning item, then a function call."""

    def __init__(self):
        self.requests = []
        self.responses = self

    def create(self, **request):
        self.requests.append(copy.deepcopy(request))
        number = len(self.requests)
        name, arguments = SCRIPT[number - 1]
        output = [
            SimpleNamespace(type="reasoning", id=f"rs_{number}", encrypted_content=f"enc-{number}"),
            SimpleNamespace(
                type="function_call",
                call_id=f"call_{number}",
                name=name,
                arguments=json.dumps(arguments),
            ),
        ]
        usage = SimpleNamespace(
            input_tokens=900,
            output_tokens=30,
            input_tokens_details=SimpleNamespace(cached_tokens=600, cache_write_tokens=0),
            output_tokens_details=SimpleNamespace(reasoning_tokens=12),
        )
        return SimpleNamespace(output=output, usage=usage, status="completed")


def test_each_request_starts_with_the_previous_one_minus_its_tail(tmp_path):
    sdk = ScriptedResponses()
    ledger = SpendLedger(tmp_path / "results", 100.0)
    client = LLMClient(OpenAIResponsesProvider(sdk, "m"), PRICING, ledger, "m").labelled(
        run="r", task_id=7
    )

    result = AgentLoop(client, FakeExecutor(), EventLog(), LoopConfig()).run("Report the total")

    assert result.reason == "finished"
    assert len(sdk.requests) == len(SCRIPT)
    for earlier, later in itertools.pairwise(sdk.requests):
        stable = json.dumps(earlier["input"][:-1])[:-1]
        assert json.dumps(later["input"]).startswith(stable)
        assert later["instructions"] == earlier["instructions"]
        assert later["tools"] == earlier["tools"]
        assert later["prompt_cache_key"] == earlier["prompt_cache_key"] == "browser-agent-r-7"
        # The turn's reasoning and call, the call's result, then the new tail.
        assert len(later["input"]) == len(earlier["input"]) + 3
    assert "Step 3 of 30." in sdk.requests[2]["input"][-1]["content"]
    assert result.usage.reasoning_tokens == 12 * len(SCRIPT)


# -- selection -----------------------------------------------------------------------


def config(**changes):
    base = {
        "provider": "openai",
        "model": "gpt-6-luna",
        "api_key": "test-key",
        "base_url": None,
        "pricing": PRICING,
        "budget_usd": 1.0,
    }
    return LLMConfig(**{**base, **changes})


def test_the_api_is_selected_by_config():
    assert isinstance(build_provider(config()), OpenAIResponsesProvider)
    assert isinstance(build_provider(config(api="chat")), OpenAIProvider)


def test_the_api_can_be_set_in_env(monkeypatch):
    for name, value in {
        "LLM_API_KEY": "test-key",
        "LLM_MODEL": "gpt-6-luna",
        "LLM_PRICE_INPUT_PER_MTOK": "0.1",
        "LLM_PRICE_OUTPUT_PER_MTOK": "0.5",
        "BUDGET_USD": "3",
        "LLM_PROVIDER": "openai",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("LLM_API", raising=False)
    assert LLMConfig.from_env().api == "responses"

    monkeypatch.setenv("LLM_API", "chat")
    assert LLMConfig.from_env().api == "chat"

    monkeypatch.setenv("LLM_API", "assistants")
    with pytest.raises(ModelError, match="LLM_API"):
        LLMConfig.from_env()
