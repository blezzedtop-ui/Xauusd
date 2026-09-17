# MT5 Gateway 422 JSON Fix

The Multi-Broker Gateway EA now builds its HTTP body with `StringToCharArray(..., WHOLE_ARRAY, CP_UTF8)` and removes the terminal NUL byte before `WebRequest`.

This specifically addresses FastAPI/Python `422 JSON decode error: Extra data` responses caused by a trailing NUL after an otherwise valid JSON document.

After replacing the EA, compile it in MetaEditor and attach the newly compiled EA to the MT5 chart. Do not run two SignalX gateway EAs for the same account/chart at the same time.
