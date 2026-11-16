"""Action primitives: goto, click, type and scroll.

Elements are addressed by the refs the observation prints, which are CDP backend
node ids. They stay valid while the node lives, so a ref from an older observation
either still means the same element or fails with a clear error.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from browser_agent.browser.session import Browser, BrowserError


class ActionError(RuntimeError):
    """The action could not be carried out; the message is written for the model."""


# `this` is the node behind the ref; a text node stands in for its parent element.
_ELEMENT = "const el = this.nodeType === 1 ? this : this.parentElement;"

_DESCRIBE_JS = f"""function() {{
  {_ELEMENT}
  if (!el) return null;
  const tag = el.tagName.toLowerCase();
  const type = (el.getAttribute('type') || '').toLowerCase();
  const typable = ['', 'text', 'search', 'email', 'url', 'tel', 'password', 'number',
                   'date', 'datetime-local', 'month', 'time', 'week'];
  const clean = s => (s || '').replace(/\\s+/g, ' ').trim();
  const field = ['input', 'textarea', 'select'].includes(tag);
  const ownLabel = el.labels && el.labels.length ? el.labels[0].innerText : '';
  // What a person would call the element: a field by its label, the rest by its text.
  const label = clean(el.getAttribute('aria-label') || ownLabel
    || (field ? el.getAttribute('placeholder') : el.innerText)
    || el.getAttribute('title') || (field ? el.getAttribute('name') : '')).slice(0, 60);
  const tr = el.closest('tr');
  return {{
    tag: tag,
    option: tag === 'option',
    select: tag === 'select',
    editable: tag === 'textarea' || el.isContentEditable
      || (tag === 'input' && typable.includes(type)),
    disabled: !!el.disabled,
    label: label,
    row: tr && tr !== el ? clean(tr.innerText).slice(0, 90) : '',
  }};
}}"""


def _described(info: dict[str, Any]) -> str:
    """The element in words, for the result line the history keeps.

    The history has no pages, so "Clicked [8123]" alone would not tell the model
    later which link, or which row of a table, it had already been to.
    """
    label, row = info.get("label") or "", info.get("row") or ""
    text = f" {json.dumps(label, ensure_ascii=False)}" if label else ""
    if row and row != label:
        text += f" in row {json.dumps(row, ensure_ascii=False)}"
    return text


_SELECT_OPTION_JS = f"""function() {{
  {_ELEMENT}
  const select = el.closest('select');
  if (!select) return false;
  el.selected = true;
  select.dispatchEvent(new Event('input', {{bubbles: true}}));
  select.dispatchEvent(new Event('change', {{bubbles: true}}));
  return true;
}}"""

_CHOOSE_BY_TEXT_JS = f"""function(wanted) {{
  {_ELEMENT}
  const norm = s => (s || '').trim().toLowerCase();
  const options = Array.from(el.options);
  const target = norm(wanted);
  const match = options.find(o => norm(o.label) === target || norm(o.value) === target)
    || options.find(o => norm(o.label).includes(target));
  if (!match) return {{ok: false, options: options.map(o => o.label.trim()).slice(0, 50)}};
  match.selected = true;
  el.dispatchEvent(new Event('input', {{bubbles: true}}));
  el.dispatchEvent(new Event('change', {{bubbles: true}}));
  return {{ok: true, chosen: match.label.trim()}};
}}"""

_SELECT_CONTENT_JS = f"""function() {{
  {_ELEMENT}
  el.focus();
  if (typeof el.select === 'function') {{ el.select(); return; }}
  const range = document.createRange();
  range.selectNodeContents(el);
  const selection = getSelection();
  selection.removeAllRanges();
  selection.addRange(range);
}}"""

_FIRE_CHANGE_JS = f"""function() {{
  {_ELEMENT}
  el.dispatchEvent(new Event('change', {{bubbles: true}}));
}}"""

_READ_VALUE_JS = f"""function() {{
  {_ELEMENT}
  const value = 'value' in el ? el.value : el.textContent;
  return String(value == null ? '' : value).slice(0, 200);
}}"""

_SCRIPT_CLICK_JS = f"""function() {{
  {_ELEMENT}
  el.click();
}}"""

_VIEWPORT_JS = "JSON.stringify({w: innerWidth, h: innerHeight})"


def _call(browser: Browser, ref: int, function: str, *args: Any) -> Any:
    """Run a function with `this` bound to the node behind ref."""
    try:
        resolved = browser.cdp("DOM.resolveNode", backendNodeId=ref)
    except BrowserError as exc:
        raise ActionError(
            f"ref {ref} is not on the current page; read the page again and use a ref from it"
        ) from exc
    result = browser.cdp(
        "Runtime.callFunctionOn",
        objectId=resolved["object"]["objectId"],
        functionDeclaration=function,
        arguments=[{"value": arg} for arg in args],
        returnByValue=True,
    )
    if "exceptionDetails" in result:
        text = result["exceptionDetails"].get("exception", {}).get("description", "script error")
        raise ActionError(f"the page raised an error: {text.splitlines()[0]}")
    return result.get("result", {}).get("value")


def _describe(browser: Browser, ref: int) -> dict[str, Any]:
    info = _call(browser, ref, _DESCRIBE_JS)
    if not info:
        raise ActionError(f"ref {ref} has no element to act on")
    if info["disabled"]:
        raise ActionError(f"element [{ref}] is disabled")
    return info


def _center(browser: Browser, ref: int) -> tuple[float, float] | None:
    """Viewport coordinates of the middle of the element, or None when it has no box."""
    try:
        browser.cdp("DOM.scrollIntoViewIfNeeded", backendNodeId=ref)
        quads = browser.cdp("DOM.getContentQuads", backendNodeId=ref).get("quads", [])
    except BrowserError:
        return None
    if not quads:
        return None
    quad = quads[0]
    return sum(quad[0::2]) / 4, sum(quad[1::2]) / 4


def goto(browser: Browser, url: str) -> str:
    """Navigate the tab to url."""
    result = browser.cdp("Page.navigate", url=url)
    if result.get("errorText"):
        raise ActionError(f"could not open {url}: {result['errorText']}")
    browser.settle()
    return f"Opened {url}."


def click(browser: Browser, ref: int) -> str:
    """Click the element behind ref."""
    info = _describe(browser, ref)
    if info["option"]:
        # A native dropdown list is drawn outside the page and cannot be clicked.
        if not _call(browser, ref, _SELECT_OPTION_JS):
            raise ActionError(f"option [{ref}] does not belong to a select")
        browser.settle()
        return f"Selected option [{ref}]{_described(info)}."
    center = _center(browser, ref)
    if center is None:
        # Styled checkboxes and similar controls are often visually hidden inputs.
        _call(browser, ref, _SCRIPT_CLICK_JS)
        browser.settle()
        return f"Clicked [{ref}]{_described(info)} by script because it has no visible box."
    browser.click_at(*center)
    browser.settle()
    return f"Clicked [{ref}]{_described(info)}."


def type_text(browser: Browser, ref: int, text: str, submit: bool = False) -> str:
    """Replace the content of a text field, or choose an option of a select by its label."""
    info = _describe(browser, ref)
    if info["select"]:
        chosen = _call(browser, ref, _CHOOSE_BY_TEXT_JS, text)
        if not chosen["ok"]:
            options = json.dumps(chosen["options"], ensure_ascii=False)
            raise ActionError(f"select [{ref}] has no option matching {text!r}; options: {options}")
        browser.settle()
        return f"Chose {chosen['chosen']!r} in select [{ref}]{_described(info)}."
    if not info["editable"]:
        raise ActionError(f"element [{ref}] is a <{info['tag']}>, not a text field or select")
    _call(browser, ref, _SELECT_CONTENT_JS)
    if text:
        browser.insert_text(text)
    else:
        browser.press_key("Backspace")
    # Some form bindings only pick the value up on a change event.
    _call(browser, ref, _FIRE_CHANGE_JS)
    # Read the field back before Enter can replace the page: an input mask or a
    # length limit may have changed what was typed.
    value = _call(browser, ref, _READ_VALUE_JS)
    if submit:
        browser.press_key("Enter")
    browser.settle()
    suffix = " and pressed Enter" if submit else ""
    differs = value is not None and value != text
    note = f" The field reads {value!r}." if differs else ""
    return f"Typed {text!r} into [{ref}]{_described(info)}{suffix}.{note}"


def scroll(browser: Browser, direction: Literal["up", "down"]) -> str:
    """Scroll the page by most of one viewport."""
    evaluated = browser.cdp("Runtime.evaluate", expression=_VIEWPORT_JS, returnByValue=True)
    viewport = json.loads(evaluated.get("result", {}).get("value") or '{"w": 1280, "h": 900}')
    distance = viewport["h"] * 0.8
    dy = distance if direction == "down" else -distance
    browser.wheel(viewport["w"] / 2, viewport["h"] / 2, dy)
    browser.settle()
    return f"Scrolled {direction}."
