"""Observation views: pruned, truncated, and as a diff. Each is a switch."""

from __future__ import annotations

from browser_agent.browser.observation import Observation
from browser_agent.context.observe import PageRenderer, ViewOptions

from fakes import load_fixture

HOW_TO_SEE_ALL = ", so look there before deciding one is missing"


def node(node_id, role, name="", children=(), **extra):
    return {
        "nodeId": str(node_id),
        "role": {"value": role},
        "name": {"value": name},
        "childIds": [str(child) for child in children],
        "backendDOMNodeId": 100 + node_id,
        **extra,
    }


def prop(name, value=True):
    return {"name": name, "value": {"value": value}}


def page(nodes, document="doc-1", url="http://site.test/admin/"):
    return Observation(url=url, title="Admin", nodes=nodes, document=document)


def body(text):
    """The view without its header lines."""
    return text.split("\n\n", 1)[1].splitlines()


def grid(rows):
    """A page with a search box and a table of `rows` orders."""
    nodes = [
        node(1, "RootWebArea", "Orders", children=[2, 3, 4]),
        node(2, "heading", "Orders", children=[90]),
        node(90, "StaticText", "Orders"),
        node(3, "textbox", "Search by keyword"),
        node(4, "table", "", children=[5, *range(10, 10 + rows)]),
        node(5, "row", "", children=[6, 7]),
        node(6, "columnheader", "ID"),
        node(7, "columnheader", "Status"),
    ]
    for index in range(rows):
        base = 1000 + index * 10
        nodes += [
            node(10 + index, "row", "", children=[base, base + 1, base + 2]),
            node(base, "cell", f"{index:09d}", children=[base + 5]),
            node(base + 5, "StaticText", f"{index:09d}"),
            node(base + 1, "cell", "Pending", children=[base + 6]),
            node(base + 6, "StaticText", "Pending"),
            node(base + 2, "cell", "View", children=[base + 3]),
            node(base + 3, "link", "View", children=[base + 4]),
            node(base + 4, "StaticText", "View"),
        ]
    return nodes


def test_with_every_switch_off_the_view_is_the_complete_outline():
    observation = page(load_fixture("ax_login.json"))

    assert PageRenderer().render(observation, None) == observation.render()
    assert not any(vars(ViewOptions())[name] for name in ("prune", "truncate", "diff"))


def test_pruned_view_of_the_saved_login_page():
    text = PageRenderer(ViewOptions(prune=True)).render(page(load_fixture("ax_login.json")), None)

    assert body(text) == [
        '[134] link "Magento Admin Panel"',
        ' image "Magento Admin Panel"',
        'group "Welcome, please sign in"',
        " Welcome, please sign in Username *",
        ' [3] textbox "Username *" focused',
        " Password *",
        ' [5] textbox "Password *"',
        ' [10] button "Sign in"',
        ' [158] link "Forgot your password?"',
        '[160] link "Magento"',
        "Copyright © 2026 Magento Commerce Inc. All rights reserved.",
    ]
    assert "read_page with a section ref" in text.split("\n\n", 1)[0]


def test_pruning_puts_a_table_row_on_one_line():
    lines = body(PageRenderer(ViewOptions(prune=True)).render(page(grid(2)), None))

    assert lines == [
        'heading "Orders"',
        '[103] textbox "Search by keyword"',
        "table",
        " [105] row: [106] ID | [107] Status",
        ' [110] row: 000000000 | Pending | [1103] link "View"',
        ' [111] row: 000000001 | Pending | [1113] link "View"',
    ]


def test_pruning_keeps_only_refs_that_can_be_acted_on():
    nodes = [
        node(1, "RootWebArea", "Page", children=[2, 3, 5, 6]),
        node(2, "paragraph", "", children=[20]),
        node(20, "StaticText", "Total: 5 orders"),
        node(3, "generic", "", children=[4]),
        node(4, "button", "Save", children=[40]),
        node(40, "StaticText", "Save"),
        node(5, "generic", "Custom dropdown", properties=[prop("focusable")]),
        node(6, "checkbox", "Active", properties=[prop("checked", "true")]),
    ]

    lines = body(PageRenderer(ViewOptions(prune=True)).render(page(nodes), None))

    assert lines == [
        "Total: 5 orders",
        '[104] button "Save"',
        # A plain element that takes focus is a hand-built control.
        '[105] generic "Custom dropdown"',
        '[106] checkbox "Active" checked',
    ]


def test_pruning_keeps_the_choices_of_a_select():
    nodes = [
        node(1, "combobox", "Status", children=[2], value={"value": "Pending"}),
        node(2, "MenuListPopup", "", children=[3, 4]),
        node(3, "option", "Pending", properties=[prop("selected")]),
        node(4, "option", "Complete"),
    ]

    lines = body(PageRenderer(ViewOptions(prune=True)).render(page(nodes), None))

    assert lines == [
        '[101] combobox "Status" value="Pending"',
        ' [103] option "Pending" selected',
        ' [104] option "Complete"',
    ]


def test_long_runs_are_counted_instead_of_listed():
    options = ViewOptions(prune=True, truncate=True, max_rows=3)

    lines = body(PageRenderer(options).render(page(grid(10)), None))

    assert lines[2:] == [
        "table",
        " [105] row: [106] ID | [107] Status",
        ' [110] row: 000000000 | Pending | [1103] link "View"',
        ' [111] row: 000000001 | Pending | [1113] link "View"',
        " … 8 more rows not shown (11 in all); read_page with section=104 lists them all"
        + HOW_TO_SEE_ALL,
    ]


def test_short_runs_are_left_alone():
    options = ViewOptions(prune=True, truncate=True, max_rows=20)

    assert not any(
        "more rows" in line for line in body(PageRenderer(options).render(page(grid(5)), None))
    )


def test_truncation_keeps_the_selected_option():
    choices = [node(10 + n, "option", f"Country {n}") for n in range(30)]
    choices[25]["properties"] = [prop("selected")]
    nodes = [node(1, "combobox", "Country", children=range(10, 40)), *choices]
    options = ViewOptions(prune=True, truncate=True, max_options=3)

    lines = body(PageRenderer(options).render(page(nodes), None))

    assert lines == [
        '[101] combobox "Country"',
        ' [110] option "Country 0"',
        ' [111] option "Country 1"',
        ' [112] option "Country 2"',
        ' [135] option "Country 25" selected',
        " … 26 more options not shown (30 in all); read_page with section=101 lists them all"
        + HOW_TO_SEE_ALL,
    ]


def test_truncation_also_works_on_the_complete_outline():
    options = ViewOptions(truncate=True, max_rows=2)

    lines = body(PageRenderer(options).render(page(grid(6)), None))

    # The header row and the first order; the other five are counted.
    assert [line for line in lines if line.endswith("] row")] == ["  [105] row", "  [110] row"]
    assert lines[-1].startswith("  … 5 more rows not shown (7 in all); read_page with section=104")
    # Not pruned: cells still have their own lines.
    assert '   [1100] cell "000000000"' in lines


def test_a_section_lists_everything_under_one_element():
    renderer = PageRenderer(ViewOptions(prune=True, truncate=True, max_rows=3))
    observation = page(grid(10))

    section = renderer.section(observation, 104)

    assert section.splitlines()[0] == "[104] table"
    assert len([line for line in section.splitlines() if " row" in line]) == 11
    assert '  [1193] link "View"' in section
    assert "more rows" not in section
    assert renderer.section(observation, 999_999) is None


def test_a_large_section_keeps_the_pruned_style():
    renderer = PageRenderer(ViewOptions(prune=True, truncate=True))

    section = renderer.section(page(grid(120)), 104)

    lines = section.splitlines()
    assert lines[0] == "table"
    assert len(lines) == 122
    assert lines[-1] == ' [229] row: 000000119 | Pending | [2293] link "View"'


def test_diff_shows_only_what_changed_on_the_same_document():
    renderer = PageRenderer(ViewOptions(prune=True, diff=True))
    before = page(grid(30))
    after_nodes = grid(30)
    next(n for n in after_nodes if n["nodeId"] == "1021")["name"]["value"] = "Canceled"
    after_nodes[-1]["name"]["value"] = "Canceled"
    after = page(after_nodes)

    first = renderer.render(before, None)
    second = renderer.render(after, before)

    assert "Only the changes are shown" not in first
    assert len(body(first)) == 34
    assert "Only the changes are shown" in second
    changed = [line for line in second.splitlines() if line.startswith(("+", "-"))]
    assert changed == [
        '- [112] row: 000000002 | Pending | [1123] link "View"',
        '+ [112] row: 000000002 | Canceled | [1123] link "View"',
    ]
    assert len(second) < len(first) / 3


def test_diff_says_when_nothing_changed():
    renderer = PageRenderer(ViewOptions(diff=True))
    observation = page(grid(3))
    renderer.render(observation, None)

    assert "The page is the same as at your last step." in renderer.render(observation, observation)


def test_a_new_document_is_shown_whole():
    renderer = PageRenderer(ViewOptions(prune=True, diff=True))
    before = page(grid(3))
    renderer.render(before, None)

    reloaded = renderer.render(page(grid(3), document="doc-2"), before)

    assert "Only the changes are shown" not in reloaded
    assert len(body(reloaded)) == 7


def test_a_large_change_is_shown_whole():
    renderer = PageRenderer(ViewOptions(prune=True, diff=True))
    before = page(grid(3))
    renderer.render(before, None)

    after = renderer.render(page(grid(60)), before)

    assert "Only the changes are shown" not in after
    assert len(body(after)) == 64
