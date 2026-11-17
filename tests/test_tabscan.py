"""The scan of old traces for pages loaded outside the agent's tab."""

from __future__ import annotations

from browser_agent.eval.tabscan import shown_urls, unshown_documents

SITE = "http://localhost:7780/admin"


def document(url, status=200, kind="Document"):
    return {"request": {"url": url}, "response": {"status": status}, "_resourceType": kind}


def log(*events):
    return list(events)


def observation(url):
    return {"type": "observation", "url": url}


def test_the_agents_tab_is_followed_through_observations_results_and_gotos():
    events = log(
        observation(f"{SITE}/admin/dashboard/"),
        {"type": "tool_call", "name": "goto", "arguments": {"url": f"{SITE}/sales/order/#grid"}},
        {
            "type": "tool_result",
            "content": f'Clicked [7] "Save". Now on: Orders ({SITE}/sales/order/view/order_id/7/)',
        },
        {"type": "tool_call", "name": "click", "arguments": None},
    )

    assert shown_urls(events) == {
        f"{SITE}/admin/dashboard",
        f"{SITE}/sales/order",
        f"{SITE}/sales/order/view/order_id/7",
    }


def test_a_page_loaded_in_another_tab_is_found():
    """Task 216 of baseline_test_r3: the product page opened in a new tab."""
    events = log(
        observation(f"{SITE}/admin/dashboard/"), observation(f"{SITE}/review/product/edit/id/349/")
    )
    trace = [
        document(SITE, status=302),
        document(f"{SITE}/admin/dashboard/"),
        document(f"{SITE}/mui/index/render/", kind="XHR"),
        document(f"{SITE}/review/product/edit/id/349/"),
        document(f"{SITE}/catalog/product/edit/id/1604/"),
    ]

    assert unshown_documents(events, trace) == [f"{SITE}/catalog/product/edit/id/1604/"]


def test_redirect_hops_and_other_requests_are_not_pages_anybody_was_shown():
    events = log(observation(f"{SITE}/admin/dashboard/"))
    trace = [
        document(SITE, status=302),
        document(f"{SITE}/admin/dashboard/"),
        document(f"{SITE}/static/app.js", kind="Script"),
        document(f"{SITE}/notification/markAsRead/", kind="XHR"),
    ]

    assert unshown_documents(events, trace) == []
