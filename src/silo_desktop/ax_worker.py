"""Bounded subprocess: an unresponsive AT-SPI application cannot wedge MCP."""
import json
import sys
import time
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
    return r


def candidates(pid, limit=1600, depth=30, root_path=None):
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
        if level < depth:
            for i in range(min(node.get_child_count(), limit - count)):
                child = node.get_child_at_index(i)
                if child:
                    q.append((child, level + 1))


def main(req):
    pid = req["pid"]
    if req.get("start") and identity(pid) != req["start"]:
        return {"error": "STALE_TARGET", "message": "Process identity changed."}
    if req["op"] == "inspect":
        # Match the accessible top-level to the X11 CLIENT rectangle. Never expose
        # sibling windows as if they belonged to the selected target.
        bounds = req["bounds"]
        roots = []
        for candidate, depth in candidates(pid, limit=200, depth=1):
            if depth != 1 or "Component" not in candidate.get_interfaces():
                continue
            rect = candidate.get_component_iface().get_extents(Atspi.CoordType.SCREEN)
            if any(all(abs(a-b)<=2 for a,b in zip((rect.x,rect.y,rect.width,rect.height),
                       (b["x"],b["y"],b["width"],b["height"]))) for b in (bounds,req["frame_bounds"])):
                roots.append(candidate.path)
        if len(roots) != 1:
            return {"error":"AMBIGUOUS_ACCESSIBILITY_WINDOW", "message":"Cannot uniquely map X11 client bounds to an accessible top-level; use screenshot controls."}
        root_path = roots[0]
        nodes = []
        errors = 0
        began = time.monotonic()
        truncated = False
        for node, depth in candidates(pid,root_path=root_path):
            if len(nodes) >= req.get("limit", 150) or time.monotonic() - began > 3:
                truncated = True
                break
            try:
                value = describe(node, pid)
                value["depth"] = depth
                value["root_path"] = root_path
                nodes.append(value)
            except Exception:
                errors += 1
        return {"nodes": nodes, "truncated": truncated, "unreadable_nodes": errors,
                "coverage": "selected accessible top-level window", "available": bool(nodes)}
    target = req["target"]
    for node, _ in candidates(pid,root_path=target["root_path"]):
        if node.path != target["path"]:
            continue
        current = describe(node, pid)
        if any(current[k] != target[k] for k in ("role", "name", "start")) or "defunct" in current["states"]:
            return {"error": "STALE_TARGET", "message": "Element identity changed; inspect again."}
        op = req["op"]
        if op != "read" and not {"enabled", "showing"}.issubset(current["states"]):
            return {"error": "NOT_INTERACTABLE", "message": "Element must be enabled and showing for mutation; inspect the visible target."}
        if op in ("read", "set") and current["protected"]:
            return {"error": "PROTECTED_FIELD", "message": "This implementation does not read or write protected fields."}
        if op == "read":
            if "Text" not in current["interfaces"]:
                return {"error": "UNSUPPORTED", "message": "Element has no Text interface."}
            t = node.get_text_iface()
            n = Atspi.Text.get_character_count(t)
            limit = req.get("limit", 16000)
            return {"text": Atspi.Text.get_text(t, 0, min(n, limit)), "characters": n, "truncated": n > limit}
        if op == "set":
            if "EditableText" not in current["interfaces"] or "Text" not in current["interfaces"]:
                return {"error": "UNSUPPORTED", "message": "Exact replacement requires EditableText and Text."}
            if "editable" not in current["states"] or "enabled" not in current["states"]:
                return {"error": "NOT_EDITABLE", "message": "Element is not editable and enabled."}
            text = req["text"]
            accepted = node.get_editable_text_iface().set_text_contents(text)
            actual = Atspi.Text.get_text(node.get_text_iface(), 0, -1)
            return {"effect": "verified" if actual == text else "uncertain", "accepted": accepted,
                    "exact_match": actual == text, "expected_characters": len(text),
                    "actual_characters": len(actual)}
        if op == "focus":
            if "Component" not in current["interfaces"]:
                return {"error": "UNSUPPORTED", "message": "Element has no Component interface."}
            ok = node.get_component_iface().grab_focus()
            return {"effect": "dispatched" if ok else "uncertain", "accepted": ok}
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
