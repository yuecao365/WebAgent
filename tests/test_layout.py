"""The prompt layout is cache-friendly: each request extends the one before it.

These tests run the real loop against the real provider adapters, with fake SDK
clients that record the requests exactly as they would be sent.
"""

from __future__ import annotations

import copy
import itertools
import json
from types import SimpleNamespace

import pytest

from browser_agent.harness.events import EventLog
from browser_agent.harness.llm import (
    AnthropicProvider,
    LLMClient,
    OpenAIProvider,
    SpendLedger,
)
from browser_agent.harness.loop import AgentLoop, LoopConfig

from fakes import FINISH_OK, PRICING, FakeExecutor

# What the scripted model does, step by step: (tool name, arguments).
SCRIPT = [
    ("click", {"ref": 4}),
    ("write_note", {"text": "order 7 total is 30.50"}),
    ("type", {"ref": 9, "text": "hoodie", "submit": True}),
    ("click", {"ref": 12}),
    ("finish", FINISH_OK),
]


class OpenAIClient:
    def __init__(self):
        self.requests = []
        self.chat = SimpleNamespace(completions=self)

    def create(self, **request):
        self.requests.append(copy.deepcopy(request))
        name, arguments = SCRIPT[len(self.requests) - 1]
        call = SimpleNamespace(
            id=f"call_{len(self.requests)}",
            function=SimpleNamespace(name=name, arguments=json.dumps(arguments)),
        )
        message = SimpleNamespace(content=None, tool_calls=[call])
        usage = SimpleNamespace(prompt_tokens=900, completion_tokens=20, prompt_tokens_details=None)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message, finish_reason="tool_calls")], usage=usage
        )


class AnthropicClient:
    def __init__(self):
        self.requests = []
        self.messages = self

    def create(self, **request):
        self.requests.append(copy.deepcopy(request))
        name, arguments = SCRIPT[len(self.requests) - 1]
        content = [
            SimpleNamespace(type="thinking", thinking="", signature=f"sig{len(self.requests)}"),
            SimpleNamespace(
                type="tool_use", id=f"tu_{len(self.requests)}", name=name, input=arguments
            ),
        ]
        usage = SimpleNamespace(
            input_tokens=900,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
            output_tokens=20,
        )
        return SimpleNamespace(content=content, usage=usage, stop_reason="tool_use")


def run_task(tmp_path, provider):
    ledger = SpendLedger(tmp_path / "results", 100.0)
    client = LLMClient(provider, PRICING, ledger, "model").labelled(run="r", task_id=7)
    AgentLoop(client, FakeExecutor(), EventLog(), LoopConfig()).run("Report the order total")


def dumps(value):
    return json.dumps(value, ensure_ascii=False, default=lambda o: vars(o))


def test_each_openai_request_starts_with_the_previous_one_minus_its_tail(tmp_path):
    sdk = OpenAIClient()
    run_task(tmp_path, OpenAIProvider(sdk, "model"))
    requests = sdk.requests

    assert len(requests) == len(SCRIPT)
    for earlier, later in itertools.pairwise(requests):
        # Everything but the last message, as the bytes that would go on the wire.
        stable = dumps(earlier["messages"][:-1])[:-1]
        assert dumps(later["messages"]).startswith(stable)
        assert dumps(later["tools"]) == dumps(earlier["tools"])
        assert later["messages"][0] == earlier["messages"][0]  # the system prompt
        assert later["prompt_cache_key"] == earlier["prompt_cache_key"] == "browser-agent-r-7"
        # The history grew by exactly the step's call and its result.
        assert len(later["messages"]) == len(earlier["messages"]) + 2


def test_only_the_tail_carries_what_changes_every_step(tmp_path):
    sdk = OpenAIClient()
    run_task(tmp_path, OpenAIProvider(sdk, "model"))

    for number, request in enumerate(sdk.requests, start=1):
        *stable, tail = request["messages"]
        assert f"Step {number} of 30." in tail["content"]
        assert "Current page:" in tail["content"]
        assert "Working note:" in tail["content"]
        assert not any("Step " in (message["content"] or "") for message in stable)
        assert not any("Current page:" in (message["content"] or "") for message in stable)
    # The note written in step 2 shows from step 3 on, in the tail only.
    assert "order 7 total is 30.50" in sdk.requests[2]["messages"][-1]["content"]


def without_marks(messages):
    cleaned = copy.deepcopy(messages)
    for message in cleaned:
        for block in message["content"]:
            if isinstance(block, dict):
                block.pop("cache_control", None)
    return cleaned


def test_each_anthropic_request_starts_with_the_previous_one_minus_its_tail(tmp_path):
    sdk = AnthropicClient()
    run_task(tmp_path, AnthropicProvider(sdk, "claude-test"))
    requests = sdk.requests

    assert len(requests) == len(SCRIPT)
    for earlier, later in itertools.pairwise(requests):
        # Cache marks move with the history; the content before the tail must not.
        stable = dumps(without_marks(earlier["messages"][:-1]))[:-1]
        assert dumps(without_marks(later["messages"])).startswith(stable)
        assert later["system"] == earlier["system"]
        assert dumps(later["tools"]) == dumps(earlier["tools"])


def marked(request):
    """(message index, block index) of every cache breakpoint in the messages."""
    return [
        (m, b)
        for m, message in enumerate(request["messages"])
        for b, block in enumerate(message["content"])
        if isinstance(block, dict) and "cache_control" in block
    ]


def test_anthropic_breakpoints_follow_the_layout(tmp_path):
    sdk = AnthropicClient()
    run_task(tmp_path, AnthropicProvider(sdk, "claude-test"))
    first, third = sdk.requests[0], sdk.requests[2]

    for request in sdk.requests:
        assert request["system"][0]["cache_control"] == {"type": "ephemeral"}
        assert not any("cache_control" in block for block in request["messages"][-1]["content"])
    # Step 1 has no history yet: only the task is marked.
    assert marked(first) == [(0, 0)]
    # Later: the task, and the newest tool result at the end of the history.
    last_history = len(third["messages"]) - 2
    assert marked(third) == [(0, 0), (last_history, 0)]
    assert third["messages"][last_history]["content"][0]["type"] == "tool_result"
    # System, task and history: three breakpoints, within the API's limit of four.
    assert len(marked(third)) + 1 <= 4


def test_anthropic_replays_model_turns_as_they_came(tmp_path):
    sdk = AnthropicClient()
    run_task(tmp_path, AnthropicProvider(sdk, "claude-test"))

    replayed = sdk.requests[1]["messages"][1]
    assert replayed["role"] == "assistant"
    assert [block.type for block in replayed["content"]] == ["thinking", "tool_use"]
    assert replayed["content"][0].signature == "sig1"


@pytest.mark.parametrize("multi_action", [False, True])
def test_parallel_tool_calls_follow_the_setting(tmp_path, multi_action):
    openai_sdk, anthropic_sdk = OpenAIClient(), AnthropicClient()
    for sdk, provider in (
        (openai_sdk, OpenAIProvider(openai_sdk, "model")),
        (anthropic_sdk, AnthropicProvider(anthropic_sdk, "claude-test")),
    ):
        ledger = SpendLedger(tmp_path / type(sdk).__name__, 100.0)
        client = LLMClient(provider, PRICING, ledger, "model", parallel_tools=multi_action)
        AgentLoop(client, FakeExecutor(), EventLog(), LoopConfig(multi_action=multi_action)).run(
            "x"
        )

    assert openai_sdk.requests[0]["parallel_tool_calls"] is multi_action
    assert anthropic_sdk.requests[0]["tool_choice"] == {
        "type": "auto",
        "disable_parallel_tool_use": not multi_action,
    }
