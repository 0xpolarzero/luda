# Date, numeric, validation and autocomplete qualification

The private GTK3 fixture exercises DATA-05, DATA-06, DATA-08 and DATA-09 through actual stdio MCP. It uses a real `de_DE.UTF-8` locale, `Gtk.Calendar`, `Gtk.SpinButton`, `Gtk.EntryCompletion`, and explicit application validation in `Europe/Berlin`. A separate widget/file oracle checks accepted values, selected suggestions, submission count and UTC timestamps. This is qualification of the listed GTK fixture workflows, not universal date-picker or autocomplete support.

Run as the ordinary desktop account:

```sh
.venv/bin/python tests/live_data_entry.py
```

The runner creates its own Xvfb, D-Bus session, private XDG directories and compiled locale. It requires `localedef` and the distro `locales` sources under `/usr/share/i18n`; an extracted source directory can instead be supplied as `LUDA_TEST_I18N_SOURCE`. It downloads nothing and modifies no installed locales. `artifacts/data-entry` must be writable by the test account. Results go to `artifacts/data-entry/results.json`.

Tested workflows:

- Calendar: select the visible March 29 cell using a fresh screenshot, then use Right and Space from that established focus to select March 30. The date field and independent calendar state agree. This GTK calendar exposes no accessible day children or day actions. Focusing it alone does not establish that keyboard navigation starts from its selected date; do not infer a relative date change without observing the result. Screenshot coordinates here are specific to the fixed fixture/theme.
- Numeric: inspect minimum, maximum and increment; verify 0 and 100 boundaries do not wrap; reject -1 and 101 without input. Setting the Value interface to `12.345` verifies that raw provider value while visible text is `12,35`. Explicit activation commits the formatted value as `12.35`. These are distinct states, not conflicting verification. Reading both accessible value and displayed text detects formatting and rounding.
- Numeric text: this native spin button rejects the overprecision text `12,345`; its replacement edit leaves the text empty. Luda returns `TEXT_MISMATCH` with uncertain effect, so the test observes state rather than treating it as a harmless rejection or automatically retrying. A separate explicit case focuses the field, enters valid `12,34`, then leaves focus and verifies numeric value `12.34`.
- Validation: impossible February dates, ISO text in a German-format field, the spring DST gap, and the autumn ambiguous hour are accepted as field text but rejected by the application on explicit Submit. Button invocation reports dispatched, never application success. `desktop_read_text` reads the visible validation error, while the oracle confirms no accepted submission. Valid dates before and after the DST transition commit the correct UTC timestamps.
- Autocomplete: entering literal `Ber`, dismissing suggestions and explicitly submitting preserves literal input without selecting a suggestion. To open this GTK completion reliably, enter `Be`, explicitly place the caret at its end, then send the final `r` as a GUI key. Observe the popup, navigate to the intended suggestion and press Return; read the field back and independently verify the `match-selected` callback. This fixture's completion rows are absent from the inspected owner tree, so it uses the observed popup order rather than claiming semantic row selection. Selecting a suggestion does not submit the form. Editing a selected suggestion back to literal text clears the selected identity and preserves the literal on explicit submit.

No runtime change or false-verification defect was needed. These results do not establish a universal date parser, automatic timezone inference, automatic rounding normalization, implicit submission, or automatic retries. Editable text verification proves text, Value verification proves the provider's numeric value, and successful suggestion selection and form submission require their own application-state checks.
