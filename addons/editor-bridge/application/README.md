# Add the application bridge

This module is for **the developer of a ProseMirror application**, not an agent visiting an arbitrary website. It is an optional part of Luda Editor Bridge and is not shipped with core Luda.

Copy `luda-prosemirror.mjs` into your application and register an existing `EditorView` after creating it:

```js
import { registerProseMirror } from './luda-prosemirror.mjs';
const unregister = registerProseMirror(view, { paragraphs: 'enter' });
// Before view.destroy() or replacement:
unregister();
```

Register each new view once; unregister retired views. Registration changes invalidate old agent handles, even if the DOM root is reused. Do not expose sensitive documents merely to test setup: the bridge makes supported document state available to the agent operating this browser.

The bridge reads model/selection/marks and maps code-point ranges through public `EditorView` DOM APIs. It never writes text, dispatches a model transaction, changes your schema, or installs key bindings. Agent edits use browser-native input and are verified afterward.

## Required application behavior

The normal declaration means your actual Enter binding creates paragraphs. Supported content is `doc → paragraph → text` with attribute-free `strong` and `em` marks. Other document nodes, marks or custom attributes are refused; a schema may define other types, but they must not occur in the edited document.

If your application also binds Shift+Enter to an attribute-free `hard_break`, declare it explicitly:

```js
const unregister = registerProseMirror(view, {
  paragraphs: 'enter',
  hard_breaks: 'shift-enter'
});
```

This narrowly extends supported content; it does not install that behavior. A wrong declaration can modify content before the add-on detects a mismatch. Both paragraph and hard-break boundaries serialize as logical LF, but the returned model and boundary metadata distinguish them.

## Check the connection

Separately install the agent add-on and open your application with `editor_open`. Call `editor_inspect` without filters. Your registered editors should appear under `text_fields`; inspect `supported`, `unsupported_reason`, `supported_line_breaks` and `selection_scope`. No entries means registration has not reached the current page, the view is gone, or the app is outside the supported single-page/light-DOM scope.

The add-on uses a fresh temporary Chromium profile and does not attach existing browsers. Composition must be observed inactive. Focus/document checks can race other actors; verification is an observed result, not an atomic edit or a save guarantee.

For budgets, supported edits and failure behavior, see the [agent reference](../skills/luda-editor-bridge/references/editing.md). For optional agent installation, see the [add-on README](../README.md).
