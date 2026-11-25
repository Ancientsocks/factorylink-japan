# ADR-002: Japanese-first localisation support

- Status: Accepted
- Date: 2026-11-03

## Decision
Support Japanese and English through a central message catalog. Use `Asia/Tokyo` and JPY as Japanese-market defaults, while storing timestamps as UTC-aware database timestamps and allowing each organisation's timezone/currency to be represented.

## Consequences
User preferences can persist across sessions. Date-only fields remain calendar dates and should not be converted as instants. New UI text must be added to both language dictionaries. A professional translator/domain reviewer should validate manufacturing terminology before customer deployment.
