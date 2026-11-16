"""The only module that calls a model.

It owns retries, tool-call parsing, token and cost accounting, the spend log and the
hard stop before BUDGET_USD. Providers are thin adapters, so everything else here is
tested offline with a scripted provider.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import random
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from browser_agent.harness.tools import ToolSpec

# ---------------------------------------------------------------------------
# Conversation types, provider neutral
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    # None when the model produced arguments that are not a JSON object.
    arguments: dict[str, Any] | None
    raw_arguments: str = ""


# Prompt sections, the units token use is reported in. "history" is everything
# before the last message that is not the task.
SECTIONS = ("system", "tools", "task", "history", "observation", "notes", "status")


@dataclass(frozen=True)
class Part:
    """A piece of a message, labelled with the prompt section it belongs to."""

    section: str
    text: str


def _parts(content: str | Sequence[Part], section: str) -> tuple[Part, ...]:
    return (Part(section, content),) if isinstance(content, str) else tuple(content)


@dataclass(frozen=True, init=False)
class UserMessage:
    parts: tuple[Part, ...]

    def __init__(self, content: str | Sequence[Part], section: str = "history") -> None:
        object.__setattr__(self, "parts", _parts(content, section))

    @property
    def content(self) -> str:
        return "\n\n".join(part.text for part in self.parts)


@dataclass(frozen=True)
class AssistantMessage:
    text: str
    tool_calls: tuple[ToolCall, ...] = ()
    # The provider's own form of this turn. Replaying it unchanged keeps what the
    # neutral fields cannot carry, such as thinking blocks.
    native: Any = None


@dataclass(frozen=True, init=False)
class ToolMessage:
    tool_call_id: str
    parts: tuple[Part, ...]
    is_error: bool

    def __init__(
        self,
        tool_call_id: str,
        content: str | Sequence[Part],
        is_error: bool = False,
        section: str = "history",
    ) -> None:
        object.__setattr__(self, "tool_call_id", tool_call_id)
        object.__setattr__(self, "parts", _parts(content, section))
        object.__setattr__(self, "is_error", is_error)

    @property
    def content(self) -> str:
        return "\n\n".join(part.text for part in self.parts)


Message = UserMessage | AssistantMessage | ToolMessage


@dataclass(frozen=True)
class Usage:
    """Token counts of one call; the three input kinds are priced differently."""

    input_tokens: int = 0
    cached_input_tokens: int = 0
    cache_write_tokens: int = 0
    output_tokens: int = 0
    # The part of output_tokens spent on reasoning. Already counted and priced as
    # output; kept apart to show what reasoning costs.
    reasoning_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.cached_input_tokens
            + self.cache_write_tokens
            + self.output_tokens
        )

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            self.input_tokens + other.input_tokens,
            self.cached_input_tokens + other.cached_input_tokens,
            self.cache_write_tokens + other.cache_write_tokens,
            self.output_tokens + other.output_tokens,
            self.reasoning_tokens + other.reasoning_tokens,
        )


@dataclass(frozen=True)
class Reply:
    """What a provider returned for one call."""

    text: str
    tool_calls: tuple[ToolCall, ...]
    usage: Usage
    stop_reason: str
    native: Any = None

    def message(self) -> AssistantMessage:
        return AssistantMessage(self.text, self.tool_calls, self.native)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ModelError(RuntimeError):
    """The call failed and retrying will not help."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class TransientModelError(ModelError):
    """The call failed in a way worth retrying: rate limit, timeout, server error."""


class BudgetExceededError(RuntimeError):
    """The next call could take spending past the cap, so it was not made."""


# ---------------------------------------------------------------------------
# Pricing and the spend ledger
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Pricing:
    """USD per million tokens."""

    input: float
    output: float
    cached_input: float | None = None
    cache_write: float | None = None

    def cost(self, usage: Usage) -> float:
        cached = self.input if self.cached_input is None else self.cached_input
        write = self.input if self.cache_write is None else self.cache_write
        return (
            usage.input_tokens * self.input
            + usage.cached_input_tokens * cached
            + usage.cache_write_tokens * write
            + usage.output_tokens * self.output
        ) / 1_000_000


class SpendLedger:
    """Append-only record of every paid call, and the cap it must stay under.

    The cap covers everything in the log, across runs: it is the amount the user
    agreed to spend in total, not an allowance per run.
    """

    def __init__(self, directory: Path, budget_usd: float) -> None:
        self.directory = directory
        self.budget_usd = budget_usd
        self._jsonl = directory / "spend.jsonl"
        self._markdown = directory / "spend.md"
        self.total_usd = sum(entry["cost_usd"] for entry in self._read())

    def check(self, reserve_usd: float) -> None:
        """Raise unless a call that may cost reserve_usd still fits under the cap."""
        if self.total_usd + reserve_usd > self.budget_usd:
            raise BudgetExceededError(
                f"spent ${self.total_usd:.4f} of ${self.budget_usd:.2f}; the next call "
                f"may cost up to ${reserve_usd:.4f}"
            )

    def record(self, entry: dict[str, Any]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        with self._jsonl.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self.total_usd += entry["cost_usd"]

    def write_summary(self) -> None:
        """Rewrite spend.md: one row per run, then the total against the cap."""
        runs: dict[str, dict[str, float]] = {}
        for entry in self._read():
            row = runs.setdefault(
                entry.get("run", "-"), {"calls": 0, "input": 0, "output": 0, "usd": 0.0}
            )
            usage = entry["usage"]
            row["calls"] += 1
            row["input"] += (
                usage["input_tokens"] + usage["cached_input_tokens"] + usage["cache_write_tokens"]
            )
            row["output"] += usage["output_tokens"]
            row["usd"] += entry["cost_usd"]
        lines = [
            "# Spend",
            "",
            "| Run | Calls | Input tokens | Output tokens | USD |",
            "|---|---:|---:|---:|---:|",
        ]
        for name, row in runs.items():
            lines.append(
                f"| {name} | {row['calls']:.0f} | {row['input']:.0f} | "
                f"{row['output']:.0f} | {row['usd']:.4f} |"
            )
        lines += ["", f"Total: ${self.total_usd:.4f} of the ${self.budget_usd:.2f} cap.", ""]
        self.directory.mkdir(parents=True, exist_ok=True)
        self._markdown.write_text("\n".join(lines), encoding="utf-8")

    def _read(self) -> list[dict[str, Any]]:
        if not self._jsonl.exists():
            return []
        with self._jsonl.open(encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CallOptions:
    """Per-call settings a provider maps to its own request fields."""

    max_output_tokens: int | None = None
    # A stable name for the conversation, so a provider can route its steps to the
    # same prompt cache.
    cache_key: str | None = None
    # Let the model send several tool calls in one reply.
    parallel_tools: bool = False
    # Reasoning effort, for models that have such a setting.
    effort: str | None = None


class Provider(Protocol):
    """One request to one model API. Raises ModelError or TransientModelError."""

    def complete(
        self,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        options: CallOptions,
    ) -> Reply: ...


def parse_arguments(raw: str) -> dict[str, Any] | None:
    """Tool arguments as a dict, or None when the model did not write a JSON object."""
    try:
        parsed = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _call_openai(
    create: Callable[..., Any], request: dict[str, Any], first_error: ModelError | None = None
) -> Any:
    """Call an OpenAI SDK endpoint and sort its errors into retryable and fatal."""
    import openai

    try:
        return create(**request)
    except openai.RateLimitError as exc:
        raise TransientModelError(f"rate limited: {exc}") from exc
    except openai.APIConnectionError as exc:  # includes timeouts
        raise TransientModelError(f"connection failed: {exc}") from exc
    except openai.APIStatusError as exc:
        if exc.status_code >= 500:
            raise TransientModelError(f"server error {exc.status_code}: {exc}") from exc
        # When a retry in another mode fails too, the first rejection is the real cause.
        cause = first_error or ModelError(
            f"request rejected ({exc.status_code}): {exc}", status_code=exc.status_code
        )
        raise cause from exc


class OpenAIProvider:
    """Chat Completions on OpenAI or any endpoint that speaks the same protocol.

    The messages are sent in the order the loop builds them and nothing is added in
    front, so the prefix of a request is byte-identical to the previous request's.
    That is all an automatic prompt cache needs.
    """

    def __init__(self, client: Any, model: str, minimal: bool = False) -> None:
        self._client = client
        self._model = model
        # Some compatible endpoints reject the newer request fields. Minimal mode
        # leaves them out; it is switched on after the first such rejection.
        self._minimal = minimal
        # Index of the request mode that last worked; see _send_with_fallback.
        self._mode = 0

    def complete(
        self,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        options: CallOptions,
    ) -> Reply:
        response = self._send_with_fallback(system, messages, tools, options)
        choice = response.choices[0]
        calls = tuple(
            ToolCall(
                id=call.id,
                name=call.function.name,
                arguments=parse_arguments(call.function.arguments or ""),
                raw_arguments=call.function.arguments or "",
            )
            for call in (choice.message.tool_calls or [])
        )
        return Reply(
            text=choice.message.content or "",
            tool_calls=calls,
            usage=self._usage(response.usage),
            stop_reason=choice.finish_reason or "",
        )

    def _send_with_fallback(
        self,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        options: CallOptions,
    ) -> Any:
        """Send the request; when it is rejected, send it again in the next mode.

        The modes, in order: the effort as configured; effort "none" (some models
        accept function tools on this API only without reasoning); no effort field
        (models without the setting); and last a request without any optional field.
        The mode that works is kept, so later calls are not rejected again. What the
        model is shown is the same in every mode.
        """
        modes: list[tuple[str | None, bool]] = []
        for mode in ((options.effort, False), ("none", False), (None, False), (None, True)):
            if mode not in modes:
                modes.append(mode)
        start = len(modes) - 1 if self._minimal else min(self._mode, len(modes) - 1)
        first_error: ModelError | None = None
        for index in range(start, len(modes)):
            effort, minimal = modes[index]
            request = self._request(system, messages, tools, options, minimal, effort)
            try:
                response = self._send(request, first_error)
            except TransientModelError:
                raise
            except ModelError as exc:
                if exc.status_code not in (400, 422) or index == len(modes) - 1:
                    raise
                first_error = first_error or exc
                continue
            self._mode, self._minimal = index, minimal
            return response
        raise first_error or ModelError("no request mode left to try")

    def _request(
        self,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        options: CallOptions,
        minimal: bool,
        effort: str | None,
    ) -> dict[str, Any]:
        request: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": "system", "content": system}, *map(self._encode, messages)],
            "tools": [self._tool(spec, strict=not minimal) for spec in tools],
        }
        if options.max_output_tokens is not None:
            key = "max_tokens" if minimal else "max_completion_tokens"
            request[key] = options.max_output_tokens
        if not minimal:
            request["parallel_tool_calls"] = options.parallel_tools
            if options.cache_key:
                request["prompt_cache_key"] = options.cache_key
            if effort:
                request["reasoning_effort"] = effort
        return request

    def _send(self, request: dict[str, Any], first_error: ModelError | None = None) -> Any:
        return _call_openai(self._client.chat.completions.create, request, first_error)

    @staticmethod
    def _tool(spec: ToolSpec, strict: bool) -> dict[str, Any]:
        function: dict[str, Any] = {
            "name": spec.name,
            "description": spec.description,
            "parameters": spec.parameters,
        }
        if strict:
            function["strict"] = True
        return {"type": "function", "function": function}

    @staticmethod
    def _encode(message: Message) -> dict[str, Any]:
        if isinstance(message, UserMessage):
            return {"role": "user", "content": message.content}
        if isinstance(message, ToolMessage):
            return {
                "role": "tool",
                "tool_call_id": message.tool_call_id,
                "content": message.content,
            }
        # A turn needs content or tool calls; an empty reply is sent back as "".
        content = message.text or (None if message.tool_calls else "")
        encoded: dict[str, Any] = {"role": "assistant", "content": content}
        if message.tool_calls:
            encoded["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.name, "arguments": call.raw_arguments or "{}"},
                }
                for call in message.tool_calls
            ]
        return encoded

    @staticmethod
    def _usage(usage: Any) -> Usage:
        if usage is None:
            return Usage()
        details = getattr(usage, "prompt_tokens_details", None)
        cached = getattr(details, "cached_tokens", None) or 0
        written = getattr(details, "cache_write_tokens", None) or 0
        prompt = usage.prompt_tokens or 0
        output_details = getattr(usage, "completion_tokens_details", None)
        return Usage(
            input_tokens=max(prompt - cached - written, 0),
            cached_input_tokens=cached,
            cache_write_tokens=written,
            output_tokens=usage.completion_tokens or 0,
            reasoning_tokens=getattr(output_details, "reasoning_tokens", None) or 0,
        )


class OpenAIResponsesProvider:
    """The OpenAI Responses API.

    Unlike Chat Completions it lets a reasoning model use function tools at any
    effort. Requests are stateless (store off): every turn of the model is sent back
    as the items it came in, reasoning included in its encrypted form, so the input
    only ever grows at the end and the prompt cache can reuse it.
    """

    def __init__(self, client: Any, model: str) -> None:
        self._client = client
        self._model = model
        # Set after the model rejects the reasoning setting, so it is not sent again.
        self._no_effort = False

    def complete(
        self,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        options: CallOptions,
    ) -> Reply:
        try:
            response = self._send(self._request(system, messages, tools, options))
        except ModelError as exc:
            retry = exc.status_code in (400, 422) and options.effort and not self._no_effort
            if isinstance(exc, TransientModelError) or not retry:
                raise
            # A model without a reasoning setting: try once without it.
            self._no_effort = True
            response = self._send(self._request(system, messages, tools, options), first_error=exc)

        text_parts: list[str] = []
        calls: list[ToolCall] = []
        native: list[dict[str, Any]] = []
        refused = False
        for item in response.output:
            if item.type == "function_call":
                calls.append(
                    ToolCall(
                        id=item.call_id,
                        name=item.name,
                        arguments=parse_arguments(item.arguments or ""),
                        raw_arguments=item.arguments or "",
                    )
                )
                native.append(
                    {
                        "type": "function_call",
                        "call_id": item.call_id,
                        "name": item.name,
                        "arguments": item.arguments or "",
                    }
                )
            elif item.type == "reasoning":
                native.append(
                    {
                        "type": "reasoning",
                        "id": item.id,
                        "summary": [],
                        "encrypted_content": item.encrypted_content,
                    }
                )
            elif item.type == "message":
                for part in item.content:
                    if part.type == "output_text":
                        text_parts.append(part.text)
                    elif part.type == "refusal":
                        refused = True
        text = "".join(text_parts)
        if text:
            native.append({"role": "assistant", "content": text})

        if refused:
            stop_reason = "refusal"
        elif calls:
            stop_reason = "tool_calls"
        else:
            detail = getattr(response, "incomplete_details", None)
            stop_reason = getattr(detail, "reason", None) or response.status or ""
        return Reply(
            text=text,
            tool_calls=tuple(calls),
            usage=self._usage(response.usage),
            stop_reason=stop_reason,
            native=native,
        )

    def _request(
        self,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        options: CallOptions,
    ) -> dict[str, Any]:
        request: dict[str, Any] = {
            "model": self._model,
            "instructions": system,
            "input": self._encode(messages),
            "tools": [
                {
                    "type": "function",
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.parameters,
                    "strict": True,
                }
                for spec in tools
            ],
            "parallel_tool_calls": options.parallel_tools,
            # Nothing is kept on the server; the reasoning comes back encrypted so it
            # can be replayed with the next request.
            "store": False,
            "include": ["reasoning.encrypted_content"],
        }
        if options.max_output_tokens is not None:
            request["max_output_tokens"] = options.max_output_tokens
        if options.cache_key:
            request["prompt_cache_key"] = options.cache_key
        if options.effort and not self._no_effort:
            request["reasoning"] = {"effort": options.effort}
        return request

    def _send(self, request: dict[str, Any], first_error: ModelError | None = None) -> Any:
        return _call_openai(self._client.responses.create, request, first_error)

    @staticmethod
    def _encode(messages: Sequence[Message]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for message in messages:
            if isinstance(message, UserMessage):
                items.append({"role": "user", "content": message.content})
            elif isinstance(message, ToolMessage):
                items.append(
                    {
                        "type": "function_call_output",
                        "call_id": message.tool_call_id,
                        "output": message.content,
                    }
                )
            elif message.native is not None:
                # The model's own items, reasoning included, exactly as they came.
                items.extend(message.native)
            else:
                if message.text:
                    items.append({"role": "assistant", "content": message.text})
                items.extend(
                    {
                        "type": "function_call",
                        "call_id": call.id,
                        "name": call.name,
                        "arguments": call.raw_arguments or "{}",
                    }
                    for call in message.tool_calls
                )
        return items

    @staticmethod
    def _usage(usage: Any) -> Usage:
        if usage is None:
            return Usage()
        details = getattr(usage, "input_tokens_details", None)
        cached = getattr(details, "cached_tokens", None) or 0
        written = getattr(details, "cache_write_tokens", None) or 0
        prompt = usage.input_tokens or 0
        reasoning = getattr(getattr(usage, "output_tokens_details", None), "reasoning_tokens", 0)
        return Usage(
            input_tokens=max(prompt - cached - written, 0),
            cached_input_tokens=cached,
            cache_write_tokens=written,
            output_tokens=usage.output_tokens or 0,
            reasoning_tokens=reasoning or 0,
        )


_CACHE_BREAKPOINT = {"type": "ephemeral"}


class AnthropicProvider:
    """The Anthropic Messages API.

    Three cache breakpoints follow the prompt layout: after the system prompt (which
    also covers the tool schemas), after the task, and after the last history entry.
    The last message is the tail that changes every step and is never cached.
    """

    def __init__(self, client: Any, model: str) -> None:
        self._client = client
        self._model = model
        # Set after the model rejects the effort setting, so it is not sent again.
        self._no_effort = False

    def complete(
        self,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        options: CallOptions,
    ) -> Reply:
        try:
            response = self._send(self._request(system, messages, tools, options))
        except ModelError as exc:
            retry = exc.status_code == 400 and options.effort and not self._no_effort
            if isinstance(exc, TransientModelError) or not retry:
                raise
            # Older models have no effort setting; try once without it.
            self._no_effort = True
            response = self._send(self._request(system, messages, tools, options), first_error=exc)

        text = "".join(block.text for block in response.content if block.type == "text")
        calls = tuple(
            ToolCall(
                id=block.id,
                name=block.name,
                arguments=block.input if isinstance(block.input, dict) else None,
                raw_arguments=json.dumps(block.input),
            )
            for block in response.content
            if block.type == "tool_use"
        )
        usage = response.usage
        return Reply(
            text=text,
            tool_calls=calls,
            usage=Usage(
                input_tokens=usage.input_tokens or 0,
                cached_input_tokens=usage.cache_read_input_tokens or 0,
                cache_write_tokens=usage.cache_creation_input_tokens or 0,
                output_tokens=usage.output_tokens or 0,
            ),
            stop_reason=response.stop_reason or "",
            native=response.content,
        )

    def _request(
        self,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        options: CallOptions,
    ) -> dict[str, Any]:
        request: dict[str, Any] = {
            "model": self._model,
            "max_tokens": options.max_output_tokens or 16_000,
            "system": [{"type": "text", "text": system, "cache_control": _CACHE_BREAKPOINT}],
            "messages": self._encode(messages),
            "tools": [
                {
                    "name": spec.name,
                    "description": spec.description,
                    "input_schema": spec.parameters,
                    "strict": True,
                }
                for spec in tools
            ],
            "tool_choice": {
                "type": "auto",
                "disable_parallel_tool_use": not options.parallel_tools,
            },
        }
        if options.effort and not self._no_effort:
            request["output_config"] = {"effort": options.effort}
        return request

    def _send(self, request: dict[str, Any], first_error: ModelError | None = None) -> Any:
        import anthropic

        try:
            return self._client.messages.create(**request)
        except anthropic.RateLimitError as exc:
            raise TransientModelError(f"rate limited: {exc}") from exc
        except anthropic.APIConnectionError as exc:  # includes timeouts
            raise TransientModelError(f"connection failed: {exc}") from exc
        except anthropic.APIStatusError as exc:
            if exc.status_code >= 500:
                raise TransientModelError(f"server error {exc.status_code}: {exc}") from exc
            cause = first_error or ModelError(
                f"request rejected ({exc.status_code}): {exc}", status_code=exc.status_code
            )
            raise cause from exc

    @classmethod
    def _encode(cls, messages: Sequence[Message]) -> list[dict[str, Any]]:
        encoded: list[dict[str, Any]] = []
        for message in messages:
            if isinstance(message, UserMessage):
                blocks = [{"type": "text", "text": part.text} for part in message.parts]
                encoded.append({"role": "user", "content": blocks})
            elif isinstance(message, AssistantMessage):
                content = message.native
                if content is None:
                    content = [{"type": "text", "text": message.text}] if message.text else []
                    content += [
                        {
                            "type": "tool_use",
                            "id": call.id,
                            "name": call.name,
                            "input": call.arguments or {},
                        }
                        for call in message.tool_calls
                    ]
                if not content:
                    # The API rejects an empty assistant turn.
                    content = [{"type": "text", "text": "(no reply)"}]
                encoded.append({"role": "assistant", "content": content})
            else:
                block = {
                    "type": "tool_result",
                    "tool_use_id": message.tool_call_id,
                    "content": message.content,
                    "is_error": message.is_error,
                }
                # All results of one turn go back in a single user message.
                previous = encoded[-1] if encoded else None
                if (
                    previous is not None
                    and previous["role"] == "user"
                    and previous["content"]
                    and previous["content"][-1].get("type") == "tool_result"
                ):
                    previous["content"].append(block)
                else:
                    encoded.append({"role": "user", "content": [block]})
        cls._mark_cache_breakpoints(encoded)
        return encoded

    @staticmethod
    def _mark_cache_breakpoints(encoded: list[dict[str, Any]]) -> None:
        """Mark the end of the task and the end of the history as cacheable.

        The last message is the tail and stays unmarked. A model turn replayed in the
        provider's own form cannot carry a mark, so a history that ends with one is
        cached up to its last tool result instead.
        """
        if len(encoded) < 2:
            return
        for message in (encoded[0], encoded[-2]):
            blocks = message["content"]
            if message["role"] == "user" and isinstance(blocks[-1], dict):
                blocks[-1]["cache_control"] = _CACHE_BREAKPOINT


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


# A step's reply is a tool call or a few; this leaves room for a long answer or note.
DEFAULT_MAX_OUTPUT_TOKENS = 4096
# The lowest setting most reasoning models accept. Picking an element on a page that
# is spelled out in text rarely needs more; providers drop it when a model has none.
DEFAULT_EFFORT = "low"
# The Responses API takes a reasoning effort together with function tools where
# Chat Completions refuses it (gpt-6-luna), and it won the learn-task arms. An
# OpenAI-compatible endpoint that has only Chat Completions sets LLM_API=chat.
DEFAULT_API = "responses"


def _env_effort() -> str | None:
    """LLM_REASONING_EFFORT: a level to send ("none" is a level), or "omit" to send nothing."""
    raw = os.environ.get("LLM_REASONING_EFFORT", "").strip().lower()
    if not raw:
        return DEFAULT_EFFORT
    return None if raw == "omit" else raw


def _env_api() -> str:
    """LLM_API: "responses" (default) or "chat"."""
    api = os.environ.get("LLM_API", "").strip().lower() or DEFAULT_API
    if api not in ("chat", "responses"):
        raise ModelError(f"LLM_API must be 'chat' or 'responses', not {api!r}")
    return api


def _env_float(name: str) -> float | None:
    raw = os.environ.get(name, "").strip()
    return float(raw) if raw else None


@dataclass(frozen=True)
class LLMConfig:
    """Model settings read from the environment (.env)."""

    provider: str
    model: str
    api_key: str = field(repr=False)
    base_url: str | None
    pricing: Pricing
    budget_usd: float
    max_output_tokens: int | None = DEFAULT_MAX_OUTPUT_TOKENS
    openai_minimal: bool = False
    effort: str | None = DEFAULT_EFFORT
    # Which OpenAI API to use: "chat" (Chat Completions) or "responses".
    api: str = DEFAULT_API

    @classmethod
    def from_env(cls) -> LLMConfig:
        """Read the settings, naming every missing variable at once."""
        missing = [
            name
            for name in (
                "LLM_API_KEY",
                "LLM_MODEL",
                "LLM_PRICE_INPUT_PER_MTOK",
                "LLM_PRICE_OUTPUT_PER_MTOK",
                "BUDGET_USD",
            )
            if not os.environ.get(name, "").strip()
        ]
        if missing:
            raise ModelError(f"set these in .env before a paid run: {', '.join(missing)}")
        model = os.environ["LLM_MODEL"].strip()
        provider = os.environ.get("LLM_PROVIDER", "").strip().lower()
        if not provider:
            provider = "anthropic" if model.startswith("claude") else "openai"
        if provider not in ("openai", "anthropic"):
            raise ModelError(f"LLM_PROVIDER must be 'openai' or 'anthropic', not {provider!r}")
        max_output = os.environ.get("LLM_MAX_OUTPUT_TOKENS", "").strip()
        return cls(
            provider=provider,
            model=model,
            api_key=os.environ["LLM_API_KEY"].strip(),
            base_url=os.environ.get("LLM_BASE_URL", "").strip() or None,
            pricing=Pricing(
                input=float(os.environ["LLM_PRICE_INPUT_PER_MTOK"]),
                output=float(os.environ["LLM_PRICE_OUTPUT_PER_MTOK"]),
                cached_input=_env_float("LLM_PRICE_CACHED_INPUT_PER_MTOK"),
                cache_write=_env_float("LLM_PRICE_CACHE_WRITE_PER_MTOK"),
            ),
            budget_usd=float(os.environ["BUDGET_USD"]),
            max_output_tokens=int(max_output) if max_output else DEFAULT_MAX_OUTPUT_TOKENS,
            openai_minimal=os.environ.get("LLM_OPENAI_MINIMAL", "").strip() == "1",
            effort=_env_effort(),
            api=_env_api(),
        )


def build_provider(config: LLMConfig) -> Provider:
    """The official SDK client for the configured provider.

    SDK retries are turned off: LLMClient retries, so that retry behaviour is the
    same for every provider and each attempt is visible in the log.
    """
    if config.provider == "anthropic":
        import anthropic

        client = anthropic.Anthropic(
            api_key=config.api_key, base_url=config.base_url, max_retries=0, timeout=300.0
        )
        return AnthropicProvider(client, config.model)
    import openai

    client = openai.OpenAI(
        api_key=config.api_key, base_url=config.base_url, max_retries=0, timeout=300.0
    )
    if config.api == "responses":
        return OpenAIResponsesProvider(client, config.model)
    return OpenAIProvider(client, config.model, minimal=config.openai_minimal)


# ---------------------------------------------------------------------------
# The client
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Completion:
    """A reply together with what it cost."""

    reply: Reply
    cost_usd: float
    seconds: float
    attempts: int
    # Estimated prompt tokens per section; they sum to the measured prompt tokens.
    sections: dict[str, int] = field(default_factory=dict)
    # The reply came from the development response cache: no call was made or paid.
    from_cache: bool = False


def _message_record(message: Message) -> dict[str, Any]:
    """A message as plain data, for hashing a request."""
    if isinstance(message, AssistantMessage):
        calls = [[call.id, call.name, call.raw_arguments] for call in message.tool_calls]
        return {"role": "assistant", "text": message.text, "calls": calls}
    record: dict[str, Any] = {"parts": [[part.section, part.text] for part in message.parts]}
    if isinstance(message, ToolMessage):
        record.update(role="tool", id=message.tool_call_id, error=message.is_error)
    else:
        record["role"] = "user"
    return record


class ResponseCache:
    """Replies stored by the hash of the full request, for development reruns.

    Running an unchanged task again then costs nothing. It is off unless asked for:
    a cached reply is not a new sample of the model, so results that count must
    come from real calls.
    """

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    @staticmethod
    def key(
        model: str,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        options: CallOptions,
    ) -> str:
        request = {
            "model": model,
            "system": system,
            "tools": [[spec.name, spec.description, spec.parameters] for spec in tools],
            "messages": [_message_record(message) for message in messages],
            # The cache key routes requests; it does not change the reply.
            "options": [options.max_output_tokens, options.parallel_tools, options.effort],
        }
        encoded = json.dumps(request, sort_keys=True, ensure_ascii=False).encode()
        return hashlib.sha256(encoded).hexdigest()

    def get(self, key: str) -> Reply | None:
        path = self.directory / f"{key}.json"
        if not path.exists():
            return None
        stored = json.loads(path.read_text(encoding="utf-8"))
        return Reply(
            text=stored["text"],
            tool_calls=tuple(ToolCall(**call) for call in stored["tool_calls"]),
            usage=Usage(**stored["usage"]),
            stop_reason=stored["stop_reason"],
        )

    def put(self, key: str, reply: Reply) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        stored = {
            "text": reply.text,
            "tool_calls": [asdict(call) for call in reply.tool_calls],
            "usage": asdict(reply.usage),
            "stop_reason": reply.stop_reason,
        }
        path = self.directory / f"{key}.json"
        path.write_text(json.dumps(stored, ensure_ascii=False), encoding="utf-8")


def _tools_chars(tools: Sequence[ToolSpec]) -> int:
    return sum(
        len(spec.name) + len(spec.description) + len(json.dumps(spec.parameters)) for spec in tools
    )


def section_chars(
    system: str, messages: Sequence[Message], tools: Sequence[ToolSpec]
) -> dict[str, int]:
    """Characters of the prompt by section.

    Parts of the last message count under their own section: it is the tail that
    changes every step. In earlier messages the task keeps its section and the rest
    is history, whatever it was when it was the tail.
    """
    chars = dict.fromkeys(SECTIONS, 0)
    chars["system"] = len(system)
    chars["tools"] = _tools_chars(tools)
    last = len(messages) - 1
    for index, message in enumerate(messages):
        if isinstance(message, AssistantMessage):
            chars["history"] += len(message.text) + sum(
                len(call.name) + len(call.raw_arguments) for call in message.tool_calls
            )
            continue
        for part in message.parts:
            section = part.section if index == last or part.section == "task" else "history"
            chars[section if section in chars else "history"] += len(part.text)
    return chars


def section_tokens(chars: dict[str, int], prompt_tokens: int) -> dict[str, int]:
    """Share the measured prompt tokens among the sections in proportion to their size.

    Only the total is measured; the split assumes every section has about the same
    number of characters per token, so it is an estimate.
    """
    total = sum(chars.values())
    if total == 0:
        return dict.fromkeys(chars, 0)
    return {name: round(prompt_tokens * count / total) for name, count in chars.items()}


def estimate_tokens(system: str, messages: Sequence[Message], tools: Sequence[ToolSpec]) -> int:
    """A deliberately high guess at the prompt size, used only for the budget check.

    Three characters per token overestimates ordinary text, which is the safe side
    for a check that must not let a call slip past the cap.
    """
    chars = len(system) + sum(
        len(json.dumps(spec.parameters)) + len(spec.description) for spec in tools
    )
    for message in messages:
        if isinstance(message, AssistantMessage):
            chars += len(message.text) + sum(
                len(call.raw_arguments) + 40 for call in message.tool_calls
            )
        else:
            chars += len(message.content)
    return chars // 3 + 1


class LLMClient:
    """Calls the model with retries, accounts for every call and enforces the cap."""

    def __init__(
        self,
        provider: Provider,
        pricing: Pricing,
        ledger: SpendLedger,
        model: str,
        max_output_tokens: int | None = None,
        max_retries: int = 4,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        labels: dict[str, Any] | None = None,
        parallel_tools: bool = False,
        effort: str | None = None,
        cache: ResponseCache | None = None,
    ) -> None:
        self._cache = cache
        self._provider = provider
        self.pricing = pricing
        self.ledger = ledger
        self.model = model
        self._max_output_tokens = max_output_tokens
        self._parallel_tools = parallel_tools
        self._effort = effort
        self._max_retries = max_retries
        self._sleep = sleep
        self._clock = clock
        self._labels = dict(labels or {})

    def labelled(self, **labels: Any) -> LLMClient:
        """The same client, tagging its spend entries with these labels (run, task)."""
        clone = copy.copy(self)
        clone._labels = {**self._labels, **labels}
        return clone

    def _cache_key(self) -> str | None:
        """One key per task: its steps share a prefix, other tasks do not."""
        task = self._labels.get("task_id")
        return None if task is None else f"browser-agent-{self._labels.get('run', 'run')}-{task}"

    def complete(
        self, system: str, messages: Sequence[Message], tools: Sequence[ToolSpec]
    ) -> Completion:
        """One model call. Raises BudgetExceededError before spending past the cap."""
        options = CallOptions(
            max_output_tokens=self._max_output_tokens,
            cache_key=self._cache_key(),
            parallel_tools=self._parallel_tools,
            effort=self._effort,
        )
        cache_key = None
        if self._cache is not None:
            cache_key = ResponseCache.key(self.model, system, messages, tools, options)
            stored = self._cache.get(cache_key)
            if stored is not None:
                return self._finish(stored, system, messages, tools, 0.0, 0, from_cache=True)

        reserve = self.pricing.cost(
            Usage(
                input_tokens=estimate_tokens(system, messages, tools),
                output_tokens=self._max_output_tokens or 8_192,
            )
        )
        self.ledger.check(reserve)

        started = self._clock()
        attempt = 0
        while True:
            attempt += 1
            try:
                reply = self._provider.complete(system, messages, tools, options)
                break
            except TransientModelError:
                if attempt > self._max_retries:
                    raise
                # Exponential backoff with jitter, capped at 30 seconds.
                self._sleep(min(2.0**attempt, 30.0) * (0.5 + random.random() / 2))
        seconds = self._clock() - started
        if self._cache is not None and cache_key is not None:
            self._cache.put(cache_key, reply)
        return self._finish(reply, system, messages, tools, seconds, attempt, from_cache=False)

    def _finish(
        self,
        reply: Reply,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        seconds: float,
        attempts: int,
        from_cache: bool,
    ) -> Completion:
        """Account for a reply and log it. A cached reply is logged at no cost."""
        usage = reply.usage
        cost = 0.0 if from_cache else self.pricing.cost(usage)
        prompt_tokens = usage.input_tokens + usage.cached_input_tokens + usage.cache_write_tokens
        sections = section_tokens(section_chars(system, messages, tools), prompt_tokens)
        self.ledger.record(
            {
                "ts": datetime.now(UTC).isoformat(timespec="seconds"),
                **self._labels,
                "model": self.model,
                "usage": asdict(usage),
                "sections": sections,
                "cost_usd": cost,
                "attempts": attempts,
                "seconds": round(seconds, 3),
                "from_response_cache": from_cache,
            }
        )
        return Completion(reply, cost, seconds, attempts, sections, from_cache)


def client_from_env(
    results_dir: Path,
    parallel_tools: bool = False,
    response_cache: Path | None = None,
    api: str | None = None,
    effort: str | None = None,
) -> LLMClient:
    """Build the client for a paid run from .env settings.

    api and effort, when given, take the place of LLM_API and LLM_REASONING_EFFORT,
    so that an experiment config can pick them per arm. effort "omit" sends none.
    """
    config = LLMConfig.from_env()
    if api is not None:
        config = replace(config, api=api)
    if effort is not None:
        config = replace(config, effort=None if effort == "omit" else effort)
    ledger = SpendLedger(results_dir, config.budget_usd)
    return LLMClient(
        provider=build_provider(config),
        pricing=config.pricing,
        ledger=ledger,
        model=config.model,
        max_output_tokens=config.max_output_tokens,
        parallel_tools=parallel_tools,
        effort=config.effort,
        cache=ResponseCache(response_cache) if response_cache is not None else None,
    )


__all__ = [
    "AssistantMessage",
    "BudgetExceededError",
    "CallOptions",
    "Completion",
    "LLMClient",
    "LLMConfig",
    "Message",
    "ModelError",
    "Part",
    "Pricing",
    "Provider",
    "Reply",
    "ResponseCache",
    "SpendLedger",
    "ToolCall",
    "ToolMessage",
    "TransientModelError",
    "Usage",
    "UserMessage",
    "build_provider",
    "client_from_env",
    "estimate_tokens",
    "parse_arguments",
]
