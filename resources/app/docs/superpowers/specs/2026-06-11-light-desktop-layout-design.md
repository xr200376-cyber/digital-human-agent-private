# Light Desktop Layout Design

## Goal

Rework the Aivo studio UI so it keeps the existing light/teal theme but uses the simpler desktop-product layout from the provided AivoClaw reference: narrow left navigation, compact top header, and task-focused two-column work areas.

## Scope

- Keep the current visual theme: light background, white panels, teal primary actions, existing font stack.
- Change the app shell layout to a full-height desktop workspace instead of a centered page.
- Make the left navigation narrower and more app-like while retaining Chinese labels.
- Rebalance the two main production screens:
  - `数字人制作`: left side shows the creation workflow, right side shows personal asset preview and output/progress.
  - `视频混剪`: left side shows main video, material upload, and count selection; right side shows status/history-style feedback.
- Do not change provider/API behavior, paid-call behavior, asset storage, or generation logic.

## Interaction Rules

- Existing buttons, inputs, selects, IDs, and JavaScript hooks must keep working.
- The page must remain usable in the desktop app viewport around 1366x768.
- On narrow screens, the layout collapses to one column with horizontal navigation.
- Static HTML must not introduce React/Vue/etc.

## Verification

- Add a regression test that checks the new app shell classes and the simplified two-column production layouts exist.
- Run the focused studio page tests.
- Run JavaScript syntax validation.
- Sync changed files into the packaged desktop runtime and verify the running app serves the new layout.
