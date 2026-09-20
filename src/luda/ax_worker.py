"""Bounded subprocess: an unresponsive AT-SPI application cannot wedge MCP."""
import json
import hashlib
import sys
import time
import math
import re
from collections import deque

import gi
gi.require_version("Atspi", "2.0")
from gi.repository import Atspi

Atspi.set_timeout(600, 1000)


def identity(pid):
    from pathlib import Path
    return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]


def toolkit_name(node):
    app = node.get_application() if hasattr(node, "get_application") else None
    return (app.get_toolkit_name() or "") if app else ""


def native_text_mutation_supported(node, current):
    # Gecko advertises EditableText for text roles while its ATK callbacks
    # return without editing them. Keep the raw interfaces visible to agents.
    return not (toolkit_name(node).casefold() == "gecko" and
                current["role"] in ("entry", "text", "password text"))


def decode_gecko_text(text, count):
    """Undo exactly Mozilla DOMtoATK's one synthetic FEFF after each astral.

    A genuine FEFF after an astral appears after its synthetic FEFF and survives.
    Refuse changed/unknown conventions instead of guessing or stripping all BOMs.
    """
    result = []
    i = 0
    while i < len(text):
        char = text[i]
        result.append(char)
        i += 1
        if ord(char) > 0xFFFF:
            if i >= len(text) or text[i] != "\ufeff":
                raise ValueError("Unsupported Gecko ATK padding convention.")
            i += 1
    decoded = "".join(result)
    if count != len(text) or count != len(decoded.encode("utf-16-le")) // 2:
        raise ValueError("Gecko text count disagrees with its padding convention.")
    return decoded


class IdentityLimit(ValueError):
    """Native full-name identity exceeds the bounded fingerprint budget."""


def bounded_name_identity(node, protected):
    if protected:
        return "[protected]", None
    name = node.get_name() or ""
    # AT-SPI returns the complete native name. Reject before encoding/hashing
    # excessive values; neither the full value nor its digest is public output.
    if len(name) > 1_048_576:
        raise IdentityLimit("Accessible name exceeds the identity budget.")
    encoded = name.encode("utf-8")
    if len(encoded) > 1_048_576:
        raise IdentityLimit("Accessible name exceeds the identity budget.")
    return name[:300], hashlib.sha256(encoded).hexdigest()


def finite_provider_number(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('Invalid provider number')
    return value


def describe(node, pid):
    interfaces = node.get_interfaces()
    state = node.get_state_set()
    states = [s.value_nick for s in state.get_states()]
    protected = "password" in node.get_role_name().lower()
    name, fingerprint = bounded_name_identity(node, protected)
    r = {"pid": pid, "start": identity(pid), "path": node.path,
         "name": name, "name_fingerprint": fingerprint,
         "role": node.get_role_name(), "states": states, "interfaces": interfaces,
         "protected": protected}
    if "Component" in interfaces:
        rect = node.get_component_iface().get_extents(Atspi.CoordType.SCREEN)
        r["bounds"] = {"x": rect.x, "y": rect.y, "width": rect.width, "height": rect.height}
    if "Action" in interfaces:
        action = node.get_action_iface()
        r["actions"] = [action.get_action_name(i) for i in range(action.get_n_actions())]
    if "Value" in interfaces and not protected:
        try:
            value = node.get_value_iface()
            numbers = {"current": finite_provider_number(value.get_current_value()),
                       "minimum": finite_provider_number(value.get_minimum_value()),
                       "maximum": finite_provider_number(value.get_maximum_value()),
                       "increment": finite_provider_number(value.get_minimum_increment())}
            if numbers["minimum"] > numbers["maximum"]:
                raise ValueError('Invalid provider range')
            r["value"] = numbers
        except Exception:
            r["value_error"] = "VALUE_UNVERIFIABLE"
    if "EditableText" in interfaces:
        r["native_text_mutation_supported"] = native_text_mutation_supported(node, r)
    return r


class BusIdentityUnavailable(ValueError):
    """The worker cannot establish its actual accessibility connection epoch."""


def bus_generation():
    # GI does not expose atspi_get_a11y_bus. Read the authenticated server GUID
    # from that exact libatspi connection, not a separately discovered bus.
    import ctypes
    try:
        atspi = ctypes.CDLL("libatspi.so.0")
        dbus = ctypes.CDLL("libdbus-1.so.3")
        atspi.atspi_get_a11y_bus.argtypes = []
        atspi.atspi_get_a11y_bus.restype = ctypes.c_void_p
        dbus.dbus_connection_get_is_connected.argtypes = [ctypes.c_void_p]
        dbus.dbus_connection_get_is_connected.restype = ctypes.c_int
        dbus.dbus_connection_get_server_id.argtypes = [ctypes.c_void_p]
        dbus.dbus_connection_get_server_id.restype = ctypes.c_void_p
        dbus.dbus_free.argtypes = [ctypes.c_void_p]
        dbus.dbus_free.restype = None
        # libatspi 2.52 returns its cached connection without adding a ref.
        # Never close/unref it here; only the allocated GUID string is ours.
        connection = atspi.atspi_get_a11y_bus()
        if not connection or not dbus.dbus_connection_get_is_connected(connection):
            raise BusIdentityUnavailable()
        value = dbus.dbus_connection_get_server_id(connection)
        if not value:
            raise BusIdentityUnavailable()
        try:
            guid = ctypes.string_at(value).decode("ascii")
        finally:
            dbus.dbus_free(value)
        if not re.fullmatch(r"[0-9a-f]{32}", guid):
            raise BusIdentityUnavailable()
        return guid
    except Exception:
        raise BusIdentityUnavailable() from None


def provider_identity(node):
    # Object paths are local to one D-Bus connection, not to an OS process.
    name = node.app.bus_name
    if not isinstance(name, str) or len(name) > 255 or not re.fullmatch(r":[0-9]+(?:\.[0-9]+)+", name):
        raise ValueError("Accessible provider has no unique bus identity.")
    return name


def candidates(pid, limit=1600, depth=30, root_path=None, stats=None, root_provider=None):
    stats = stats if stats is not None else {}
    stats.setdefault("budget_pruned", False)
    stats.setdefault("depth_pruned", False)
    stats.setdefault("unreadable_branches", 0)
    desktop = Atspi.get_desktop(0)
    q = deque()
    for i in range(desktop.get_child_count()):
        app = desktop.get_child_at_index(i)
        if app and app.get_process_id() == pid and (not root_path or provider_identity(app) == root_provider):
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
        if root_path and provider_identity(node) != root_provider:
            stats["unreadable_branches"] += 1
            continue
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


class VerificationLimit(ValueError):
    """Exact text normalization cannot fit the documented worker budget."""


class SelectionUnavailable(ValueError):
    """Provider cannot expose exact, unambiguous selection offsets."""


class TextChanged(ValueError):
    """Provider length changed while taking a bounded text snapshot."""


class TextAccess:
    """Normalize providers that use UTF-16 offsets (Qt) to Unicode code points.

    Never infer offsets from application names. The reported count must agree
    with either the actual code-point count or UTF-16 count of bounded readback.
    """
    def __init__(self, raw):
        self.raw = raw
        self.toolkit = toolkit_name(raw)
        self.document = None
        self.selection_source = "Text"
        if self.toolkit.casefold() == "chromium" and hasattr(Atspi, "Document"):
            parent = raw.get_parent()
            for _ in range(30):
                if parent is None:
                    break
                if "Document" in parent.get_interfaces():
                    self.document = parent.get_document_iface()
                    break
                parent = parent.get_parent()
        self._refresh()

    def _refresh(self):
        count = Atspi.Text.get_character_count(self.raw)
        if not 0 <= count <= 2_000_000:
            raise VerificationLimit("Text provider exceeds the bounded offset-normalization budget.")
        text = Atspi.Text.get_text(self.raw, 0, count)
        if Atspi.Text.get_character_count(self.raw) != count:
            raise TextChanged("Text length changed during bounded readback.")
        if len(text) > 1_000_000:
            raise VerificationLimit("Text provider exceeds the one-million-code-point budget.")
        if self.toolkit.casefold() == "gecko":
            text = decode_gecko_text(text, count)
            self.utf16 = True
        elif self.toolkit.casefold() == "qt":
            if count != len(text.encode("utf-16-le")) // 2:
                raise ValueError("Qt provider count disagrees with UTF-16 offsets.")
            self.utf16 = True
        elif count == len(text):
            self.utf16 = False
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

    def representation(self):
        objects = []
        truncated = False
        if "\ufffc" in self.text and hasattr(self.raw, "get_interfaces") and "Hypertext" in self.raw.get_interfaces():
            hypertext = self.raw.get_hypertext_iface()
            count = Atspi.Hypertext.get_n_links(hypertext)
            truncated = count > 100
            for i in range(min(count, 100)):
                link = Atspi.Hypertext.get_link(hypertext, i)
                start = self.public_offset(link.get_start_index())
                end = self.public_offset(link.get_end_index())
                if "\ufffc" not in self.text[start:end]:
                    continue
                child = link.get_object(0)
                objects.append({"start_offset": start, "end_offset": end,
                                "role": child.get_role_name() if child else "unknown"})
        embedded = bool(objects) or truncated
        return {"text_representation": "hypertext" if embedded else "plain",
                "plain_text_verification_supported": not embedded,
                "embedded_objects": objects, "embedded_objects_truncated": truncated}

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

    def document_offset(self, endpoint, offset, is_end):
        """Lift exact embedded-object boundaries into this parent's hypertext.

        Interior positions in another object have no parent character equivalent
        and are deliberately rejected, rather than flattening rich text.
        """
        current = endpoint
        for _ in range(30):
            if current.path == self.raw.path:
                return self.public_offset(offset)
            if "password" in current.get_role_name().casefold():
                raise ValueError("Protected endpoint cannot be mapped.")
            parent = current.get_parent()
            if parent is None or "Hypertext" not in parent.get_interfaces() or "Text" not in current.get_interfaces():
                break
            count = Atspi.Text.get_character_count(current.get_text_iface())
            if offset not in (0, count):
                break
            hypertext = parent.get_hypertext_iface()
            links = Atspi.Hypertext.get_n_links(hypertext)
            if links > 100:
                break
            found = False
            for i in range(links):
                link = Atspi.Hypertext.get_link(hypertext, i)
                linked = link.get_object(0)
                if linked is not None and linked.path == current.path:
                    offset = link.get_end_index() if offset == count and (count > 0 or is_end) else link.get_start_index()
                    current = parent
                    found = True
                    break
            if not found:
                break
        raise ValueError("Document endpoint has no exact offset in this text object.")

    def get_selection(self, index):
        from types import SimpleNamespace
        if self.document is not None:
            ranges = Atspi.Document.get_text_selections(self.document)
            matching = []
            for selected in ranges:
                try:
                    start = self.document_offset(selected.start_object, selected.start_offset, False)
                    end = self.document_offset(selected.end_object, selected.end_offset, True)
                except (ValueError, AttributeError):
                    continue
                matching.append(SimpleNamespace(start_offset=start, end_offset=end))
            if index < len(matching):
                self.selection_source = "Document.GetTextSelections"
                return matching[index]
            # Older Chromium advertises Document but returns no ranges. Its
            # legacy Text selection double-converts UTF-16 offsets; it is exact
            # only when the complete field contains no non-BMP characters.
            if ranges or any(ord(c) > 0xFFFF for c in self.text):
                raise SelectionUnavailable("Document selection does not map to this exact text object.")
        if self.toolkit.casefold() == "chromium" and any(ord(c) > 0xFFFF for c in self.text):
            raise SelectionUnavailable("Chromium non-BMP selection requires the Document selection interface.")
        selection = Atspi.Text.get_selection(self.raw, index)
        return SimpleNamespace(start_offset=self.public_offset(selection.start_offset),
                               end_offset=self.public_offset(selection.end_offset))

    def add_selection(self, start, end):
        return Atspi.Text.add_selection(self.raw, self.provider_offset(start), self.provider_offset(end))

    def set_selection(self, index, start, end):
        return Atspi.Text.set_selection(self.raw, index, self.provider_offset(start), self.provider_offset(end))

    def remove_selection(self, index):
        return Atspi.Text.remove_selection(self.raw, index)


def text_representation_error(text_access, mutation_started=False):
    if text_access.representation()['plain_text_verification_supported']:
        return None
    return {'error': 'TEXT_REPRESENTATION_UNSUPPORTED',
            'message': ('Input may already have occurred; embedded objects prevent exact plain-text verification. Inspect before retrying.'
                        if mutation_started else
                        'Embedded objects prevent exact plain-text verification; no text input sent. Use deliberate paste with application-specific verification.'),
            'effect': 'uncertain' if mutation_started else 'none'}


def choice_identity(node, observed=None):
    """Bounded option identity, shared by each supported selection provider."""
    role = observed["role"] if observed is not None else node.get_role_name()
    name = ((observed["name"], observed.get("name_fingerprint")) if observed is not None
            else bounded_name_identity(node, "password" in role.lower()))
    return (provider_identity(node), node.path, role, *name)


def choose_table_row(node, current, extend, request=None):
    """Select a row through Table, preserving the exact observed cell identity."""
    cell = node.get_table_cell()
    table_node = Atspi.TableCell.get_table(cell)
    if table_node is None or "Table" not in table_node.get_interfaces():
        return failure("UNSUPPORTED", "Cell has no accessible Table container.")
    container_states = states_of(table_node)
    if "showing" not in container_states or not {"enabled", "sensitive"}.intersection(container_states):
        return failure("NOT_INTERACTABLE", "Table container must be sensitive and showing.")
    if request and request.get("target", {}).get("bounds_coordinates") == "unavailable":
        return failure("UNSUPPORTED", "Table viewport visibility requires reliable accessible coordinates.")
    if "Component" not in current["interfaces"] or "Component" not in table_node.get_interfaces():
        return failure("UNSUPPORTED", "Cannot establish the table cell's visible viewport.")
    bounds = node.get_component_iface().get_extents(Atspi.CoordType.SCREEN)
    viewport = table_node.get_component_iface().get_extents(Atspi.CoordType.SCREEN)
    # GTK may retain SHOWING on offscreen cells and return G_MININT coordinates.
    if (min(bounds.x, bounds.y, viewport.x, viewport.y) <= -2147483648 or
            min(bounds.width, bounds.height, viewport.width, viewport.height) <= 0 or
            max(bounds.x, viewport.x) >= min(bounds.x + bounds.width, viewport.x + viewport.width) or
            max(bounds.y, viewport.y) >= min(bounds.y + bounds.height, viewport.y + viewport.height)):
        return failure("NOT_INTERACTABLE", "Table cell is outside its visible viewport; scroll and inspect again.")
    table = table_node.get_table_iface()
    position = Atspi.TableCell.get_position(cell)
    row, column = position[-2:]
    observed = choice_identity(node, current)
    container = (provider_identity(table_node), table_node.path)
    def same_cell():
        position_now = Atspi.TableCell.get_position(cell)
        actual = table.get_accessible_at(row, column)
        return (tuple(position_now[-2:]) == (row, column) and actual is not None
                and (provider_identity(table_node), table_node.path) == container
                and choice_identity(actual) == observed and choice_identity(node) == observed)
    if row < 0 or column < 0 or not same_cell():
        return failure("STALE_TARGET", "Table cell position or meaning changed; inspect again.")
    selected = table.get_selected_rows()
    if len(selected) > 500:
        return failure("SELECTION_TOO_LARGE", "Table row selection normalization exceeds 500 rows.")
    # At most one existing cell per selected row, in the target column; never
    # scan the complete grid. Missing anchors cannot prove retained row meaning.
    anchors = {}
    for old_row in selected:
        if type(old_row) is not int or old_row < 0:
            return failure("SELECTION_UNVERIFIABLE", "Table exposes an invalid selected row.")
        anchor = table.get_accessible_at(old_row, column)
        if anchor is None:
            return failure("SELECTION_UNVERIFIABLE", "Selected row has no stable cell identity in this column.")
        anchors[old_row] = choice_identity(anchor)
    def same_anchor(old_row):
        actual = table.get_accessible_at(old_row, column)
        return actual is not None and choice_identity(actual) == anchors[old_row]
    if not same_cell() or not all(same_anchor(old_row) for old_row in anchors):
        return failure("STALE_TARGET", "Table changed while observing selection; inspect again.")
    expected = set(selected) | {row} if extend else {row}
    if set(selected) == expected:
        return {"effect": "verified", "accepted": True, "selected": True, "changed": False,
                "selection_scope": "table_row"}
    if request is not None:
        request["_mutation_started"] = True
    accepted = bool(table.add_row_selection(row))
    if accepted and not extend:
        for old_row in selected:
            if old_row == row or old_row not in table.get_selected_rows():
                continue
            if not same_cell() or not same_anchor(old_row):
                return {"effect": "uncertain", "accepted": accepted, "selected": False,
                        "verification": "Table changed while selecting; inspect again."}
            accepted = bool(table.remove_row_selection(old_row)) and accepted
    matched = verify(lambda: same_cell() and set(table.get_selected_rows()) == expected
                     and (not extend or all(same_anchor(old_row) for old_row in anchors)))
    return {"effect": "verified" if matched else "uncertain", "accepted": accepted,
            "selected": matched, "changed": matched, "selection_scope": "table_row", "extend": extend}


class RangeSelectionFailure(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message


def choose_range(node, current, req):
    """Inclusive inspected order; no synthesis of missing or virtual rows."""
    started = False
    receipt = req.setdefault('_range_receipt', {})
    def refuse(code, message):
        raise RangeSelectionFailure(code, message)
    try:
        target, end = req['target'], req.get('range_end')
        observations = req.get('range_nodes')
        if not isinstance(end, dict) or not isinstance(observations, list) or not 1 <= len(observations) <= 500:
            refuse('INVALID_ARGUMENT', 'A range requires two endpoints from one bounded inspection.')
        if any(end.get(k) != target.get(k) for k in ('start', 'root_path', 'root_provider', 'root_bus_guid')):
            refuse('STALE_TARGET', 'Range endpoints must belong to the same observed window and provider.')
        if target.get('bounds_coordinates') == 'unavailable':
            refuse('UNSUPPORTED', 'Range visibility requires reliable accessible coordinates.')
        table_mode = current['role'] == 'table cell' and 'TableCell' in current['interfaces']
        if not table_mode and current['role'] != 'list item':
            refuse('UNSUPPORTED', 'Ranges support visible table rows or Selection list items only.')
        if table_mode:
            container = Atspi.TableCell.get_table(node.get_table_cell())
            if container is None or 'Table' not in container.get_interfaces():
                refuse('UNSUPPORTED', 'Range has no accessible table.')
            provider = container.get_table_iface()
            _, column = Atspi.TableCell.get_position(node.get_table_cell())[-2:]
            def position(option):
                row, col = Atspi.TableCell.get_position(option.get_table_cell())[-2:]
                owner = Atspi.TableCell.get_table(option.get_table_cell())
                if (provider_identity(owner), owner.path) != container_key or col != column:return None
                return row
            def at(index):return provider.get_accessible_at(index, column)
            def selected():
                rows = provider.get_selected_rows()
                if len(rows)>500 or any(type(i) is not int or i<0 for i in rows) or len(set(rows))!=len(rows):
                    refuse('SELECTION_TOO_LARGE', 'Selected rows exceed the 500-item verification budget or are invalid.')
                return set(rows)
            def prepare(index, enabled):
                return lambda: provider.add_row_selection(index) if enabled else provider.remove_row_selection(index)
        else:
            container = node.get_parent()
            if container is None or 'Selection' not in container.get_interfaces():
                refuse('UNSUPPORTED', 'Range list must expose the Selection interface.')
            provider = container.get_selection_iface()
            def position(option):
                owner = option.get_parent()
                if owner is None or (provider_identity(owner),owner.path)!=container_key:return None
                return option.get_index_in_parent()
            def at(index):return container.get_child_at_index(index)
            def selected():
                count = Atspi.Selection.get_n_selected_children(provider)
                if not 0<=count<=500:refuse('SELECTION_TOO_LARGE','Selected items exceed the 500-item verification budget.')
                indices=[]
                for i in range(count):
                    option=Atspi.Selection.get_selected_child(provider,i);index=position(option)
                    if index is None or index<0 or choice_identity(at(index))!=choice_identity(option):
                        refuse('STALE_TARGET','Selected list item changed container or identity.')
                    indices.append(index)
                if len(set(indices))!=len(indices):refuse('SELECTION_UNVERIFIABLE','Selected list contains duplicate provider positions.')
                return set(indices)
            def prepare(index, enabled):
                if enabled:return lambda: Atspi.Selection.select_child(provider,index)
                # Replacement is one explicit clear followed by verified additions.
                # GTK ListBox individual deselection APIs do not reliably work.
                return lambda: Atspi.Selection.clear_selection(provider)
        container_key = (provider_identity(container), container.path)
        container_identity = choice_identity(container)
        # GTK may omit this hint even for MULTIPLE tables/lists. Each explicit
        # component action must verify the complete set; a single-select provider
        # stops at its first incompatible change, with an uncertain receipt.
        multiple_hint = 'multiselectable' in states_of(container)
        observed = [v for v in observations if v.get('role') == current['role'] and v.get('parent_path') == target.get('parent_path')]
        wanted={v['path'] for v in observed}
        if end.get('path') not in wanted or target['path'] not in wanted:
            refuse('UNSUPPORTED', 'Endpoints do not share one observed collection.')
        found={}
        for option,_ in candidates(req['pid'],root_path=target['root_path'],root_provider=target['root_provider']):
            if option.path in wanted:found[option.path]=option
            if len(found)==len(wanted):break
        anchors={};ordered=[];descriptions={}
        for old in observed:
            option=found.get(old['path'])
            if option is None:refuse('STALE_TARGET','An inspected range item is no longer available.')
            index=position(option)
            if index is None:
                if old['path'] in (target['path'],end['path']):refuse('UNSUPPORTED','Table range endpoints must use the same column.')
                continue
            identity=choice_identity(option,old)
            if index<0 or choice_identity(option)!=identity:
                refuse('STALE_TARGET','An inspected range item changed identity.')
            if index in anchors:refuse('STALE_TARGET','Range contains duplicate provider positions.')
            anchors[index]=identity;ordered.append(index);descriptions[index]={'name':old['name'],'role':old['role'],'position':index}
        first=position(found[target['path']]);last=position(found[end['path']])
        if first is None or last is None:refuse('UNSUPPORTED','Range endpoints have different containers.')
        if abs(first-last)+1>50:refuse('SELECTION_TOO_LARGE','A range supports at most 50 observed items.')
        expected_order=list(range(min(first,last),max(first,last)+1))
        if ordered!=expected_order:
            refuse('STALE_TARGET','Range order changed or intervening items were not inspected; inspect the complete range again.')
        labels=[(v['role'],v['name'],v.get('name_fingerprint')) for v in observed if v['path'] in found and position(found[v['path']]) in anchors]
        if len(set(labels))!=len(labels):
            refuse('UNSUPPORTED','Duplicate range labels cannot establish distinct visible item meaning.')
        ancestors=[];ancestor=container
        for _ in range(60):
            if ancestor is None:break
            ancestors.append(ancestor)
            if (provider_identity(ancestor),ancestor.path)==(target['root_provider'],target['root_path']):break
            ancestor=ancestor.get_parent()
        if not ancestors or (provider_identity(ancestors[-1]),ancestors[-1].path)!=(target['root_provider'],target['root_path']):
            refuse('STALE_TARGET','Selection container left the observed window.')
        root=ancestors[-1]
        previous=selected()
        retained={i:choice_identity(at(i)) for i in previous}
        expected=previous|set(anchors) if req.get('extend',False) else set(anchors)
        if len(expected)>500:refuse('SELECTION_TOO_LARGE','Resulting selection exceeds 500 items.')
        def guard():
            if choice_identity(container)!=container_identity or target['root_bus_guid']!=bus_generation():
                refuse('STALE_TARGET','Selection provider or container changed.')
            container_states=states_of(container)
            if 'showing' not in container_states or not {'enabled','sensitive'}.intersection(container_states):refuse('NOT_INTERACTABLE','Selection container is no longer enabled and showing.')
            for child,parent in zip(ancestors,ancestors[1:]):
                actual=child.get_parent()
                if actual is None or (provider_identity(actual),actual.path)!=(provider_identity(parent),parent.path):refuse('STALE_TARGET','Selection container changed window ancestry.')
            if 'active' not in states_of(root):refuse('FOCUS_CHANGED','Observed selection window is no longer active.')
            clip=None
            for parent in ancestors:
                if 'Component' not in parent.get_interfaces():continue
                rect=parent.get_component_iface().get_extents(Atspi.CoordType.SCREEN)
                bounds=(rect.x,rect.y,rect.x+rect.width,rect.y+rect.height)
                clip=bounds if clip is None else (max(clip[0],bounds[0]),max(clip[1],bounds[1]),min(clip[2],bounds[2]),min(clip[3],bounds[3]))
            if clip is None:refuse('UNSUPPORTED','Range viewport cannot be observed.')
            for index,identity in anchors.items():
                option=at(index)
                if option is None or position(option)!=index or choice_identity(option)!=identity:
                    refuse('STALE_TARGET','Range item order or identity changed.')
                states=states_of(option)
                if 'showing' not in states or not {'enabled','sensitive'}.intersection(states) or 'defunct' in states:
                    refuse('NOT_INTERACTABLE','Every range item must remain enabled and showing.')
                if 'Component' not in option.get_interfaces():refuse('UNSUPPORTED','Range item has no visible bounds.')
                rect=option.get_component_iface().get_extents(Atspi.CoordType.SCREEN)
                if min(rect.x,rect.y)<=-2147483648 or min(rect.width,rect.height)<=0 or max(rect.x,clip[0])>=min(rect.x+rect.width,clip[2]) or max(rect.y,clip[1])>=min(rect.y+rect.height,clip[3]):
                    refuse('NOT_INTERACTABLE','Every range item must be in the visible viewport; scroll and inspect again.')
            for index,identity in retained.items():
                if choice_identity(at(index))!=identity:refuse('STALE_TARGET','Previously selected item changed meaning or order.')
        guard()
        clear_list=not table_mode and bool(previous-expected)
        plan=([(None,False)]+[(i,True) for i in sorted(expected)] if clear_list else
              [(i,False) for i in sorted(previous-expected)]+[(i,True) for i in sorted(expected-previous)])
        progress={'unit':'selection_step','requested':len(plan),'verified_completed':0,'current_uncertain':0,'not_started':len(plan),'application_commit_verified':False}
        receipt['progress']=progress
        expected_now=set(previous);deadline=time.monotonic()+2.5
        for index,enabled in plan:
            guard()
            if selected()!=expected_now:refuse('SELECTION_UNVERIFIABLE','Selection changed before the next range action.')
            guard()  # Selected-set readback may itself yield to app reorder/focus events.
            action=prepare(index,enabled)
            if time.monotonic()>=deadline:refuse('TIMEOUT','Range selection verification deadline reached; inspect before continuing.')
            req['_mutation_started']=True;started=True
            progress['current_uncertain']=1;progress['not_started']-=1
            accepted=bool(action())
            after=expected_now|{index} if enabled else (set() if index is None else expected_now-{index})
            def matched():
                guard()
                matches=selected()==after
                guard()
                return matches
            if not accepted or not verify(matched):refuse('SELECTION_UNVERIFIABLE','Range action did not verify the exact selected set; inspect before continuing.')
            expected_now=after;progress['verified_completed']+=1;progress['current_uncertain']=0
        guard()
        if selected()!=expected:refuse('SELECTION_UNVERIFIABLE','Final selection changed during readback.')
        items=[]
        for index in sorted(expected):
            option=at(index);role=option.get_role_name();name,_=bounded_name_identity(option,'password' in role.lower())
            items.append({'name':name,'role':role,'position':index})
        guard()
        if selected()!=expected:refuse('SELECTION_UNVERIFIABLE','Selection changed while describing selected items.')
        guard()
        return {'effect':'verified','accepted':True,'selected':True,'changed':bool(plan),'extend':req.get('extend',False),
                'selection_scope':'table_row_range' if table_mode else 'list_item_range','selected_items':items,
                'multiple_selection_advertised':multiple_hint,
                'verification':'Exact observed provider item identities and selected set; not atomic against later application changes.'}
    except RangeSelectionFailure as exc:
        return {'error':exc.code,'message':exc.message,'effect':'uncertain' if started else 'none'}
    except Exception:
        return {'error':'ACCESSIBILITY_ERROR','message':'Range provider failed; inspect before continuing.','effect':'uncertain' if started else 'none'}


def choose_combo_option(node, combo, current, request=None):
    """Commit a popup option, not merely highlight a menu row."""
    combo_states = states_of(combo)
    if "showing" not in combo_states or not {"enabled", "sensitive"}.intersection(combo_states):
        return failure("NOT_INTERACTABLE", "Combo must be sensitive and showing.")
    if "Selection" not in combo.get_interfaces() or "Action" not in node.get_interfaces():
        return failure("UNSUPPORTED_ACTION", "Combo option commitment cannot be verified semantically; use the visible popup workflow.")
    action = node.get_action_iface()
    recognized = [i for i in range(action.get_n_actions())
                  if action.get_action_name(i).casefold() in ("click", "press", "activate")]
    if len(recognized) != 1:
        return failure("UNSUPPORTED_ACTION", "Combo option has no unambiguous activation action.")
    selection = combo.get_selection_iface()
    observed = choice_identity(node, current)
    container = (provider_identity(combo), combo.path)
    if choice_identity(node) != observed:
        return failure("STALE_TARGET", "Combo option meaning changed; inspect again.")
    if request is not None:
        request["_mutation_started"] = True
    accepted = bool(action.do_action(recognized[0]))
    def committed():
        if Atspi.Selection.get_n_selected_children(selection) != 1:
            return False
        actual = Atspi.Selection.get_selected_child(selection, 0)
        return (actual is not None and (provider_identity(combo), combo.path) == container
                and choice_identity(actual) == observed)
    matched = verify(committed)
    return {"effect": "verified" if matched else "uncertain", "accepted": accepted,
            "selected": matched, "selection_method": "combo_option_activation"}


def choose_by_action(node, parent, current, extend, request=None):
    """Qt list items expose Toggle/selected instead of a Selection container."""
    if current["role"] != "list item" or "selectable" not in current["states"] or parent.get_role_name() not in ("list", "list box"):
        return failure("UNSUPPORTED", "Option parent has no supported selection interface.")
    count = parent.get_child_count()
    if count > 500:
        return failure("SELECTION_TOO_LARGE", "Action-based selection is limited to 500 direct options.")
    container = (provider_identity(parent), parent.path)
    siblings = [parent.get_child_at_index(i) for i in range(count)]
    identities = [choice_identity(other) for other in siblings]
    observed = choice_identity(node, current)
    index = node.get_index_in_parent()
    if not 0 <= index < count or identities[index] != observed:
        return failure("STALE_TARGET", "Option meaning changed before selection; inspect again.")
    def live_siblings():
        if (provider_identity(parent), parent.path) != container or parent.get_child_count() != count:
            return None
        actual = [parent.get_child_at_index(i) for i in range(count)]
        return actual if [choice_identity(other) for other in actual] == identities else None
    previous = {identities[i] for i, other in enumerate(siblings) if "selected" in states_of(other)}
    expected = previous | {observed} if extend else {observed}
    changes = ([node] if observed not in previous else [])
    if not extend:
        changes += [other for i, other in enumerate(siblings) if identities[i] != observed and identities[i] in previous]
    plan = []
    for other in changes:
        if "Action" not in other.get_interfaces():
            return failure("UNSUPPORTED_ACTION", "Every changed option must advertise a Toggle action.")
        action = other.get_action_iface()
        indices = [i for i in range(action.get_n_actions()) if action.get_action_name(i).casefold() == "toggle"]
        if len(indices) != 1:
            return failure("UNSUPPORTED_ACTION", "Every changed option must advertise one unambiguous Toggle action.")
        plan.append((other, action, indices[0]))
    def same_position(option):
        position = option.get_index_in_parent()
        if not 0 <= position < count:
            return False
        actual = parent.get_child_at_index(position)
        return (actual is not None and choice_identity(actual) == identities[position]
                and choice_identity(option) == identities[position])
    accepted = True
    for other, action, action_index in plan:
        # Check the target and next changed option per action; rereading all
        # children for every toggle would make a 500-option plan quadratic.
        if ((provider_identity(parent), parent.path) != container
                or parent.get_child_count() != count
                or not same_position(node) or not same_position(other)):
            return {"effect": "uncertain", "accepted": accepted, "selected": False,
                    "verification": "Option identity changed while selecting; inspect again."}
        if request is not None:
            request["_mutation_started"] = True
        accepted = bool(action.do_action(action_index)) and accepted
    def matched_selection():
        actual = live_siblings()
        return actual is not None and {identities[i] for i, other in enumerate(actual)
                                       if "selected" in states_of(other)} == expected
    matched = verify(matched_selection)
    return {"effect": "verified" if matched else "uncertain", "accepted": accepted,
            "selected": matched, "changed": bool(plan) and matched, "extend": extend,
            "selection_method": "advertised_toggle_actions"}


def semantic(node, current, req):
    """Return None for legacy operations. Never emulate unsupported semantics by typing."""
    op = req["op"]
    if op in ("set", "insert") and not native_text_mutation_supported(node, current):
        return failure("UNSUPPORTED", "Gecko text controls do not implement native EditableText mutations; use verified ordinary typing where permitted.")
    if op == "secret":
        if not current["protected"]:
            return failure("NOT_PROTECTED_FIELD", "Explicit protected input requires an observed protected field.")
        if not native_text_mutation_supported(node, current):
            return failure("UNSUPPORTED", "Gecko protected controls do not implement native EditableText mutations.")
        if "EditableText" not in current["interfaces"] or "editable" not in current["states"]:
            return failure("UNSUPPORTED", "Protected input requires an editable EditableText interface.")
        text = req.get("text")
        if not isinstance(text, str) or len(text) > 1_000_000 or any(c in text for c in ('\0', '\r')) or any(0xD800 <= ord(c) <= 0xDFFF for c in text):
            return failure("UNSUPPORTED_TEXT", "Protected input must be valid Unicode without NUL or CR, within the text budget.")
        try:
            accepted = bool(node.get_editable_text_iface().set_text_contents(text))
        except Exception:
            # A provider may echo its argument in an exception. Never expose it.
            return {"error": "ACCESSIBILITY_ERROR", "message": "Protected input provider failed; outcome is uncertain.", "effect": "uncertain"}
        return {"effect": "dispatched" if accepted else "uncertain", "accepted": accepted,
                "verification": "Protected contents are never read back; acceptance does not verify the value."}
    if op == "choose":
        if current["protected"]:
            return failure("PROTECTED_FIELD", "Protected fields are not selectable options.")
        extend = req.get("extend", False)
        if type(extend) is not bool:
            return failure("INVALID_ARGUMENT", "extend must be a boolean.")
        if req.get("range_end") is not None:
            return choose_range(node, current, req)
        if current["role"] == "radio button":
            if extend:
                return failure("INVALID_ARGUMENT", "Radio choices cannot extend a selection.")
            return semantic(node, current, {"op": "check", "checked": True})
        if current["role"] == "table cell" and "TableCell" in current["interfaces"]:
            return choose_table_row(node, current, extend, request=req)
        parent = node.get_parent()
        if parent is None:
            return failure("UNSUPPORTED", "Option has no accessible parent.")
        parent_states = states_of(parent)
        if "showing" not in parent_states or not {"enabled", "sensitive"}.intersection(parent_states):
            return failure("NOT_INTERACTABLE", "Selection container must be sensitive and showing.")
        ancestor = parent
        for _ in range(8):
            if ancestor.get_role_name() == "combo box":
                if extend:
                    return failure("INVALID_ARGUMENT", "Combo options cannot extend a selection.")
                return choose_combo_option(node, ancestor, current, request=req)
            if ancestor.get_role_name() in ("frame", "window", "dialog", "application"):
                break
            ancestor = ancestor.get_parent()
            if ancestor is None:
                break
        if current["role"] == "menu item":
            return failure("UNSUPPORTED", "Menu commands require their explicit activation action, not option selection.")
        index = node.get_index_in_parent()
        if index < 0 or parent.get_child_at_index(index).path != node.path:
            return failure("STALE_TARGET", "Option position changed; inspect again.")
        if "Selection" not in parent.get_interfaces():
            return choose_by_action(node, parent, current, extend, request=req)
        selection = parent.get_selection_iface()
        parent_identity = (provider_identity(parent), parent.path)
        expected_identity = choice_identity(node, current)
        option_identity = choice_identity
        def same_option():
            actual = parent.get_child_at_index(index)
            return (actual is not None and node.get_index_in_parent() == index
                    and (provider_identity(parent), parent.path) == parent_identity
                    and option_identity(actual) == expected_identity
                    and option_identity(node) == expected_identity)
        def selected_identities():
            count = Atspi.Selection.get_n_selected_children(selection)
            if count > 500:
                return None
            return {option_identity(Atspi.Selection.get_selected_child(selection, i))
                    for i in range(count)}
        previous = selected_identities()
        if previous is None:
            return failure("SELECTION_TOO_LARGE", "Selection normalization exceeds the 500-option budget.")
        expected = previous | {expected_identity} if extend else {expected_identity}
        def chosen():
            return (same_option() and Atspi.Selection.is_child_selected(selection, index)
                    and selected_identities() == expected and same_option())
        if chosen():
            return {"effect": "verified", "accepted": True, "selected": True, "changed": False}
        if not same_option():
            return failure("STALE_TARGET", "Option identity changed before selection; inspect again.")
        # Some GTK containers omit multiselectable even when multiple selections
        # are enabled. Select first, then remove only previously observed options.
        req["_mutation_started"] = True
        accepted = (True if Atspi.Selection.is_child_selected(selection, index)
                    else bool(Atspi.Selection.select_child(selection, index)))
        if not extend and accepted:
            count = Atspi.Selection.get_n_selected_children(selection)
            if count > 500:
                return {"effect": "uncertain", "accepted": accepted, "selected": False,
                        "verification": "Selection grew beyond the normalization budget."}
            others = [Atspi.Selection.get_selected_child(selection, i) for i in range(count)]
            for selected_index in range(len(others) - 1, -1, -1):
                if not same_option():
                    return {"effect": "uncertain", "accepted": accepted, "selected": False,
                            "verification": "Option identity changed while selecting; inspect again."}
                other = others[selected_index]
                other_identity = option_identity(other)
                if other_identity == expected_identity:
                    continue
                other_index = other.get_index_in_parent()
                if (other_identity not in previous or other_index < 0
                        or option_identity(parent.get_child_at_index(other_index)) != other_identity):
                    return {"effect": "uncertain", "accepted": accepted, "selected": False,
                            "verification": "Selected options changed while normalizing selection."}
                if option_identity(Atspi.Selection.get_selected_child(selection, selected_index)) != other_identity:
                    return {"effect": "uncertain", "accepted": accepted, "selected": False,
                            "verification": "Selected option order changed; inspect again."}
                accepted = bool(Atspi.Selection.deselect_selected_child(selection, selected_index)) and accepted
        matched = verify(chosen)
        return {"effect": "verified" if matched else "uncertain", "accepted": accepted,
                "selected": matched, "changed": matched, "extend": extend}
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
            req["_mutation_started"] = True
            if t.toolkit.casefold() == "gecko" and start != end:
                # Gecko's AddSelection can expose the correct DOM range while
                # leaving the editor insertion caret at its old location. A
                # verified collapsed caret first synchronizes that editor state.
                accepted = t.set_caret_offset(start)
                if not accepted or not verify(lambda: t.get_caret_offset() == start and t.get_n_selections() == 0):
                    return {"error": "SELECTION_UNVERIFIED", "message": "Gecko insertion caret could not be synchronized before selection.", "effect": "uncertain"}
                count = 0
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
        representation_error = text_representation_error(t)
        if representation_error:
            return representation_error
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
        representation_error = text_representation_error(t)
        if representation_error:
            return representation_error
        accepted = True
        req["_mutation_started"] = True
        if end > start:
            accepted = bool(edit.delete_text(t.provider_offset(start), t.provider_offset(end)))
            if not accepted or not verify(lambda: t.get_text(0, -1) == before[:start] + before[end:]):
                return {"effect": "uncertain", "accepted": accepted, "exact_match": False,
                        "verification": "Selection deletion was rejected; inspect before retrying."}
        # Deletion is itself a provider mutation. Do not send the insertion
        # if the remaining field has become an opaque representation.
        representation_error = text_representation_error(t, mutation_started=True)
        if representation_error:
            return representation_error
        # GTK consumes UTF-8 length; Qt bridge consumes UTF-16 units. Normalize
        # this separately from public code-point positions to avoid NUL padding.
        if text:
            accepted = bool(edit.insert_text(t.provider_offset(start), text, t.insertion_length(text)))
        observed_text = None
        def text_matches():
            nonlocal observed_text
            observed_text = t.get_text(0, -1)
            return observed_text == expected
        matched = verify(text_matches)
        representation_error = text_representation_error(t, mutation_started=True)
        if representation_error:
            return representation_error
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
                "actual_characters": len(observed_text),
                "replaced_characters": end-start, "inserted_characters": len(text),
                "caret_verified": caret_verified, "caret_offset": wanted_caret if caret_verified else t.get_caret_offset(),
                "verification": "Text and character count describe the same observed readback; caret verification is a separate observation. Later application changes are not excluded."}
    if op == "value":
        value = req.get("value")
        if type(value) not in (int, float) or not math.isfinite(value):
            return failure("INVALID_ARGUMENT", "Value must be a finite number.")
        if "Value" not in current["interfaces"]:
            return failure("UNSUPPORTED", "Element has no Value interface.")
        v = node.get_value_iface()
        try:
            minimum = finite_provider_number(v.get_minimum_value())
            maximum = finite_provider_number(v.get_maximum_value())
            if minimum > maximum:
                raise ValueError('Invalid provider range')
        except Exception:
            return {"error": "VALUE_UNVERIFIABLE", "message": "Provider numeric range is unavailable or invalid; no value change sent.", "effect": "none"}
        if not minimum <= value <= maximum:
            return failure("OUT_OF_BOUNDS", "Value is outside the reported range.")
        accepted = bool(v.set_current_value(value))
        observed_value = None
        def value_matches():
            nonlocal observed_value
            observed_value = finite_provider_number(v.get_current_value())
            return observed_value == value
        try:
            matched = verify(value_matches)
        except Exception:
            return {"error": "VALUE_UNVERIFIABLE", "message": "Provider numeric readback is unavailable or invalid after input; inspect before retrying.", "effect": "uncertain"}
        return {"effect": "verified" if matched else "uncertain", "accepted": accepted,
                "exact_match": matched, "actual_value": observed_value}
    if op in ("check", "expand"):
        key, state = ("checked", "checked") if op == "check" else ("expanded", "expanded")
        desired = req.get(key)
        if type(desired) is not bool:
            return failure("INVALID_ARGUMENT", f"{key} must be a boolean.")
        if op == "check" and not ({"checkable", "checked", "indeterminate"} & set(current["states"])) and current["role"] not in ("check box", "radio button", "toggle button", "check menu item"):
            return failure("UNSUPPORTED", "Element is not a checkable control.")
        if op == "expand" and "expandable" not in current["states"]:
            return failure("UNSUPPORTED", "Element is not expandable.")
        observed_states = set()
        def matches():
            nonlocal observed_states
            observed_states = states_of(node)
            return (state in observed_states) == desired and "indeterminate" not in observed_states
        if matches():
            return {"effect": "verified", "accepted": True, "changed": False, key: desired}
        actions = current.get("actions", [])
        eligible = (("check" if desired else "uncheck"), "toggle", "click", "activate") if op == "check" else ("expand or contract", "expand or collapse", "toggle", "activate")
        action = next((actual for a in eligible for actual in actions if actual.casefold() == a), None)
        if action is None:
            return failure("UNSUPPORTED_ACTION", "No recognized semantic state-changing action is available.")
        accepted = bool(node.get_action_iface().do_action(actions.index(action)))
        matched = verify(matches)
        return {"effect": "verified" if matched else "uncertain", "accepted": accepted,
                "changed": matched, key: state in observed_states}
    return None


def main(req):
    pid = req["pid"]
    if req.get("op") not in {"inspect", "read", "set", "focus", "invoke", "insert", "select", "value", "check", "expand", "secret", "choose"}:
        return failure("UNSUPPORTED_OPERATION", "Unknown accessibility operation.")
    if req.get("start") and identity(pid) != req["start"]:
        return {"error": "STALE_TARGET", "message": "Process identity changed."}
    if req["op"] == "inspect":
        # Match the accessible top-level to the X11 CLIENT rectangle. Never expose
        # sibling windows as if they belonged to the selected target.
        if type(req.get("limit", 150)) is not int or not 1 <= req.get("limit", 150) <= 500:
            return failure("INVALID_ARGUMENT", "Inspection limit must be an integer from 1 to 500.")
        generation = bus_generation()
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
                roots.append((provider_identity(candidate), candidate.path))
            if (req.get("window_title") and candidate.get_name() == req["window_title"]
                    and rect.width == bounds["width"] and rect.height == bounds["height"]):
                title_size_matches.append((provider_identity(candidate), candidate.path))
                if rect.x == 0 and rect.y == 0:
                    fallback_roots.append((provider_identity(candidate), candidate.path))
        if scope_stats.get("budget_pruned") or scope_stats.get("unreadable_branches"):
            return failure("AMBIGUOUS_ACCESSIBILITY_WINDOW", "Cannot prove uniqueness within the top-level traversal budget.")
        mapping = "screen_bounds"
        if not roots and len(fallback_roots) == 1 and len(title_size_matches) == 1:
            roots = fallback_roots
            mapping = "unique_title_and_size"
        if not roots and len(title_size_matches) <= 1:
            return failure("ACCESSIBILITY_UNAVAILABLE", "No accessible window matches this X11 target. The application may not be registered with the accessibility bus or expose usable window geometry; use screenshot controls.")
        if len(roots) != 1:
            return {"error":"AMBIGUOUS_ACCESSIBILITY_WINDOW", "message":"Multiple accessible windows may match this X11 target; use screenshot controls."}
        root_provider, root_path = roots[0]
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
        for node, depth in candidates(pid,root_path=root_path, root_provider=root_provider, depth=max_depth, stats=traversal):
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
                value["root_provider"] = root_provider
                value["root_bus_guid"] = generation
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
        return {"nodes": nodes, "truncated": truncated or bool(errors) or any(traversal.values()), "truncation": {"result_or_time_limit": truncated, **traversal}, "visited_nodes": visited, "max_depth": max_depth, "unreadable_nodes": errors, "unreadable_branches": traversal.get("unreadable_branches", 0),
                "coverage": "selected accessible top-level window", "available": visited > 0,
                "window_mapping": mapping, "bounds_coordinates": "unavailable" if mapping == "unique_title_and_size" else "screen"}
    target = req["target"]
    if target.get("root_bus_guid") != bus_generation():
        return {"error": "STALE_TARGET", "message": "Accessibility bus changed; inspect again.", "effect": "none"}
    for node, _ in candidates(pid,root_path=target["root_path"],root_provider=target.get("root_provider")):
        if node.path != target["path"]:
            continue
        current = describe(node, pid)
        if (any(current[k] != target[k] for k in ("role", "name", "start"))
                or current.get("name_fingerprint") != target.get("name_fingerprint")
                or "defunct" in current["states"]):
            return {"error": "STALE_TARGET", "message": "Element identity changed; inspect again."}
        op = req["op"]
        if op != "read" and ("showing" not in current["states"] or not {"enabled", "sensitive"}.intersection(current["states"])):
            return {"error": "NOT_INTERACTABLE", "message": "Element must be enabled and showing for mutation; inspect the visible target."}
        if op in ("read", "set", "insert", "select", "value") and current["protected"]:
            return {"error": "PROTECTED_FIELD", "message": "This implementation does not read or write protected fields."}
        if target["root_bus_guid"] != bus_generation():
            return {"error": "STALE_TARGET", "message": "Accessibility bus changed before operation; inspect again.", "effect": "none"}
        result = semantic(node, current, req)
        if result is not None:
            return result
        if op == "read":
            if "Text" not in current["interfaces"]:
                return {"error": "UNSUPPORTED", "message": "Element has no Text interface."}
            t = TextAccess(node.get_text_iface())
            n = len(t.text)
            limit = req.get("limit", 16000)
            if type(limit) is not int or not 1 <= limit <= 1_000_000:
                return failure("INVALID_ARGUMENT", "Text read limit must be 1..1000000.")
            # All text/count/truncation fields describe the same bounded read.
            # Refreshing with an old end offset can hide a concurrently added suffix.
            content = t.text[:limit]
            selections = [{"start_offset": sel.start_offset, "end_offset": sel.end_offset}
                          for sel in (t.get_selection(i) for i in range(min(t.get_n_selections(), 100)))]
            representation = t.representation()
            return {"text": content, "characters": n, "truncated": n > limit,
                    "caret_offset": t.get_caret_offset(), "offset_units": "Unicode code points",
                    "provider_offset_units": "UTF-16 code units" if t.utf16 else "Unicode code points",
                    "provider_text_encoding": "Gecko ATK astral padding" if t.toolkit.casefold() == "gecko" else "plain",
                    "selections": selections, "selection_source": t.selection_source,
                    "selections_truncated": t.get_n_selections() > 100,
                    **representation}
        if op == "set":
            if "EditableText" not in current["interfaces"] or "Text" not in current["interfaces"]:
                return {"error": "UNSUPPORTED", "message": "Exact replacement requires EditableText and Text."}
            if "editable" not in current["states"] or not {"enabled", "sensitive"}.intersection(current["states"]):
                return {"error": "NOT_EDITABLE", "message": "Element is not editable and enabled."}
            text = req["text"]
            if not isinstance(text, str) or len(text) > 1_000_000 or any(c in text for c in ('\0', '\r')) or any(0xD800 <= ord(c) <= 0xDFFF for c in text):
                return failure("UNSUPPORTED_TEXT", "Text must be valid Unicode without NUL or CR and at most one million characters.")
            # Qualify complete existing text before mutation; bounded independent
            # readback also refuses a provider that grows unexpectedly afterward.
            t = TextAccess(node.get_text_iface())
            representation_error = text_representation_error(t)
            if representation_error:
                return representation_error
            req["_mutation_started"] = True
            accepted = node.get_editable_text_iface().set_text_contents(text)
            actual = t.get_text(0, -1)
            representation_error = text_representation_error(t, mutation_started=True)
            if representation_error:
                return representation_error
            return {"effect": "verified" if actual == text else "uncertain", "accepted": accepted,
                    "exact_match": actual == text, "expected_characters": len(text),
                    "actual_characters": len(actual)}
        if op == "focus":
            if "Component" not in current["interfaces"]:
                return {"error": "UNSUPPORTED", "message": "Element has no Component interface."}
            try:
                ok = node.get_component_iface().grab_focus()
            except Exception:
                if "focused" in states_of(node):
                    return {"effect": "verified", "accepted": False, "focused": True,
                            "changed": False, "focus_request_supported": False}
                raise
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


def _dispatch(request):
    # Provider exception strings can contain application contents or input.
    # Expose fixed diagnostics, never the native exception's message.
    request = dict(request)
    request.pop("_mutation_started", None)
    try:
        return main(request)
    except BusIdentityUnavailable:
        return {"error": "ACCESSIBILITY_UNAVAILABLE", "message": "Cannot establish accessibility bus identity; inspect again before input.", "effect": "none"}
    except IdentityLimit:
        return {"error": "TARGET_IDENTITY_UNAVAILABLE",
                "message": "Accessible name exceeds the one-MiB identity budget; exact target identity cannot be established.",
                "effect": "uncertain" if request.get("_mutation_started") else "none"}
    except TextChanged:
        return {"error": "TEXT_CHANGED",
                "message": "Text changed during bounded readback; inspect again before input.",
                "effect": "uncertain" if request.get("_mutation_started") else "none"}
    except SelectionUnavailable:
        return {"error": "SELECTION_UNVERIFIABLE",
                "message": "The accessibility provider cannot expose exact selection offsets. Use deliberate screenshot/clipboard controls and independently verify the application result before retrying.",
                "effect": "uncertain" if request.get("_mutation_started") else "none"}
    except VerificationLimit:
        return {"error": "VERIFICATION_LIMIT",
                "message": "Exact text verification exceeds the one-million-code-point or two-million-provider-unit budget.",
                "effect": "uncertain" if request.get("_mutation_started") else "none"}
    except Exception:
        return {"error": "ACCESSIBILITY_ERROR",
                "message": "The accessibility provider failed. Inspect again before retrying an action.",
                "effect": "none" if request.get("op") in ("read", "inspect") else "uncertain"}


def dispatch(request):
    request=dict(request)
    request['_range_receipt']=receipt={}
    result=_dispatch(request)
    if 'progress' in receipt:result['progress']=receipt['progress']
    return result


if __name__ == "__main__":
    try:
        request = json.load(sys.stdin)
    except Exception:
        print(json.dumps(failure("INVALID_ARGUMENT", "Worker request must be valid JSON.")))
    else:
        print(json.dumps(dispatch(request), ensure_ascii=False))
