"""The only module that calls a model.

It owns retries, tool-call parsing, token and cost accounting, the spend log and the
hard stop before BUDGET_USD. Providers are thin adapters, so everything else here is
tested offline with a scripted provider.
"""

from __future__ import annotations

import copy
import json
import os
import random
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
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


class Provider(Protocol):
    """One request to one model API. Raises ModelError or TransientModelError."""

    def complete(
        self,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        max_output_tokens: int | None,
    ) -> Reply: ...


def parse_arguments(raw: str) -> dict[str, Any] | None:
    """Tool arguments as a dict, or None when the model did not write a JSON object."""
    try:
        parsed = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


class OpenAIProvider:
    """Chat Completions on OpenAI or any endpoint that speaks the same protocol."""

    def __init__(self, client: Any, model: str, minimal: bool = False) -> None:
        self._client = client
        self._model = model
        # Some compatible endpoints reject the newer request fields.
        self._minimal = minimal

    def complete(
        self,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        max_output_tokens: int | None,
    ) -> Reply:
        import openai

        request: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": "system", "content": system}, *map(self._encode, messages)],
            "tools": [self._tool(spec) for spec in tools],
        }
        if not self._minimal:
            request["parallel_tool_calls"] = False
        if max_output_tokens is not None:
            key = "max_tokens" if self._minimal else "max_completion_tokens"
            request[key] = max_output_tokens
        try:
            response = self._client.chat.completions.create(**request)
        except openai.RateLimitError as exc:
            raise TransientModelError(f"rate limited: {exc}") from exc
        except openai.APIConnectionError as exc:  # includes timeouts
            raise TransientModelError(f"connection failed: {exc}") from exc
        except openai.APIStatusError as exc:
            if exc.status_code >= 500:
                raise TransientModelError(f"server error {exc.status_code}: {exc}") from exc
            raise ModelError(f"request rejected ({exc.status_code}): {exc}") from exc

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

    def _tool(self, spec: ToolSpec) -> dict[str, Any]:
        function: dict[str, Any] = {
            "name": spec.name,
            "description": spec.description,
            "parameters": spec.parameters,
        }
        if not self._minimal:
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
        return Usage(
            input_tokens=max(prompt - cached - written, 0),
            cached_input_tokens=cached,
            cache_write_tokens=written,
            output_tokens=usage.completion_tokens or 0,
        )


class AnthropicProvider:
    """The Anthropic Messages API."""

    def __init__(self, client: Any, model: str, prompt_caching: bool = False) -> None:
        self._client = client
        self._model = model
        self._prompt_caching = prompt_caching

    def complete(
        self,
        system: str,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        max_output_tokens: int | None,
    ) -> Reply:
        import anthropic

        request: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_output_tokens or 16_000,
            "system": system,
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
            # One action per step: a second call would act on a page the first changed.
            "tool_choice": {"type": "auto", "disable_parallel_tool_use": True},
        }
        if self._prompt_caching:
            request["cache_control"] = {"type": "ephemeral"}
        try:
            response = self._client.messages.create(**request)
        except anthropic.RateLimitError as exc:
            raise TransientModelError(f"rate limited: {exc}") from exc
        except anthropic.APIConnectionError as exc:  # includes timeouts
            raise TransientModelError(f"connection failed: {exc}") from exc
        except anthropic.APIStatusError as exc:
            if exc.status_code >= 500:
                raise TransientModelError(f"server error {exc.status_code}: {exc}") from exc
            raise ModelError(f"request rejected ({exc.status_code}): {exc}") from exc

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

    @staticmethod
    def _encode(messages: Sequence[Message]) -> list[dict[str, Any]]:
        encoded: list[dict[str, Any]] = []
        for message in messages:
            if isinstance(message, UserMessage):
                encoded.append({"role": "user", "content": message.content})
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
                    and isinstance(previous["content"], list)
                ):
                    previous["content"].append(block)
                else:
                    encoded.append({"role": "user", "content": [block]})
        return encoded


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


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
    max_output_tokens: int | None = None
    openai_minimal: bool = False

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
            max_output_tokens=int(max_output) if max_output else None,
            openai_minimal=os.environ.get("LLM_OPENAI_MINIMAL", "").strip() == "1",
        )


def build_provider(config: LLMConfig, prompt_caching: bool = False) -> Provider:
    """The official SDK client for the configured provider.

    SDK retries are turned off: LLMClient retries, so that retry behaviour is the
    same for every provider and each attempt is visible in the log.
    """
    if config.provider == "anthropic":
        import anthropic

        client = anthropic.Anthropic(
            api_key=config.api_key, base_url=config.base_url, max_retries=0, timeout=300.0
        )
        return AnthropicProvider(client, config.model, prompt_caching=prompt_caching)
    import openai

    client = openai.OpenAI(
        api_key=config.api_key, base_url=config.base_url, max_retries=0, timeout=300.0
    )
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
    ) -> None:
        self._provider = provider
        self.pricing = pricing
        self.ledger = ledger
        self.model = model
        self._max_output_tokens = max_output_tokens
        self._max_retries = max_retries
        self._sleep = sleep
        self._clock = clock
        self._labels = dict(labels or {})

    def labelled(self, **labels: Any) -> LLMClient:
        """The same client, tagging its spend entries with these labels (run, task)."""
        clone = copy.copy(self)
        clone._labels = {**self._labels, **labels}
        return clone

    def complete(
        self, system: str, messages: Sequence[Message], tools: Sequence[ToolSpec]
    ) -> Completion:
        """One model call. Raises BudgetExceededError before spending past the cap."""
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
                reply = self._provider.complete(system, messages, tools, self._max_output_tokens)
                break
            except TransientModelError:
                if attempt > self._max_retries:
                    raise
                # Exponential backoff with jitter, capped at 30 seconds.
                self._sleep(min(2.0**attempt, 30.0) * (0.5 + random.random() / 2))
        seconds = self._clock() - started
        cost = self.pricing.cost(reply.usage)
        usage = reply.usage
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
                "attempts": attempt,
                "seconds": round(seconds, 3),
            }
        )
        return Completion(
            reply=reply, cost_usd=cost, seconds=seconds, attempts=attempt, sections=sections
        )


def client_from_env(results_dir: Path, prompt_caching: bool = False) -> LLMClient:
    """Build the client for a paid run from .env settings."""
    config = LLMConfig.from_env()
    ledger = SpendLedger(results_dir, config.budget_usd)
    return LLMClient(
        provider=build_provider(config, prompt_caching=prompt_caching),
        pricing=config.pricing,
        ledger=ledger,
        model=config.model,
        max_output_tokens=config.max_output_tokens,
    )


__all__ = [
    "AssistantMessage",
    "BudgetExceededError",
    "Completion",
    "LLMClient",
    "LLMConfig",
    "Message",
    "ModelError",
    "Part",
    "Pricing",
    "Provider",
    "Reply",
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
