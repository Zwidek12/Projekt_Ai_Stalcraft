# StalcraftDB - Selectors and Endpoints

## Data source strategy
1. Primary source: JSON API (`/api/market/items/{item_id}/prices`).
2. Fallback source: HTML market page (`/market/items/{item_id}`).
3. JS-only fallback: extension point prepared in scraper (`mock_js_fallback` source in MVP).

## API contract assumptions
Expected payload:
```json
{
  "item_name": "AK-103",
  "history": [
    {
      "price": 12000,
      "volume": 5,
      "timestamp": "2026-04-28T18:00:00Z"
    }
  ]
}
```

## HTML selectors
1. Item title: `h1.item-title`
2. History table: `table.market-history`
3. Rows: `table.market-history tbody tr`
4. Columns:
   - `td[0]` -> timestamp
   - `td[1]` -> price
   - `td[2]` -> volume

## Known risks
1. DOM class names can change without notice.
2. API endpoint can be rate-limited or undocumented.
3. Numeric formatting may vary by locale (spaces, commas).
4. Timestamp format may differ from ISO-8601.

## Review checklist for scraper changes
1. API-first flow remains the default path.
2. HTML fallback keeps the same output schema.
3. Invalid/missing rows are skipped safely.
4. Errors are logged with item context.
5. Tests include positive and regression cases.
