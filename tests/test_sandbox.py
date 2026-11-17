"""The sandbox for skill code: what the AST check refuses, and what code can reach."""

from __future__ import annotations

import pytest

from browser_agent.harness.sandbox import SandboxError, check_source, parameters, run_sandboxed

PRIMITIVES = ("goto", "click", "type", "select", "read", "check", "return_value")


def body(*lines):
    """A run() function with these lines as its body."""
    return "def run(order):\n" + "\n".join(f"    {line}" for line in lines) + "\n"


GOOD = body(
    'goto("/sales/order/")',
    'check(url="^/sales/order/")',
    'click(role="link", name="View", row=order)',
    'check(text="Order # " + order)',
    'total = read(role="row", name="", row="Grand Total")',
    'return_value(total.replace("Grand Total", "").strip())',
)


class Calls:
    """Primitives that record what they were called with."""

    def __init__(self, read_result="Grand Total $219.40"):
        self.log = []
        self.read_result = read_result

    def primitives(self):
        def make(name):
            def call(*args, **kwargs):
                self.log.append((name, args, kwargs))
                return self.read_result if name == "read" else None

            return call

        return {name: make(name) for name in PRIMITIVES}


def test_code_in_form_passes_and_runs_with_only_the_primitives():
    calls = Calls()

    run_sandboxed(GOOD, calls.primitives(), {"order": "000000299"})

    assert [name for name, _, _ in calls.log] == [
        "goto", "check", "click", "check", "read", "return_value",
    ]  # fmt: skip
    assert calls.log[2] == ("click", (), {"role": "link", "name": "View", "row": "000000299"})
    assert calls.log[-1] == ("return_value", ("$219.40",), {})
    assert parameters(GOOD, PRIMITIVES) == ["order"]


@pytest.mark.parametrize(
    ("source", "reason"),
    [
        ("import os\n" + GOOD, "exactly one function"),
        (body("import os"), "Import is not allowed"),
        (body("from os import path"), "ImportFrom is not allowed"),
        (body('x = __import__("os")'), "'__import__' cannot be called"),
        (body("x = __builtins__"), "may not start with an underscore"),
        (body("x = order.__class__"), "reading the attribute '__class__'"),
        (body("x = order.__class__()"), "the method '__class__' is not allowed"),
        (body('x = "{0.__class__}".format(order)'), "the method 'format' is not allowed"),
        (body('open("/etc/passwd")'), "'open' cannot be called"),
        (body("x = open"), "'open' is not a parameter"),
        (body('exec("1")'), "'exec' cannot be called"),
        (body('eval("1")'), "'eval' cannot be called"),
        (body('getattr(order, "x")'), "'getattr' cannot be called"),
        (body("while True:", "    pass"), "While is not allowed"),
        (body("x = [c for c in order]"), "ListComp is not allowed"),
        (body("f = lambda: 1"), "Lambda is not allowed"),
        (body("def inner():", "    pass"), "FunctionDef is not allowed"),
        (body("class A:", "    pass"), "ClassDef is not allowed"),
        (body("try:", "    pass", "except Exception:", "    pass"), "Try is not allowed"),
        (body('with open("x") as f:', "    pass"), "With is not allowed"),
        (body("global order"), "Global is not allowed"),
        (body("x = yield 1"), "Yield is not allowed"),
        (body("x = run"), "'run' is not a parameter"),
        (body("click = 3"), "click is a name the skill may not reuse"),
        (body("x = 2 ** 64"), "Pow is not allowed"),
        (body("x = 10000000"), "the constant 10000000 is not allowed"),
        (body('x = b"bytes"'), "is not allowed"),
        (body("for i in range(100000):", "    pass"), "range takes constants up to 200"),
        (body("for i in range(order):", "    pass"), "range takes constants up to 200"),
        (
            body(
                "for a in order:",
                "    for b in order:",
                "        for c in order:",
                "            pass",
            ),
            "nested 2 deep at most",
        ),
        (body("for a in order:", "    pass", "else:", "    pass"), "may not have an else"),
        (body("order.x = 1"), "only plain names can be assigned to"),
        (body("x = read(*order)"), r"no \* or \*\* in a call"),
        (body("x = [*order]"), "Starred is not allowed"),
        (body("x = read(**order)"), r"no \* or \*\* in a call"),
        ("def run(order, *rest):\n    pass\n", "plain named parameters only"),
        ("def run(order=3):\n    pass\n", "plain named parameters only"),
        ("@staticmethod\ndef run(order):\n    pass\n", "no decorators"),
        ("def other(order):\n    pass\n", "exactly one function"),
        ("def run(order):\n    pass\n\ndef more():\n    pass\n", "exactly one function"),
        ("def run(order:\n", "not valid Python"),
    ],
)
def test_what_is_not_on_the_allow_list_is_refused(source, reason):
    with pytest.raises(SandboxError, match=reason):
        check_source(source, PRIMITIVES)


def test_a_refusal_names_the_line():
    source = body('check(text="ok")', "import os")

    with pytest.raises(SandboxError, match=r"^line 3: Import is not allowed"):
        check_source(source, PRIMITIVES)


@pytest.mark.parametrize(
    ("lines", "reason"),
    [
        (('click(role="button", name="Save")',), r"click\(\) changes the page and needs a check"),
        (('goto("/a/")', 'goto("/b/")', 'check(text="b")'), r"goto\(\) at line 2 changes the page"),
        (
            ('click(role="button", name="Filters")', 'type(role="textbox", name="ID", text="7")'),
            r"click\(\) at line 2 changes the page",
        ),
        (
            (
                'select(role="combobox", name="Status", option="Complete")',
                'x = read(role="a", name="b")',
            ),
            r"select\(\) changes the page and needs a check",
        ),
        (
            ('type(role="textbox", name="ID", text="7", submit=True)',),
            r"type\(\) changes the page and needs a check",
        ),
        (
            ('type(role="textbox", name="ID", text="7", submit=order)',),
            r"type\(\) changes the page and needs a check",
        ),
    ],
)
def test_every_step_that_changes_the_page_needs_a_check_after_it(lines, reason):
    with pytest.raises(SandboxError, match=reason):
        check_source(body(*lines), PRIMITIVES)


def test_typing_without_enter_and_reading_need_no_check_of_their_own():
    source = body(
        'type(role="textbox", name="From", text="01/01/2023")',
        'type(role="textbox", name="To", text="01/31/2023", submit=False)',
        'click(role="button", name="Show Report")',
        'rows = read(role="table", name="")',
        'check(text="records found")',
        "return_value(len(rows))",
    )

    check_source(source, PRIMITIVES)


def test_loops_over_what_was_read_and_small_ranges_are_allowed():
    source = body(
        'rows = read(role="table", name="")',
        "total = 0",
        "for row in rows:",
        '    if row[8] == "Complete" and order in row[1]:',
        "        total += 1",
        "for i in range(len(rows)):",
        "    for j in range(3):",
        "        total = total + 0",
        "return_value(total)",
    )
    calls = Calls(read_result=[["", "000000299", "", "", "", "", "", "", "Complete"]])

    run_sandboxed(source, calls.primitives(), {"order": "299"})

    assert calls.log[-1] == ("return_value", (1,), {})


def test_builtins_are_out_of_reach_even_past_the_check(monkeypatch):
    """The namespace has no builtins: a name the check let through still finds nothing."""
    import browser_agent.harness.sandbox as sandbox

    monkeypatch.setattr(sandbox._Checker, "check", lambda self, tree: None)

    with pytest.raises(SandboxError, match="NameError"):
        run_sandboxed(body('open("x")'), Calls().primitives(), {"order": "1"})


def test_an_error_in_the_code_comes_back_with_its_line():
    source = body('check(text="ok")', "x = int(order)", "return_value(x)")

    with pytest.raises(SandboxError, match=r"^line 3: ValueError"):
        run_sandboxed(source, Calls().primitives(), {"order": "not a number"})


def test_the_arguments_must_be_the_parameters():
    with pytest.raises(SandboxError, match=r"run takes \['order'\], but was given \['other'\]"):
        run_sandboxed(GOOD, Calls().primitives(), {"other": 1})


def test_errors_raised_by_a_primitive_pass_through_unchanged():
    class StepFailed(RuntimeError):
        pass

    def failing(*args, **kwargs):
        raise StepFailed("check failed: the page does not show it")

    primitives = {**Calls().primitives(), "check": failing}

    with pytest.raises(StepFailed, match="does not show it"):
        run_sandboxed(GOOD, primitives, {"order": "000000299"})


def test_a_bounded_loop_may_be_left_early():
    source = body(
        'rows = read(role="table", name="")',
        'found = ""',
        "for row in rows:",
        '    if row[0] == "":',
        "        continue",
        "    if order in row[1]:",
        "        found = row[2]",
        "        break",
        "return_value(found)",
    )
    calls = Calls(
        read_result=[["", "x", "no"], ["1", "000000299", "yes"], ["2", "000000299", "late"]]
    )

    run_sandboxed(source, calls.primitives(), {"order": "299"})

    assert calls.log[-1] == ("return_value", ("yes",), {})
