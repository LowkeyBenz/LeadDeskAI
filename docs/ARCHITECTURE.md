# Architecture

- `src/leaddesk_ai/core`: paths and logging
- `src/leaddesk_ai/db`: schema and repository
- `src/leaddesk_ai/services`: business rules, backups, calculations, compliance
- `src/leaddesk_ai/ui`: PySide6 user interface
- `tests`: automated regression tests

The UI depends on repository/service interfaces. Business rules do not depend on Qt, allowing them to be tested without opening a window.
