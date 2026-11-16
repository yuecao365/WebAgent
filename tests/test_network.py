"""HAR building from CDP events: saved events from the real site, plus small cases."""

from __future__ import annotations

from webarena_verified.types.tracing import NetworkTrace

from browser_agent.browser.network import HarBuilder

from fakes import load_fixture


def built(events):
    builder = HarBuilder()
    for event in events:
        builder.feed(event["method"], event["params"], event.get("session_id"))
    return builder


def headers(part):
    return {header["name"].lower(): header["value"] for header in part["headers"]}


def test_saved_page_loads_become_har_entries():
    entries = built(load_fixture("cdp_network.json")).entries()

    summary = [
        (e["request"]["method"], e["response"]["status"], e["_resourceType"]) for e in entries
    ]
    assert summary == [
        ("GET", 302, "Document"),
        ("GET", 200, "Document"),
        ("GET", 200, "Document"),
        ("GET", 200, "XHR"),
    ]
    assert entries[0]["request"]["url"] == "http://localhost:7780/admin"
    assert entries[1]["request"]["url"] == "http://localhost:7780/admin/admin/dashboard/"
    assert "mui/index/render" in entries[3]["request"]["url"]


def test_static_assets_are_left_out():
    events = load_fixture("cdp_network.json")
    requested = {e["params"]["type"] for e in events if e["method"] == "Network.requestWillBeSent"}

    assert {"Stylesheet", "Script"} <= requested
    types = {entry["_resourceType"] for entry in built(events).entries()}
    assert types == {"Document", "XHR"}


def test_a_redirect_is_two_entries_and_the_first_names_its_target():
    first, second = built(load_fixture("cdp_network.json")).entries()[:2]

    assert first["response"]["status"] == 302
    assert first["response"]["redirectURL"] == second["request"]["url"]
    assert second["response"]["redirectURL"] == ""


def test_real_request_headers_come_from_the_extra_info_events():
    document = built(load_fixture("cdp_network.json")).entries()[2]
    sent = headers(document["request"])

    # The main event carries provisional headers only; these arrive separately.
    assert sent["sec-fetch-dest"] == "document"
    assert sent["sec-fetch-mode"] == "navigate"
    assert "cookie" in sent
    assert sent["x-m2-admin-auto-login"].startswith("admin:")


def test_xhr_keeps_its_referer():
    xhr = built(load_fixture("cdp_network.json")).entries()[3]

    assert headers(xhr["request"])["referer"] == "http://localhost:7780/admin/customer/index/"


def test_the_official_evaluator_reads_the_trace():
    trace = NetworkTrace.from_content(built(load_fixture("cdp_network.json")).entries())

    assert not trace.is_playwright
    navigations = [event.url for event in trace.events if event.is_navigation_event]
    assert navigations == [
        "http://localhost:7780/admin",
        "http://localhost:7780/admin/admin/dashboard/",
        "http://localhost:7780/admin/customer/index/",
    ]
    assert trace.events[0].is_redirect
    assert trace.events[0].redirect_url == "http://localhost:7780/admin/admin/dashboard/"
    assert trace.events[3].request_status == 200


def request(request_id, url, method="GET", resource="Document", **extra):
    payload = {"url": url, "method": method, "headers": {"Accept": "text/html"}, **extra}
    return {
        "method": "Network.requestWillBeSent",
        "params": {"requestId": request_id, "request": payload, "type": resource, "wallTime": 1.0},
    }


def response(request_id, status=200, resource="Document", response_headers=None):
    payload = {"status": status, "headers": response_headers or {}, "mimeType": "text/html"}
    return {
        "method": "Network.responseReceived",
        "params": {"requestId": request_id, "response": payload, "type": resource},
    }


def test_form_posts_keep_their_body_and_content_type():
    body = "product%5Bstatus%5D=2&form_key=abc"
    events = [
        request(
            "r1",
            "http://site.test/admin/catalog/product/save/id/78/",
            method="POST",
            postData=body,
            hasPostData=True,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ),
        response("r1", status=302, response_headers={"Location": "http://site.test/admin/x/"}),
    ]

    entry = built(events).entries()[0]
    trace = NetworkTrace.from_content([entry])

    assert entry["request"]["postData"] == {
        "mimeType": "application/x-www-form-urlencoded",
        "text": body,
    }
    assert trace.events[0].post_data == {"product[status]": "2", "form_key": "abc"}
    assert trace.events[0].redirect_url == "http://site.test/admin/x/"


def test_extra_info_may_arrive_before_the_request_event():
    extra = {
        "method": "Network.requestWillBeSentExtraInfo",
        "params": {"requestId": "r1", "headers": {"Sec-Fetch-Dest": "document", "Cookie": "a=b"}},
    }
    events = [extra, request("r1", "http://site.test/admin/"), response("r1")]

    sent = headers(built(events).entries()[0]["request"])

    assert sent["sec-fetch-dest"] == "document"
    assert sent["accept"] == "text/html"


def test_the_status_of_the_wire_wins_over_the_cached_one():
    extra = {
        "method": "Network.responseReceivedExtraInfo",
        "params": {"requestId": "r1", "statusCode": 304, "headers": {"ETag": "x"}},
    }
    events = [request("r1", "http://site.test/a"), response("r1", status=200), extra]

    assert built(events).entries()[0]["response"]["status"] == 304


def test_requests_without_a_response_are_left_out():
    events = [
        request("r1", "http://site.test/a"),
        request("r2", "http://site.test/b"),
        response("r2"),
    ]

    urls = [entry["request"]["url"] for entry in built(events).entries()]

    assert urls == ["http://site.test/b"]


def test_same_request_id_in_two_tabs_stays_apart():
    builder = HarBuilder()
    for session, url in (("S1", "http://site.test/one"), ("S2", "http://site.test/two")):
        event = request("r1", url)
        builder.feed(event["method"], event["params"], session)
    for session in ("S1", "S2"):
        event = response("r1")
        builder.feed(event["method"], event["params"], session)

    assert [entry["request"]["url"] for entry in builder.entries()] == [
        "http://site.test/one",
        "http://site.test/two",
    ]


def test_clear_forgets_everything():
    builder = built([request("r1", "http://site.test/a"), response("r1")])

    builder.clear()

    assert builder.har()["log"]["entries"] == []
