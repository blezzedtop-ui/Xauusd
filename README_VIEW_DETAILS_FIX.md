# SignalX History — View Details Fix

Fixes the Signal History `View Details` button so the detail modal is actually opened with the `.show` class required by the dashboard CSS.

Additional safeguards:
- loaded history items are cached by `signal_id`, so View Details does not require a second broad API request in normal use;
- if an item is not in cache, it is fetched from the history endpoint;
- modal close button, backdrop click, and Escape key all close the modal correctly;
- errors are surfaced through the existing toast instead of being silently swallowed.

No changes are intended for Signal Engine, AlgoTrade, AutoTrade, MT5 Gateway, or trading strategy logic.
