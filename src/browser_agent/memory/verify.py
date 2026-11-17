"""Verify candidate skill code before it may run in a task.

Each candidate is replayed on the local site, from the start page of the learn task it
came from:

1. with the episode's own parameter values, where it must reproduce the episode's
   outcome. For a task that changes or shows something, the official evaluator must
   score the replay successful (only that yes or no is used). For a question, the
   value the code returns must hold the same values as the agent's answer did;
2. with one or two other sets of values that the episode's pages showed.

After every replay a verifier judges it: a model call with a context of its own that
sees the SKILL.md, the parameter values, the returned value and the final page, and
nothing of the episode. The code is kept only if every replay passes every check.
Otherwise the skill stays as it is: guidance, without code.

The site is reset before each replay of a skill that changes data, and once more at
the end.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from browser_agent.browser.actions import ActionError
from browser_agent.browser.environment import TaskStart, prepare
from browser_agent.browser.observation import observe
from browser_agent.browser.session import BrowserConfig, BrowserError, BrowserSession, origin_of
from browser_agent.context.observe import PageRenderer, ViewOptions
from browser_agent.harness.llm import LLMClient
from browser_agent.harness.tools import ToolSpec
from browser_agent.memory.build import BuildError, ask
from browser_agent.memory.episodes import Episode, without_refs, without_site
from browser_agent.memory.gate import check_gate
from browser_agent.memory.pipeline import (
    CANDIDATES,
    LOG_FILE,
    BuildConfig,
    BuildLog,
    episode_for,
    read_log,
)
from browser_agent.memory.skill import Skill, render_skill_md
from browser_agent.memory.skill_api import SkillRun, run_skill_code, site_path
from browser_agent.memory.store import MemoryStore

MAX_PAGE_CHARS = 12_000

VERIFY_SYSTEM = """\
You check one run of a skill's code on a web site. A skill is a short procedure; its
code was run once with the parameter values given. You see the skill, those values,
the value the code handed back, and the page the browser was on when the code ended.
You do not see the pages in between, and you are not told what the right result is.
Reply by calling verdict once.

Pass the run only if what you see supports that it did what the skill says, for these
parameter values:
- A skill that changes something: the final page shows the change (a success message,
  the new value in place, the new state of the item), for the item the parameters
  name.
- A skill that shows a page or a report: the final page is that page, with the
  parameter values applied.
- A skill that answers a question: the returned value is the kind of answer the skill
  describes, and where the final page shows the facts it agrees with them. A value
  that is empty, a placeholder or of the wrong kind fails.
Fail the run when the page shows another item than the parameters name, an error
message, or nothing that bears on the outcome. Give the reason in one sentence.
"""


class _Verdict(BaseModel):
    model_config = ConfigDict(extra="forbid")


VERDICT = ToolSpec(
    "verdict",
    "Say whether the run did what the skill says.",
    {
        "type": "object",
        "properties": {"passed": {"type": "boolean"}, "reason": {"type": "string"}},
        "required": ["passed", "reason"],
        "additionalProperties": False,
    },
    _Verdict,
)


@dataclass
class Replay:
    """One run of a candidate's code and what was concluded from it."""

    kind: str  # "original" or "other"
    args: dict[str, Any]
    ran: bool = False
    error: str = ""
    steps: int = 0
    seconds: float = 0.0
    value: Any = None
    final_path: str = ""
    # original only: did it reproduce the episode's outcome, and how that was told.
    reproduced: bool | None = None
    reproduced_how: str = ""
    verifier_passed: bool | None = None
    verifier_reason: str = ""

    @property
    def passed(self) -> bool:
        return (
            self.ran
            and not self.error
            and self.reproduced is not False
            and self.verifier_passed is True
        )


@dataclass
class Verdict:
    """The outcome for one candidate skill."""

    name: str
    template_id: int
    source: dict[str, Any]
    code_kept: bool = False
    why: str = ""
    replays: list[Replay] = field(default_factory=list)


def leaves(value: Any) -> list[str]:
    """The plain values inside an answer, normalized, in sorted order.

    An answer and a returned value may be shaped differently (a list of objects, a
    bare number); what must agree is what they hold.
    """
    found: list[str] = []
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            stack.extend(current.values())
        elif isinstance(current, (list, tuple)):
            stack.extend(current)
        elif current is not None:
            found.append(_plain(current))
    return sorted(found)


def _plain(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    text = str(value).strip().casefold()
    number = text.replace("$", "").replace(",", "")
    try:
        parsed = float(number)
    except ValueError:
        return " ".join(text.split())
    return str(int(parsed)) if parsed == int(parsed) else f"{parsed:.4f}".rstrip("0")


def same_values(returned: Any, answer: Any) -> bool:
    return bool(leaves(answer)) and leaves(returned) == leaves(answer)


def final_page_text(session: BrowserSession, base_url: str) -> tuple[str, str]:
    """The page the browser is on, as an agent would be shown it, and its address."""
    observation = observe(session)
    text = PageRenderer(ViewOptions(prune=True, truncate=True)).render(observation, None)
    text = without_refs(without_site(text))
    if len(text) > MAX_PAGE_CHARS:
        text = f"{text[:MAX_PAGE_CHARS]}\n[... {len(text) - MAX_PAGE_CHARS} more characters]"
    return text, site_path(observation.url, base_url)


def judge(llm: LLMClient, skill: Skill, replay: Replay, page: str) -> tuple[bool, str]:
    """The verifier's call. It sees the skill, the values, the result and the last page."""
    prompt = (
        f"The skill (SKILL.md):\n\n{render_skill_md(skill.meta, skill.body)}\n"
        f"Parameter values of this run: {json.dumps(replay.args, ensure_ascii=False)}\n"
        f"Value the code handed back: {json.dumps(replay.value, ensure_ascii=False)}\n\n"
        f"The page at the end (address {replay.final_path}):\n\n{page}\n"
    )
    answer = ask(llm, VERIFY_SYSTEM, prompt, VERDICT)
    return bool(answer.get("passed")), str(answer.get("reason", ""))[:400]


class Verifier:
    """Replays candidates on the site. One instance per verification run."""

    def __init__(
        self, env: Any, session: BrowserSession, llm: LLMClient, log: BuildLog, work: Path
    ) -> None:
        self._env = env
        self._session = session
        self._llm = llm
        self._log = log
        self._work = work
        self._origin = origin_of(env.site.url)
        self._base = env.site.admin_url
        self.dirty = False

    def verify(
        self, skill: Skill, episode: Episode, source_args: dict, other_args: Sequence[dict]
    ) -> Verdict:
        verdict = Verdict(skill.name, episode.template_id, episode.source())
        runs = [("original", source_args), *(("other", args) for args in other_args)]
        for kind, args in runs:
            replay = self._replay(skill, episode, kind, args)
            verdict.replays.append(replay)
            self._log.add("replay", skill=skill.name, **asdict(replay))
            if not replay.passed:
                # One failed replay settles it; the rest would only cost resets.
                break
        failed = next((replay for replay in verdict.replays if not replay.passed), None)
        if failed is None:
            verdict.code_kept = True
            verdict.why = f"all {len(verdict.replays)} replays passed"
        else:
            verdict.why = f"the {failed.kind} replay failed: {_why_failed(failed)}"
        return verdict

    def _replay(self, skill: Skill, episode: Episode, kind: str, args: dict[str, Any]) -> Replay:
        replay = Replay(kind, dict(args))
        task = self._env.task(episode.task_id)
        try:
            self._session.reset_state([self._origin])
            if episode.state_changing or self.dirty:
                self._env.reset()
                self.dirty = False
            else:
                self._env.restore_ui_state()
            self.dirty = episode.state_changing
            prepare(
                self._session, TaskStart(task.start_url, self._origin, self._env.site.auth_headers)
            )
            gate = check_gate(skill, args, observe(self._session), self._base)
            if not gate.passed:
                replay.error = f"the gate rejects it on the task's start page: {gate.detail}"
                return replay
            run: SkillRun = run_skill_code(skill, args, self._session, self._base, [self._origin])
            replay.ran, replay.steps, replay.seconds = True, len(run.steps), round(run.seconds, 1)
            replay.value = run.value
            if not run.ok:
                step = run.failed_step
                where = f"step {step.number} {step.call}({step.detail}): " if step else ""
                replay.error = f"{where}{run.error}"[:500]
                return replay
            page, replay.final_path = final_page_text(self._session, self._base)
            if kind == "original":
                replay.reproduced, replay.reproduced_how = self._reproduced(episode, run)
                if not replay.reproduced:
                    return replay
            call = self._llm.labelled(task_id=f"verify-{skill.name}-{kind}")
            replay.verifier_passed, replay.verifier_reason = judge(call, skill, replay, page)
        except (BrowserError, ActionError, BuildError) as exc:
            replay.error = f"{type(exc).__name__}: {exc}"[:500]
        return replay

    def _reproduced(self, episode: Episode, run: SkillRun) -> tuple[bool, str]:
        """Did the replay with the episode's own values end as the episode did?"""
        if episode.task_type == "retrieve":
            answer = (episode.answer or {}).get("retrieved_data")
            same = run.returned and same_values(run.value, answer)
            return bool(same), (
                f"returned {json.dumps(run.value, ensure_ascii=False)[:200]}; the agent had "
                f"answered {json.dumps(answer, ensure_ascii=False)[:200]}"
            )
        har = self._work / f"{episode.task_id}.har"
        assert self._session.recorder is not None
        self._session.recorder.save(har)
        response = {
            "task_type": episode.task_type.upper(),
            "status": "SUCCESS",
            "retrieved_data": None,
            "error_details": None,
        }
        score = self._env.evaluate(episode.task_id, response, har)
        # Only whether it passed is kept; the evaluator's detail stays out of memory.
        return score.success, f"the official evaluator scored the replay {score.success}"


def _why_failed(replay: Replay) -> str:
    if replay.error:
        return replay.error
    if replay.reproduced is False:
        return f"it did not reproduce the episode's outcome ({replay.reproduced_how})"
    return f"the verifier: {replay.verifier_reason}"


def verify_build(config: BuildConfig, root: Path, llm: LLMClient, build: Path) -> list[Verdict]:
    """Stage two of a build: replay every candidate with code and settle its verdict."""
    import os

    from browser_agent.eval.webarena import ShoppingAdmin, SiteConfig

    env = ShoppingAdmin(SiteConfig.from_env())
    problems = env.not_answering()
    if problems:
        raise SystemExit("not verifying: " + "; ".join(problems))
    store = MemoryStore.open(build, read_only=False)
    log = BuildLog(build / LOG_FILE)
    data_dir = Path(os.environ.get("BROWSER_AGENT_DATA_DIR", "").strip() or root / "data")
    browser_path = os.environ.get("BROWSER_PATH", "").strip()
    session = BrowserSession(
        BrowserConfig(data_dir=data_dir, browser_path=Path(browser_path) if browser_path else None)
    )
    verdicts: list[Verdict] = []
    skills = store.skills()
    with session, tempfile.TemporaryDirectory() as work:
        # A known state to start from, and the saved grid state that restores need.
        env.reset()
        verifier = Verifier(env, session, llm, log, Path(work))
        # A verification that was interrupted continues where it stopped: a candidate
        # that already has its verdict in the log is not replayed again.
        settled = {event["name"] for event in read_log(build) if event["event"] == "verdict"}
        for folder in sorted((build / CANDIDATES).iterdir()):
            if folder.name in settled:
                continue
            info = json.loads((folder / "candidate.json").read_text(encoding="utf-8"))
            code_file = folder / "skill.py"
            skill = skills.get(folder.name)
            if skill is None or not info.get("has_code") or not code_file.is_file():
                verdict = Verdict(folder.name, info["template_id"], info["source"])
                verdict.why = "no candidate code: " + "; ".join(
                    info.get("code_problems") or info.get("notes") or ["none was written"]
                )
                verdicts.append(verdict)
                log.add("verdict", **asdict(verdict))
                continue
            candidate = replace(skill, code=code_file.read_text(encoding="utf-8"))
            episode = episode_for(root, config, info["source"])
            verdict = verifier.verify(
                candidate, episode, info["source_args"], info.get("other_args") or []
            )
            for replay in verdict.replays:
                store.count_use("skill", skill.name, skill.meta.version, replay.passed)
            if verdict.code_kept:
                verified = replace(
                    candidate,
                    meta=skill.meta.model_copy(update={"version": skill.meta.version + 1}),
                )
                store.add_skill(verified, episode.source(), note=f"code verified: {verdict.why}")
            verdicts.append(verdict)
            log.add("verdict", **asdict(verdict))
        if verifier.dirty:
            env.reset()
    # Every verdict of the build, including those of an earlier, interrupted pass.
    everything = [
        {key: value for key, value in event.items() if key not in ("ts", "event")}
        for event in read_log(build)
        if event["event"] == "verdict"
    ]
    (build / "verification.json").write_text(
        json.dumps(everything, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    store.write_manifest()
    store.close()
    kept = sum(bool(verdict["code_kept"]) for verdict in everything)
    log.add("verified", candidates=len(everything), code_kept=kept)
    return verdicts
