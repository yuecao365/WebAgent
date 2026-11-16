"""Observation: accessibility tree to text, on a saved tree and on small cases."""

from __future__ import annotations

from browser_agent.browser.observation import observe, render_ax_tree

from fakes import FakeBrowser, load_fixture


def node(node_id, role, name="", children=(), **extra):
    return {
        "nodeId": str(node_id),
        "role": {"value": role},
        "name": {"value": name},
        "childIds": [str(child) for child in children],
        "backendDOMNodeId": 100 + node_id,
        **extra,
    }


def prop(name, value):
    return {"name": name, "value": {"value": value}}


def test_saved_login_page():
    text = render_ax_tree(load_fixture("ax_login.json"))
    lines = text.splitlines()

    assert lines[0].startswith("[")
    assert "RootWebArea" in lines[0]
    assert '   [3] textbox "Username *" focused' in lines
    assert '   [5] textbox "Password *"' in lines
    assert '    [10] button "Sign in"' in lines
    assert not any("InlineTextBox" in line for line in lines)
    assert len(lines) == 22
    # Every line starts with a ref; "[-]" marks content with no element to act on.
    assert all(line.lstrip().startswith("[") for line in lines)
    assert '    [-] StaticText "*"' in lines


def test_nesting_is_shown_by_indentation():
    nodes = [
        node(1, "RootWebArea", "Page", children=[2]),
        node(2, "navigation", "Menu", children=[3]),
        node(3, "link", "Orders"),
    ]

    assert render_ax_tree(nodes).splitlines() == [
        '[101] RootWebArea "Page"',
        ' [102] navigation "Menu"',
        '  [103] link "Orders"',
    ]


def test_unnamed_wrappers_are_dropped_and_their_children_lifted():
    nodes = [
        node(1, "RootWebArea", "Page", children=[2]),
        node(2, "generic", children=[3]),
        node(3, "none", children=[4]),
        node(4, "button", "Save"),
    ]

    assert render_ax_tree(nodes).splitlines() == [
        '[101] RootWebArea "Page"',
        ' [104] button "Save"',
    ]


def test_ignored_nodes_are_dropped_but_not_their_children():
    nodes = [
        node(1, "RootWebArea", "Page", children=[2]),
        node(2, "table", "Hidden wrapper", children=[3], ignored=True),
        node(3, "cell", "Total: 5"),
    ]

    assert render_ax_tree(nodes).splitlines()[1] == ' [103] cell "Total: 5"'


def test_text_that_repeats_its_parent_is_dropped():
    nodes = [
        node(1, "link", "Customers", children=[2, 3]),
        node(2, "StaticText", "Customers"),
        node(3, "StaticText", "(12)"),
    ]

    assert render_ax_tree(nodes).splitlines() == [
        '[101] link "Customers"',
        ' [103] StaticText "(12)"',
    ]


def test_values_and_states_are_shown():
    nodes = [
        node(1, "textbox", "Name", value={"value": "Ann"}),
        node(
            2,
            "checkbox",
            "Active",
            properties=[prop("checked", "true"), prop("focusable", True), prop("disabled", False)],
        ),
        node(3, "button", "More", properties=[prop("expanded", False)]),
        node(
            4,
            "combobox",
            "Status",
            value={"value": "Pending"},
            properties=[prop("invalid", "spelling")],
        ),
    ]

    assert render_ax_tree(nodes).splitlines() == [
        '[101] textbox "Name" value="Ann"',
        '[102] checkbox "Active" checked',
        '[103] button "More"',
        '[104] combobox "Status" value="Pending" invalid=spelling',
    ]


def test_observe_reads_url_title_and_tree():
    browser = FakeBrowser(
        [node(1, "RootWebArea", "Orders", children=[2]), node(2, "button", "Search")]
    )
    browser.url, browser.title = "http://site.test/admin/sales/", "Orders"

    page = observe(browser)

    assert page.render().splitlines() == [
        "URL: http://site.test/admin/sales/",
        "Title: Orders",
        "Scroll: 0 of 1100 px",
        "",
        '[101] RootWebArea "Orders"',
        ' [102] button "Search"',
    ]


def test_fingerprint_changes_with_the_page():
    browser = FakeBrowser([node(1, "button", "Search")])
    first = observe(browser).fingerprint()
    assert observe(browser).fingerprint() == first

    browser.nodes = [node(1, "button", "Reset")]

    assert observe(browser).fingerprint() != first


def test_an_open_dialog_is_accepted_and_reported():
    browser = FakeBrowser([node(1, "button", "Delete")])
    browser.dialog = {"type": "confirm", "message": "Delete this review?"}

    page = observe(browser)

    assert ("Page.handleJavaScriptDialog", {"accept": True}) in browser.cdp_calls
    assert "Dialog (accepted automatically): confirm: Delete this review?" in page.render()


def test_oversized_pages_are_cut_and_say_so():
    browser = FakeBrowser([node(n, "button", f"Button {n}") for n in range(1, 200)])

    page = observe(browser, max_chars=500)

    assert len(page.tree) < 600
    assert page.tree.splitlines()[-1].startswith("[observation cut: ")
