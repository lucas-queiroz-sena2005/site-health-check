Status: resolved
Type: task

## Issue
- The HTTP child node matched the 'active' filter incorrectly because its own status was `success`, bypassing the Host-level port stats aggregation. This resulted in false positives (warning ports appearing under active filter) and false negatives (HTTP payloads under a warning port not appearing when filtering by warning).
- The View Selector UI had an awkward layout: the dropdown was grayish, used emojis instead of text for Create/Delete actions, the delete button was disabled incorrectly for local fallback views, and it wasn't styled consistently with the rest of the dark UI.
- `⭐` was prepended to new views unnecessarily.

## Answer
- Updated `filterTree` in `HostTablePage.tsx` to force structural child nodes (`HTTP`, `SAN`) to strictly inherit their filter `matchesStatus` from their parent (`Port`). This perfectly aligns the UI filtering logic with the node stats aggregation logic.
- Restyled the `<select>` to `bg-background` and separated the `+ Create` and `✕ Delete` buttons to be standalone rounded buttons matching the `isSavingView` state buttons.
- Fixed the delete button disable-logic by strictly checking `activeViewId === 'view-default'` instead of a loose prefix match, enabling deletion of local fallback views.
- Removed the `⭐` prefix from newly created views.
