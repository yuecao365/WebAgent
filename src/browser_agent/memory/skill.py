"""A skill on disk: a folder with SKILL.md and, if it was verified, skill.py.

SKILL.md starts with a YAML frontmatter block and continues with numbered steps in
plain language. The frontmatter is what the harness reads: the name and one-line
description shown to the model, the typed parameters, and what must be true of the
page before the code may run (url_pattern, required_elements, preconditions). The body
is what the model reads when it follows the skill itself.

skill.py holds the same steps as code. It exists only for a skill whose code passed
verification; a skill without it is guidance only.

A skill folder is written once and never changed: an update is a new version in a new
folder.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from browser_agent.harness.sandbox import SandboxError, parameters
from browser_agent.memory.locators import Locator, PageIndex, fill

SKILL_FILE = "SKILL.md"
CODE_FILE = "skill.py"
# Everything skill code can call (memory/skill_api.py binds them to a browser).
PRIMITIVES = ("goto", "click", "type", "select", "read", "check", "return_value")
MAX_TIME_LIMIT_S = 300.0
_FRONTMATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?(.*)\Z", re.DOTALL)
_STEP = re.compile(r"^\s*\d+\.\s+\S", re.MULTILINE)
_PYTHON_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
}


class SkillFormatError(ValueError):
    """A skill folder or SKILL.md does not have the required form."""


class Param(BaseModel):
    """One typed parameter of a skill."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["string", "integer", "number", "boolean"]
    description: str = ""


class Check(BaseModel):
    """Something that must be on the page: a text, a URL pattern or an element.

    Used for a skill's preconditions and by the check() call in skill code. Exactly one
    of text, url and role/name is given.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    # The page shows this text somewhere.
    text: str | None = None
    # The page's address, relative to the site, matches this regular expression.
    url: str | None = None
    # Exactly one element matches this locator.
    role: str | None = None
    name: str | None = None
    row: str | None = None
    section: str | None = None
    # Why the skill needs it; for the reader, not evaluated.
    why: str | None = None

    @model_validator(mode="after")
    def _exactly_one_kind(self) -> Check:
        element = self.role is not None or self.name is not None
        kinds = [self.text is not None, self.url is not None, element]
        if sum(kinds) != 1:
            raise ValueError("a check is one of: text, url, or an element by role and name")
        if element and (self.role is None or self.name is None):
            raise ValueError("an element check needs both role and name")
        if not element and (self.row is not None or self.section is not None):
            raise ValueError("row and section only narrow an element check")
        if self.url is not None:
            _compile(self.url)
        return self

    def locator(self) -> Locator | None:
        if self.role is None or self.name is None:
            return None
        return Locator(role=self.role, name=self.name, row=self.row, section=self.section)

    def filled(self, values: Mapping[str, Any]) -> Check:
        """This check with its {param} placeholders replaced."""
        # A value put into a regular expression stands for itself, not for a pattern.
        escaped = {key: re.escape(str(value)) for key, value in values.items()}
        return Check(
            **{
                key: None if value is None else fill(value, escaped if key == "url" else values)
                for key, value in self.model_dump(exclude={"why"}).items()
            },
            why=self.why,
        )

    def describe(self) -> str:
        if self.text is not None:
            return f'the page shows "{self.text}"'
        if self.url is not None:
            return f"the address matches {self.url}"
        locator = self.locator()
        assert locator is not None
        return f"there is one {locator.describe()}"

    def failure(self, index: PageIndex, site_path: str) -> str | None:
        """Why the check does not hold on this page, or None when it holds."""
        if self.text is not None:
            return None if index.has_text(self.text) else f'the page does not show "{self.text}"'
        if self.url is not None:
            if re.search(self.url, site_path):
                return None
            return f"the address {site_path} does not match {self.url}"
        locator = self.locator()
        assert locator is not None
        found = len(index.find(locator))
        if found == 1:
            return None
        return f"{found} elements match {locator.describe()}, where exactly one is needed"


def _compile(pattern: str) -> re.Pattern[str]:
    try:
        return re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"{pattern!r} is not a valid regular expression: {exc}") from exc


class SkillMeta(BaseModel):
    """The frontmatter of SKILL.md."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,62}$")
    # One line: it is listed in the prompt for every task while skills are on.
    description: str = Field(min_length=1, max_length=200)
    version: int = Field(ge=1)
    params: dict[str, Param] = Field(default_factory=dict)
    # Regular expression searched in the page's address relative to the site.
    url_pattern: str
    required_elements: list[Locator] = Field(default_factory=list)
    preconditions: list[Check] = Field(default_factory=list)
    time_limit_s: float = Field(default=120.0, gt=0, le=MAX_TIME_LIMIT_S)

    @field_validator("description")
    @classmethod
    def _one_line(cls, value: str) -> str:
        if "\n" in value or "\r" in value:
            raise ValueError("the description is one line")
        return value.strip()

    @field_validator("url_pattern")
    @classmethod
    def _valid_pattern(cls, value: str) -> str:
        _compile(value)
        return value

    @field_validator("params")
    @classmethod
    def _identifiers(cls, value: dict[str, Param]) -> dict[str, Param]:
        for key in value:
            if not key.isidentifier() or key.startswith("_"):
                raise ValueError(f"parameter name {key!r} is not a plain identifier")
        return value

    def matches_url(self, site_path: str) -> bool:
        return re.search(self.url_pattern, site_path) is not None

    def check_args(self, args: Mapping[str, Any]) -> dict[str, Any]:
        """The arguments for a run, or SkillFormatError naming what is wrong with them."""
        problems = []
        for key in args:
            if key not in self.params:
                problems.append(f"unknown argument {key!r}")
        for key, param in self.params.items():
            if key not in args:
                problems.append(f"missing argument {key!r} ({param.type})")
                continue
            value = args[key]
            # bool is an int in Python; an integer parameter must not take True.
            wrong_bool = isinstance(value, bool) and param.type != "boolean"
            if wrong_bool or not isinstance(value, _PYTHON_TYPES[param.type]):
                problems.append(f"argument {key!r} must be a {param.type}")
        if problems:
            expected = ", ".join(f"{key}: {param.type}" for key, param in self.params.items())
            raise SkillFormatError(f"{'; '.join(problems)}. Expected: {expected or 'no arguments'}")
        return dict(args)


@dataclass(frozen=True)
class Skill:
    """A skill as loaded from its folder."""

    meta: SkillMeta
    # The numbered steps, as the model is shown them.
    body: str
    # The verified code, or None for a skill that is guidance only.
    code: str | None = None

    @property
    def name(self) -> str:
        return self.meta.name

    def summary(self) -> str:
        """The one line that lists the skill in the prompt."""
        return f"{self.meta.name}: {self.meta.description} (on {self.meta.url_pattern})"


def parse_skill_md(text: str) -> tuple[SkillMeta, str]:
    """Split SKILL.md into its checked frontmatter and its body."""
    match = _FRONTMATTER.match(text)
    if match is None:
        raise SkillFormatError("SKILL.md must start with a frontmatter block between --- lines")
    try:
        raw = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        raise SkillFormatError(f"the frontmatter is not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise SkillFormatError("the frontmatter must be a mapping of fields")
    try:
        meta = SkillMeta.model_validate(raw)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in error['loc']) or 'frontmatter'}: {error['msg']}"
            for error in exc.errors()
        )
        raise SkillFormatError(f"invalid frontmatter: {problems}") from exc
    body = match.group(2).strip()
    if not _STEP.search(body):
        raise SkillFormatError("the body must list numbered steps (1. ..., 2. ...)")
    return meta, body


def render_skill_md(meta: SkillMeta, body: str) -> str:
    """SKILL.md for a skill; parse_skill_md reads it back to the same meta and body."""
    front = yaml.safe_dump(
        meta.model_dump(exclude_none=True), sort_keys=False, allow_unicode=True, width=1000
    )
    return f"---\n{front}---\n\n{body.strip()}\n"


def load_skill(folder: Path) -> Skill:
    """Read a skill folder. The folder's name must be the skill's name."""
    path = folder / SKILL_FILE
    if not path.is_file():
        raise SkillFormatError(f"{folder} has no {SKILL_FILE}")
    meta, body = parse_skill_md(path.read_text(encoding="utf-8"))
    if meta.name != folder.name and not folder.name.startswith(f"{meta.name}@"):
        raise SkillFormatError(f"the folder {folder.name} holds a skill named {meta.name}")
    code_path = folder / CODE_FILE
    code = code_path.read_text(encoding="utf-8") if code_path.is_file() else None
    skill = Skill(meta, body, code)
    check_code(skill)
    return skill


def check_code(skill: Skill) -> None:
    """Refuse code that the sandbox would refuse, or whose parameters are not the skill's."""
    if skill.code is None:
        return
    try:
        names = parameters(skill.code, PRIMITIVES)
    except SandboxError as exc:
        raise SkillFormatError(f"{CODE_FILE} of {skill.name} is not allowed: {exc}") from exc
    if sorted(names) != sorted(skill.meta.params):
        raise SkillFormatError(
            f"{CODE_FILE} of {skill.name} takes {names}, but SKILL.md declares "
            f"{list(skill.meta.params)}"
        )


def write_skill(folder: Path, skill: Skill) -> None:
    """Write a skill into a new folder. An existing folder is never written into."""
    if folder.exists():
        raise SkillFormatError(f"{folder} exists; a new version goes into a new folder")
    check_code(skill)
    folder.mkdir(parents=True)
    (folder / SKILL_FILE).write_text(
        render_skill_md(skill.meta, skill.body), encoding="utf-8", newline="\n"
    )
    if skill.code is not None:
        (folder / CODE_FILE).write_text(skill.code, encoding="utf-8", newline="\n")
