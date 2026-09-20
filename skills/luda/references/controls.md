# Semantic controls

Inspect first and use IDs for observed controls. Native semantic actions depend on the application's AT-SPI provider; visual similarity does not imply the same supported action. Most actions require the target window to be active. `desktop_focus_element(element_id=...)` requests focus within that window; inspect the result when focus matters.

## Buttons and menus

```python
desktop_inspect(window_id="<window_id>", name="Save")
desktop_invoke(element_id="<button_id>")
```

With one exposed action, omit `action`. With several, pass the exact intended action name returned by inspection; do not guess `click`, `press`, or toolkit-specific names. Invocation confirms dispatch, not the resulting application state. A menu opener and an item inside its popup are different controls; open, inspect, then choose.

If no semantic action exists, ground a click in a fresh screenshot. A semantic failure with uncertain effects must be inspected before a visual fallback.

## Desired state, not blind toggles

```python
desktop_set_checked(element_id="<checkbox_id>", checked=True)
desktop_set_expanded(element_id="<tree_item_id>", expanded=True)
desktop_set_value(element_id="<numeric_control_id>", value=5)
```

These operations aim for a requested state and avoid toggling a matching state away. State verification is an observation, not a guarantee against later application changes. Reinspect newly exposed children after expansion.

Numeric values use the provider's numeric Value interface. Inspect its minimum/maximum and displayed text: a verified numeric value can differ from locale-formatted or rounded presentation. Application commit may require a separate observed action. Invalid/nonfinite provider metadata is not a usable numeric range; `VALUE_UNVERIFIABLE` means the provider cannot establish the requested contract.

## Lists, radio groups, combos, and tables

```python
desktop_choose(element_id="<option_id>")
desktop_choose(element_id="<additional_item_id>", extend=True)
```

Choose the observed option, not the collapsed combo box. Open hidden/collapsed choices and inspect first. Default selection is exclusive; `extend=True` preserves other list/table selections where supported. Selecting a visible table cell selects its **whole row**, not its text or a spreadsheet range.

For an inclusive range:

```python
desktop_choose(element_id="<first_item_id>", range_end_id="<last_item_id>", extend=False)
```

Both endpoints must come from the same inspection. Every intervening item must be observed, visible, distinct, and in unchanged order; table endpoints must use the same column. Reversed endpoints are accepted. The limits are 50 range items and 500 selected items. `extend=False` replaces the selection; `extend=True` adds the range. Duplicate range labels, unloaded gaps, and unsupported providers are refused.

An interrupted or failed range can include historical `selection_step` progress. Inspect the current selection before further action; those receipts are not an instruction to replay remaining items. Sorting, filtering, and virtualization can recycle row indices or provider objects; reacquire the intended row using its current identity/context.

For editable grid cells, enter the intended cell's edit mode and inspect for the transient editor. Type into that editor, commit explicitly when requested, then read the committed cell. If accessibility omits the visible editor, a deliberate GUI paste and independent readback can be appropriate. Do not replace a whole table because the cell editor is unavailable.

## When semantics are incomplete

An empty or partial tree does not mean the interface lacks a control. Use screenshots for visual grounding, then check the application's result. Do not report semantic verification merely because a coordinate click succeeded. Conversely, a screen rectangle is unnecessary when a supported semantic action directly expresses the user's request.
