"""Bounded subprocess: an unresponsive AT-SPI application cannot wedge MCP."""
import json
import sys
import time
import math
from collections import deque

import gi
gi.require_version("Atspi", "2.0")
from gi.repository import Atspi

Atspi.set_timeout(600, 1000)


def identity(pid):
    from pathlib import Path
    return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]


def describe(node, pid):
    interfaces = node.get_interfaces()
    state = node.get_state_set()
    states = [s.value_nick for s in state.get_states()]
    protected = "password" in node.get_role_name().lower()
    r = {"pid": pid, "start": identity(pid), "path": node.path,
         "name": "[protected]" if protected else (node.get_name() or "")[:300],
         "role": node.get_role_name(), "states": states, "interfaces": interfaces,
         "protected": protected}
    if "Component" in interfaces:
        rect = node.get_component_iface().get_extents(Atspi.CoordType.SCREEN)
        r["bounds"] = {"x": rect.x, "y": rect.y, "width": rect.width, "height": rect.height}
    if "Action" in interfaces:
        action = node.get_action_iface()
        r["actions"] = [action.get_action_name(i) for i in range(action.get_n_actions())]
    if "Value" in interfaces and not protected:
        value = node.get_value_iface()
        r["value"] = {"current": value.get_current_value(), "minimum": value.get_minimum_value(),
                      "maximum": value.get_maximum_value(), "increment": value.get_minimum_increment()}
    return r


def candidates(pid, limit=1600, depth=30, root_path=None, stats=None):
    stats = stats if stats is not None else {}
    stats.setdefault("budget_pruned", False)
    stats.setdefault("depth_pruned", False)
    stats.setdefault("unreadable_branches", 0)
    desktop = Atspi.get_desktop(0)
    q = deque()
    for i in range(desktop.get_child_count()):
        app = desktop.get_child_at_index(i)
        if app and app.get_process_id() == pid:
            q.append((app, 0))
    if root_path:
        roots = []
        for app, _ in q:
            for i in range(app.get_child_count()):
                root = app.get_child_at_index(i)
                if root and root.path == root_path:
                    roots.append((root, 0))
        q = deque(roots)
    count = 0
    while q and count < limit:
        node, level = q.popleft()
        count += 1
        yield node, level
        try:
            children = node.get_child_count()
        except Exception:
            stats["unreadable_branches"] += 1
            continue
        if level < depth:
            capacity = max(0, limit - count - len(q))
            if children > capacity:
                stats["budget_pruned"] = True
            for i in range(min(children, capacity)):
                try:
                    child = node.get_child_at_index(i)
                except Exception:
                    stats["unreadable_branches"] += 1
                    continue
                if child:
                    q.append((child, level + 1))
        elif children:
            stats["depth_pruned"] = True


def failure(code, message):
    return {"error": code, "message": message}


def verify(predicate, timeout=.35):
    deadline = time.monotonic() + timeout
    while True:
        if predicate():
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(.025)


def states_of(node):
    return {s.value_nick for s in node.get_state_set().get_states()}


class TextAccess:
    """Normalize providers that use UTF-16 offsets (Qt) to Unicode code points.

    Never infer offsets from application names. The reported count must agree
    with either the actual code-point count or UTF-16 count of bounded readback.
    """
    def __init__(self, raw):
        self.raw = raw
        app = raw.get_application() if hasattr(raw, "get_application") else None
        self.toolkit = (app.get_toolkit_name() or "") if app else ""
        self._refresh()

    def _refresh(self):
        count = Atspi.Text.get_character_count(self.raw)
        if not 0 <= count <= 2_000_000:
            raise ValueError("Text provider exceeds the bounded offset-normalization budget.")
        text = Atspi.Text.get_text(self.raw, 0, count)
        if len(text) > 1_000_000:
            raise ValueError("Text provider exceeds the one-million-code-point budget.")
        if count == len(text):
            self.utf16 = self.toolkit.casefold() == "qt"
        elif count == len(text.encode("utf-16-le")) // 2:
            self.utf16 = True
        else:
            raise ValueError("Text changed or provider character offsets are unsupported.")
        self.text = text

    def insertion_length(self, text):
        return len(text.encode("utf-16-le")) // 2 if self.utf16 else len(text.encode("utf-8"))

    def provider_offset(self, position):
        if not 0 <= position <= len(self.text):
            raise ValueError("Text position is outside the verified content.")
        return len(self.text[:position].encode("utf-16-le")) // 2 if self.utf16 else position

    def public_offset(self, position):
        if position < 0:
            return position
        if not self.utf16:
            return position
        encoded = self.text.encode("utf-16-le")
        if position * 2 > len(encoded):
            raise ValueError("Provider position is outside verified text.")
        return len(encoded[:position * 2].decode("utf-16-le"))

    def get_text(self, start, end):
        self._refresh()
        return self.text[start:None if end == -1 else end]

    def get_character_count(self):
        self._refresh()
        return len(self.text)

    def get_caret_offset(self):
        return self.public_offset(Atspi.Text.get_caret_offset(self.raw))

    def set_caret_offset(self, position):
        return Atspi.Text.set_caret_offset(self.raw, self.provider_offset(position))

    def get_n_selections(self):
        return Atspi.Text.get_n_selections(self.raw)

    def get_selection(self, index):
        from types import SimpleNamespace
        selection = Atspi.Text.get_selection(self.raw, index)
        return SimpleNamespace(start_offset=self.public_offset(selection.start_offset),
                               end_offset=self.public_offset(selection.end_offset))

    def add_selection(self, start, end):
        return Atspi.Text.add_selection(self.raw, self.provider_offset(start), self.provider_offset(end))

    def set_selection(self, index, start, end):
        return Atspi.Text.set_selection(self.raw, index, self.provider_offset(start), self.provider_offset(end))

    def remove_selection(self, index):
        return Atspi.Text.remove_selection(self.raw, index)


def semantic(node, current, req):
    """Return None for legacy operations. Never emulate unsupported semantics by typing."""
    op = req["op"]
    if op in ("insert", "select"):
        if current["protected"]:
            return failure("PROTECTED_FIELD", "Protected text cannot be read or changed.")
        if "Text" not in current["interfaces"]:
            return failure("UNSUPPORTED", "Operation requires the Text interface.")
        t = TextAccess(node.get_text_iface())
        if t.get_character_count() > 1_000_000:
            return failure("TEXT_TOO_LARGE", "Full verification exceeds the one-million-character budget.")
        before = t.get_text(0, t.get_character_count())
        if len(before) > 1_000_000:
            return failure("TEXT_TOO_LARGE", "Text grew beyond the verification budget.")
        if op == "select":
            start, end = req.get("start_offset"), req.get("end_offset")
            if any(type(x) is not int for x in (start, end)) or not 0 <= start <= end <= len(before):
                return failure("INVALID_ARGUMENT", "Selection offsets must satisfy 0 <= start <= end <= character count.")
            count = t.get_n_selections()
            if count > 1:
                return failure("UNSUPPORTED", "Multiple selections cannot be changed safely.")
            if start == end:
                if count:
                    t.remove_selection(0)
                accepted = t.set_caret_offset(start)
                matched = verify(lambda: t.get_n_selections() == 0 and t.get_caret_offset() == start)
            else:
                accepted = t.set_selection(0, start, end) if count else t.add_selection(start, end)
                def selection_matches():
                    if t.get_n_selections() != 1:
                        return False
                    sel = t.get_selection(0)
                    return (sel.start_offset, sel.end_offset) == (start, end)
                matched = verify(selection_matches)
            return {"accepted": bool(accepted), "effect": "verified" if matched else "uncertain",
                    "exact_match": matched, "start_offset": start, "end_offset": end}
        text = req.get("text")
        if not isinstance(text, str) or len(text) > 1_000_000 or any(c in text for c in ('\0', '\r')) or any(0xD800 <= ord(c) <= 0xDFFF for c in text):
            return failure("UNSUPPORTED_TEXT", "Text must be valid Unicode without NUL or CR and at most one million characters.")
        if "EditableText" not in current["interfaces"] or "editable" not in current["states"]:
            return failure("NOT_EDITABLE", "Insertion requires editable Text and EditableText interfaces.")
        count = t.get_n_selections()
        if count > 1:
            return failure("UNSUPPORTED", "Multiple selections cannot be replaced safely.")
        if count:
            selected = t.get_selection(0)
            start, end = sorted((selected.start_offset, selected.end_offset))
        else:
            start = end = t.get_caret_offset()
        if not 0 <= start <= end <= len(before):
            return failure("INVALID_SELECTION", "Provider returned invalid caret or selection offsets.")
        expected = before[:start] + text + before[end:]
        if len(expected) > 1_000_000:
            return failure("TEXT_TOO_LARGE", "Result exceeds verification budget.")
        edit = node.get_editable_text_iface()
        # Read again immediately before mutation to refuse a concurrent text edit.
        current_count = t.get_n_selections()
        if current_count == 1:
            selection_now = t.get_selection(0)
            range_now = tuple(sorted((selection_now.start_offset, selection_now.end_offset)))
        elif current_count == 0:
            caret_now = t.get_caret_offset()
            range_now = (caret_now, caret_now)
        else:
            range_now = None
        if t.get_text(0, -1) != before or range_now != (start, end):
            return failure("STALE_TARGET", "Text changed before insertion; inspect again.")
        accepted = True
        if end > start:
            accepted = bool(edit.delete_text(t.provider_offset(start), t.provider_offset(end)))
            if not accepted or not verify(lambda: t.get_text(0, -1) == before[:start] + before[end:]):
                return {"effect": "uncertain", "accepted": accepted, "exact_match": False,
                        "verification": "Selection deletion was rejected; inspect before retrying."}
        # GTK consumes UTF-8 length; Qt bridge consumes UTF-16 units. Normalize
        # this separately from public code-point positions to avoid NUL padding.
        if text:
            accepted = bool(edit.insert_text(t.provider_offset(start), text, t.insertion_length(text)))
        matched = verify(lambda: t.get_text(0, -1) == expected)
        caret_verified = False
        if matched:
            for _ in range(min(t.get_n_selections(), 100)):
                if not t.remove_selection(0):
                    break
            wanted_caret = start + len(text)
            caret_verified = t.get_n_selections() == 0 and t.get_caret_offset() == wanted_caret
            if not caret_verified:
                try:
                    t.set_caret_offset(wanted_caret)
                    caret_verified = verify(lambda: t.get_n_selections() == 0 and t.get_caret_offset() == wanted_caret)
                except Exception:
                    # Text is already independently read back exactly. A provider
                    # lacking caret mutation must not erase that verified outcome.
                    caret_verified = False
        return {"effect": "verified" if matched else "uncertain", "accepted": accepted,
                "exact_match": matched, "expected_characters": len(expected),
                "actual_characters": t.get_character_count(),
                "replaced_characters": end-start, "inserted_characters": len(text),
                "caret_verified": caret_verified, "caret_offset": t.get_caret_offset()}
    if op == "value":
        value = req.get("value")
        if type(value) not in (int, float) or not math.isfinite(value):
            return failure("INVALID_ARGUMENT", "Value must be a finite number.")
        if "Value" not in current["interfaces"]:
            return failure("UNSUPPORTED", "Element has no Value interface.")
        v = node.get_value_iface()
        if not v.get_minimum_value() <= value <= v.get_maximum_value():
            return failure("OUT_OF_BOUNDS", "Value is outside the reported range.")
        accepted = bool(v.set_current_value(value))
        matched = verify(lambda: v.get_current_value() == value)
        return {"effect": "verified" if matched else "uncertain", "accepted": accepted,
                "exact_match": matched, "actual_value": v.get_current_value()}
    if op in ("check", "expand"):
        key, state = ("checked", "checked") if op == "check" else ("expanded", "expanded")
        desired = req.get(key)
        if type(desired) is not bool:
            return failure("INVALID_ARGUMENT", f"{key} must be a boolean.")
        if op == "check" and not ({"checkable", "checked", "indeterminate"} & set(current["states"])) and current["role"] not in ("check box", "radio button", "toggle button", "check menu item"):
            return failure("UNSUPPORTED", "Element is not a checkable control.")
        if op == "expand" and "expandable" not in current["states"]:
            return failure("UNSUPPORTED", "Element is not expandable.")
        def matches():
            current_states = states_of(node)
            return (state in current_states) == desired and "indeterminate" not in current_states
        if matches():
            return {"effect": "verified", "accepted": True, "changed": False, key: desired}
        actions = current.get("actions", [])
        eligible = ("toggle", "click", "activate") if op == "check" else ("expand or contract", "expand or collapse", "toggle", "activate")
        action = next((actual for a in eligible for actual in actions if actual.casefold() == a), None)
        if action is None:
            return failure("UNSUPPORTED_ACTION", "No recognized semantic state-changing action is available.")
        accepted = bool(node.get_action_iface().do_action(actions.index(action)))
        matched = verify(matches)
        return {"effect": "verified" if matched else "uncertain", "accepted": accepted,
                "changed": matched, key: state in states_of(node)}
    return None


def main(req):
    pid = req["pid"]
    if req.get("op") not in {"inspect", "read", "set", "focus", "invoke", "insert", "select", "value", "check", "expand"}:
        return failure("UNSUPPORTED_OPERATION", "Unknown accessibility operation.")
    if req.get("start") and identity(pid) != req["start"]:
        return {"error": "STALE_TARGET", "message": "Process identity changed."}
    if req["op"] == "inspect":
        # Match the accessible top-level to the X11 CLIENT rectangle. Never expose
        # sibling windows as if they belonged to the selected target.
        if type(req.get("limit", 150)) is not int or not 1 <= req.get("limit", 150) <= 500:
            return failure("INVALID_ARGUMENT", "Inspection limit must be an integer from 1 to 500.")
        bounds = req["bounds"]
        roots = []
        fallback_roots = []
        title_size_matches = []
        scope_stats = {}
        for candidate, depth in candidates(pid, limit=200, depth=1, stats=scope_stats):
            if depth != 1 or "Component" not in candidate.get_interfaces():
                continue
            rect = candidate.get_component_iface().get_extents(Atspi.CoordType.SCREEN)
            if any(all(abs(a-b)<=2 for a,b in zip((rect.x,rect.y,rect.width,rect.height),
                       (b["x"],b["y"],b["width"],b["height"]))) for b in (bounds,req["frame_bounds"])):
                roots.append(candidate.path)
            if (req.get("window_title") and candidate.get_name() == req["window_title"]
                    and rect.width == bounds["width"] and rect.height == bounds["height"]):
                title_size_matches.append(candidate.path)
                if rect.x == 0 and rect.y == 0:
                    fallback_roots.append(candidate.path)
        if scope_stats.get("budget_pruned") or scope_stats.get("unreadable_branches"):
            return failure("AMBIGUOUS_ACCESSIBILITY_WINDOW", "Cannot prove uniqueness within the top-level traversal budget.")
        mapping = "screen_bounds"
        if not roots and len(fallback_roots) == 1 and len(title_size_matches) == 1:
            roots = fallback_roots
            mapping = "unique_title_and_size"
        if len(roots) != 1:
            return {"error":"AMBIGUOUS_ACCESSIBILITY_WINDOW", "message":"Cannot uniquely map X11 client bounds to an accessible top-level; use screenshot controls."}
        root_path = roots[0]
        nodes = []
        errors = 0
        began = time.monotonic()
        truncated = False
        max_depth = req.get("max_depth", 30)
        filters = req.get("filters", {})
        if type(max_depth) is not int or not 0 <= max_depth <= 60 or not isinstance(filters, dict):
            return failure("INVALID_ARGUMENT", "max_depth must be 0..60 and filters an object.")
        if set(filters) - {"name", "role", "states"} or any(not isinstance(filters[k], str) for k in ("name", "role") if k in filters) or ("states" in filters and (not isinstance(filters["states"], list) or any(not isinstance(x, str) for x in filters["states"]))):
            return failure("INVALID_ARGUMENT", "Filters accept name/role substring strings and a list of required states.")
        visited = 0
        traversal = {}
        for node, depth in candidates(pid,root_path=root_path, depth=max_depth, stats=traversal):
            visited += 1
            if len(nodes) >= req.get("limit", 150) or time.monotonic() - began > 3:
                truncated = True
                break
            try:
                value = describe(node, pid)
                parent = node.get_parent()
                value["parent_path"] = parent.path if parent else None
                value["depth"] = depth
                value["root_path"] = root_path
                value["bounds_coordinates"] = "unavailable" if mapping == "unique_title_and_size" else "screen"
                if mapping == "unique_title_and_size":
                    value.pop("bounds", None)
                if any(filters.get(k, "").casefold() not in value[k].casefold() for k in ("name", "role")):
                    continue
                if not set(filters.get("states", [])).issubset(value["states"]):
                    continue
                nodes.append(value)
            except Exception:
                errors += 1
        return {"nodes": nodes, "truncated": truncated or any(traversal.values()), "truncation": {"result_or_time_limit": truncated, **traversal}, "visited_nodes": visited, "max_depth": max_depth, "unreadable_nodes": errors, "unreadable_branches": traversal.get("unreadable_branches", 0),
                "coverage": "selected accessible top-level window", "available": visited > 0,
                "window_mapping": mapping, "bounds_coordinates": "unavailable" if mapping == "unique_title_and_size" else "screen"}
    target = req["target"]
    for node, _ in candidates(pid,root_path=target["root_path"]):
        if node.path != target["path"]:
            continue
        current = describe(node, pid)
        if any(current[k] != target[k] for k in ("role", "name", "start")) or "defunct" in current["states"]:
            return {"error": "STALE_TARGET", "message": "Element identity changed; inspect again."}
        op = req["op"]
        if op != "read" and ("showing" not in current["states"] or not {"enabled", "sensitive"}.intersection(current["states"])):
            return {"error": "NOT_INTERACTABLE", "message": "Element must be enabled and showing for mutation; inspect the visible target."}
        if op in ("read", "set", "insert", "select", "value") and current["protected"]:
            return {"error": "PROTECTED_FIELD", "message": "This implementation does not read or write protected fields."}
        result = semantic(node, current, req)
        if result is not None:
            return result
        if op == "read":
            if "Text" not in current["interfaces"]:
                return {"error": "UNSUPPORTED", "message": "Element has no Text interface."}
            t = TextAccess(node.get_text_iface())
            n = t.get_character_count()
            limit = req.get("limit", 16000)
            if type(limit) is not int or not 1 <= limit <= 1_000_000:
                return failure("INVALID_ARGUMENT", "Text read limit must be 1..1000000.")
            return {"text": t.get_text(0, min(n, limit)), "characters": n, "truncated": n > limit,
                    "caret_offset": t.get_caret_offset(), "offset_units": "Unicode code points", "provider_offset_units": "UTF-16 code units" if t.utf16 else "Unicode code points",
                    "selections": [{"start_offset": sel.start_offset, "end_offset": sel.end_offset}
                                   for sel in (t.get_selection(i) for i in range(min(t.get_n_selections(), 100)))],
                    "selections_truncated": t.get_n_selections() > 100}
        if op == "set":
            if "EditableText" not in current["interfaces"] or "Text" not in current["interfaces"]:
                return {"error": "UNSUPPORTED", "message": "Exact replacement requires EditableText and Text."}
            if "editable" not in current["states"] or not {"enabled", "sensitive"}.intersection(current["states"]):
                return {"error": "NOT_EDITABLE", "message": "Element is not editable and enabled."}
            text = req["text"]
            accepted = node.get_editable_text_iface().set_text_contents(text)
            actual = Atspi.Text.get_text(node.get_text_iface(), 0, -1)
            return {"effect": "verified" if actual == text else "uncertain", "accepted": accepted,
                    "exact_match": actual == text, "expected_characters": len(text),
                    "actual_characters": len(actual)}
        if op == "focus":
            if "focused" in current["states"]:
                return {"effect": "verified", "accepted": True, "focused": True, "changed": False}
            if "Component" not in current["interfaces"]:
                return {"error": "UNSUPPORTED", "message": "Element has no Component interface."}
            ok = node.get_component_iface().grab_focus()
            focused = verify(lambda: "focused" in states_of(node))
            return {"effect": "verified" if focused else "uncertain", "accepted": bool(ok), "focused": focused}
        if op == "invoke":
            action_name = req["action"]
            if action_name not in current.get("actions", []):
                return {"error": "UNSUPPORTED_ACTION", "message": "Select an action returned by inspect."}
            ok = node.get_action_iface().do_action(current["actions"].index(action_name))
            return {"effect": "dispatched" if ok else "uncertain", "accepted": ok,
                    "verification": "Application outcome not verified; observe next."}
    return {"error": "STALE_TARGET", "message": "Element not found within traversal budget; inspect again."}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"error": "ACCESSIBILITY_ERROR", "message": str(exc)[:500]}))
