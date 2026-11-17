"""Run model-written skill code with nothing in reach but the browser primitives.

Skill code is written by a model, so it is treated as untrusted. Two layers:

1. An AST check before anything runs. It works by allow-list: the source must be one
   function `run(...)` built from a small set of statements and expressions. Whatever
   is not on the list is refused, which covers imports, attribute access to dunder
   names, open/exec/eval, `while` loops and everything else that could reach outside
   or run without end.
2. A namespace without builtins. The code can call the primitives it is given and a
   few pure helpers (len, str, int, ...), and nothing else exists.

The check also requires what makes a replay safe to trust: every call that changes
the page is followed by a check() before the next one.

The time limit is enforced by the primitives (each one looks at the clock first).
With no `while`, no recursion and bounded `for`, code cannot spend long between two
primitive calls.
"""

from __future__ import annotations

import ast
from collections.abc import Callable, Collection, Mapping
from typing import Any

# Calls that load or change the page; each needs a check() after it.
PAGE_CHANGING = frozenset({"goto", "click", "select"})
CHECK = "check"
ENTRY = "run"
MAX_RANGE = 200
MAX_LOOP_DEPTH = 2
MAX_INT = 1_000_000

SAFE_BUILTINS: dict[str, Callable[..., Any]] = {
    "len": len,
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sum": sum,
    "sorted": sorted,
    "range": range,
    "enumerate": enumerate,
    "zip": zip,
    "list": list,
    "dict": dict,
}

# Methods of strings, lists and dicts that read or build values. "format" is left
# out on purpose: a format string can read attributes ("{0.__class__}").
_METHODS = frozenset(
    {
        "strip", "lstrip", "rstrip", "split", "splitlines", "lower", "upper", "title",
        "startswith", "endswith", "replace", "join", "removeprefix", "removesuffix",
        "isdigit", "count", "index", "find", "get", "keys", "values", "items", "append",
    }
)  # fmt: skip

_STATEMENTS = (
    ast.Expr, ast.Assign, ast.AugAssign, ast.Return, ast.If, ast.For, ast.Pass,
    # Leaving a bounded loop early is how "the first row that matches" is written.
    ast.Break, ast.Continue,
)  # fmt: skip
_EXPRESSIONS = (
    ast.Call, ast.Name, ast.Constant, ast.Attribute, ast.Subscript, ast.Slice,
    ast.List, ast.Tuple, ast.Dict, ast.Compare, ast.BoolOp, ast.UnaryOp, ast.BinOp,
    ast.IfExp, ast.JoinedStr, ast.FormattedValue, ast.keyword,
)  # fmt: skip
_OPERATORS = (
    ast.And, ast.Or, ast.Not, ast.USub, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv,
    ast.Mod, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn,
    ast.Is, ast.IsNot, ast.Load, ast.Store,
)  # fmt: skip


class SandboxError(RuntimeError):
    """The code is refused, or broke a rule while running; it names the line."""


def _refuse(node: ast.AST, why: str) -> SandboxError:
    return SandboxError(f"line {getattr(node, 'lineno', '?')}: {why}")


class _Checker:
    def __init__(self, primitives: Collection[str]) -> None:
        self._primitives = frozenset(primitives)
        self._callable = self._primitives | frozenset(SAFE_BUILTINS)
        self._known: set[str] = set()

    def check(self, tree: ast.Module) -> None:
        body = list(tree.body)
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            body = body[1:]  # a module docstring
        if len(body) != 1 or not isinstance(body[0], ast.FunctionDef) or body[0].name != ENTRY:
            raise SandboxError(f"the code must be exactly one function, def {ENTRY}(...)")
        function = body[0]
        self._arguments(function)
        self._known = {arg.arg for arg in function.args.args} | {
            node.id
            for node in ast.walk(function)
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
        }
        clash = self._known & self._callable
        if clash:
            raise _refuse(function, f"{sorted(clash)[0]} is a name the skill may not reuse")
        statements = list(function.body)
        if (
            statements
            and isinstance(statements[0], ast.Expr)
            and isinstance(statements[0].value, ast.Constant)
            and isinstance(statements[0].value.value, str)
        ):
            statements = statements[1:]  # the function's docstring
        self._block(statements, loop_depth=0)
        self._checks_follow_changes(function)

    def _arguments(self, function: ast.FunctionDef) -> None:
        args = function.args
        if function.decorator_list or function.returns is not None:
            raise _refuse(function, "no decorators or annotations on run")
        if args.vararg or args.kwarg or args.kwonlyargs or args.posonlyargs or args.defaults:
            raise _refuse(function, "run takes plain named parameters only")
        for arg in args.args:
            if arg.annotation is not None or arg.arg.startswith("_"):
                raise _refuse(function, f"parameter {arg.arg!r} must be a plain name")

    def _block(self, statements: list[ast.stmt], loop_depth: int) -> None:
        for statement in statements:
            if not isinstance(statement, _STATEMENTS):
                raise _refuse(statement, f"{type(statement).__name__} is not allowed in a skill")
            if isinstance(statement, ast.For):
                self._loop(statement, loop_depth)
            elif isinstance(statement, ast.If):
                self._expression(statement.test)
                self._block(statement.body, loop_depth)
                self._block(statement.orelse, loop_depth)
            elif isinstance(statement, ast.Assign):
                for target in statement.targets:
                    self._target(target)
                self._expression(statement.value)
            elif isinstance(statement, ast.AugAssign):
                self._target(statement.target)
                self._expression(statement.value)
            elif isinstance(statement, (ast.Expr, ast.Return)) and statement.value is not None:
                self._expression(statement.value)

    def _loop(self, loop: ast.For, loop_depth: int) -> None:
        if loop.orelse:
            raise _refuse(loop, "a for loop may not have an else part")
        if loop_depth >= MAX_LOOP_DEPTH:
            raise _refuse(loop, f"loops may be nested {MAX_LOOP_DEPTH} deep at most")
        self._target(loop.target)
        self._expression(loop.iter)
        self._block(loop.body, loop_depth + 1)

    def _target(self, target: ast.expr) -> None:
        if isinstance(target, ast.Name):
            if target.id.startswith("_"):
                raise _refuse(target, f"the name {target.id!r} may not start with an underscore")
            return
        if isinstance(target, ast.Tuple) and all(isinstance(e, ast.Name) for e in target.elts):
            for element in target.elts:
                self._target(element)
            return
        raise _refuse(target, "only plain names can be assigned to")

    def _expression(self, expression: ast.AST) -> None:
        for node in ast.walk(expression):
            if isinstance(node, _OPERATORS):
                continue
            if not isinstance(node, _EXPRESSIONS):
                raise _refuse(node, f"{type(node).__name__} is not allowed in a skill")
            if isinstance(node, ast.Name):
                self._name(node)
            elif isinstance(node, ast.Constant):
                self._constant(node)
            elif isinstance(node, ast.Call):
                self._call(node)
        # Attributes are only reachable as the method of a call, which _call accepts.
        called = {id(node.func) for node in ast.walk(expression) if isinstance(node, ast.Call)}
        for node in ast.walk(expression):
            if isinstance(node, ast.Attribute) and id(node) not in called:
                raise _refuse(node, f"reading the attribute {node.attr!r} is not allowed")

    def _name(self, node: ast.Name) -> None:
        if node.id.startswith("_"):
            raise _refuse(node, f"the name {node.id!r} may not start with an underscore")
        if node.id not in self._known and node.id not in self._callable:
            raise _refuse(node, f"{node.id!r} is not a parameter, a variable or an allowed call")

    @staticmethod
    def _constant(node: ast.Constant) -> None:
        value = node.value
        if isinstance(value, bool) or value is None or isinstance(value, (str, float)):
            return
        if isinstance(value, int) and abs(value) <= MAX_INT:
            return
        raise _refuse(node, f"the constant {value!r} is not allowed")

    def _call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Attribute):
            if func.attr.startswith("_") or func.attr not in _METHODS:
                raise _refuse(node, f"the method {func.attr!r} is not allowed")
        elif isinstance(func, ast.Name):
            if func.id not in self._callable:
                allowed = ", ".join(sorted(self._primitives))
                raise _refuse(
                    node,
                    f"{func.id!r} cannot be called; a skill calls only {allowed} and a few helpers",
                )
            if func.id == "range":
                self._bounded_range(node)
        else:
            raise _refuse(node, "only named functions and methods can be called")
        if any(isinstance(arg, ast.Starred) for arg in node.args) or any(
            keyword.arg is None for keyword in node.keywords
        ):
            raise _refuse(node, "no * or ** in a call")

    @staticmethod
    def _bounded_range(node: ast.Call) -> None:
        for arg in node.args:
            bounded = (
                isinstance(arg, ast.Constant)
                and isinstance(arg.value, int)
                and abs(arg.value) <= MAX_RANGE
            )
            # len(x) of a value read from the page is as bounded as the page.
            counted = (
                isinstance(arg, ast.Call)
                and isinstance(arg.func, ast.Name)
                and arg.func.id == "len"
            )
            if not (bounded or counted):
                raise _refuse(node, f"range takes constants up to {MAX_RANGE}, or len(...)")

    def _checks_follow_changes(self, function: ast.FunctionDef) -> None:
        """Every call that changes the page is checked before the next step acts.

        Calls are taken in source order. That is exact for straight-line code and on
        the strict side for branches, which is the side to err on.
        """
        calls = sorted(
            (
                node
                for node in ast.walk(function)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in self._primitives
            ),
            key=lambda node: (node.lineno, node.col_offset),
        )
        pending: ast.Call | None = None
        for call in calls:
            name = call.func.id  # type: ignore[attr-defined]
            if name == CHECK:
                pending = None
                continue
            acts = name in PAGE_CHANGING or name == "type"
            if acts and pending is not None:
                raise _refuse(
                    call,
                    f"{pending.func.id}() at line {pending.lineno} changes the page and "  # type: ignore[attr-defined]
                    f"needs a check() before the next step",
                )
            if name in PAGE_CHANGING or (name == "type" and _submits(call)):
                pending = call
        if pending is not None:
            raise _refuse(
                pending,
                f"{pending.func.id}() changes the page and needs a check() after it",  # type: ignore[attr-defined]
            )


def _submits(call: ast.Call) -> bool:
    """type(..., submit=...) presses Enter unless submit is the constant False."""
    for keyword in call.keywords:
        if keyword.arg == "submit":
            return not (isinstance(keyword.value, ast.Constant) and keyword.value.value is False)
    return False


def check_source(source: str, primitives: Collection[str]) -> ast.Module:
    """Parse skill code and refuse whatever is not on the allow-list."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise SandboxError(f"line {exc.lineno}: not valid Python: {exc.msg}") from exc
    _Checker(primitives).check(tree)
    return tree


def parameters(source: str, primitives: Collection[str]) -> list[str]:
    """The parameter names of run(), in order."""
    tree = check_source(source, primitives)
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef))
    return [arg.arg for arg in function.args.args]


def run_sandboxed(
    source: str, primitives: Mapping[str, Callable[..., Any]], args: Mapping[str, Any]
) -> Any:
    """Check the code, then call run(**args) with only the primitives in reach.

    Errors raised by a primitive pass through unchanged, so the caller can tell a
    failed check from a locator that matched nothing. Any other error in the code
    comes back as SandboxError with the line it happened on.
    """
    tree = check_source(source, primitives)
    namespace: dict[str, Any] = {"__builtins__": {}, **SAFE_BUILTINS, **primitives}
    # The tree passed the allow-list above, and the namespace holds no builtins.
    exec(compile(tree, "<skill>", "exec"), namespace)
    expected = parameters(source, primitives)
    if sorted(expected) != sorted(args):
        raise SandboxError(f"run takes {expected}, but was given {sorted(args)}")
    try:
        return namespace[ENTRY](**args)
    except SandboxError:
        raise
    except (
        TypeError, ValueError, KeyError, IndexError, ZeroDivisionError, NameError, AttributeError
    ) as exc:  # fmt: skip
        line = _line_in_skill(exc)
        raise SandboxError(f"line {line}: {type(exc).__name__}: {exc}") from exc


def _line_in_skill(exc: BaseException) -> int | str:
    trace = exc.__traceback__
    line: int | str = "?"
    while trace is not None:
        if trace.tb_frame.f_code.co_filename == "<skill>":
            line = trace.tb_lineno
        trace = trace.tb_next
    return line
