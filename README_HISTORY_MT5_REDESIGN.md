# History redesign

- MetaTrader 5 section shows only Auto Trading history using `auto_only=true`.
- Auto Trading rows are stored with `source="Auto Trading"` and `auto_entry=true`.
- Signal History is a dedicated full-history screen for all non-auto module signals plus Auto Trading records.
- Both screens expose TOTAL SIGNALS, COMPLETED, TAKE PROFIT, STOP LOSS, OPEN, AMBIGUOUS and WIN RATE.
- Both screens support date selection and ascending/descending chronological order.
- Section navigation scrolls to the top and does not vertically center content.
