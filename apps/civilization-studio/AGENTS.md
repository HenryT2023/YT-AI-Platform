# Civilization Studio local V1

This module is the authorized local first release for cultural knowledge, cited
answers, editable traditional woodcut drafts, artisan review and feedback.

- Bind to 127.0.0.1 by default. SQLite stays in a user-selected local data folder.
- No production migrations, model/provider calls, external sends or machine I/O.
- All facts need source, locator, scope, review state and use scope. Never turn
  regional facts into a specific Yantian origin/history claim.
- Mark generated geometric designs as new design exercises, not heritage motifs.
- Source/question/draft inputs are untrusted. Escape HTML, sanitize SVG with a
  strict element/attribute allowlist and deny scripts, external resources/events.
- Reviews bind exact immutable design versions. Editing invalidates approval;
  stale-version approval must fail. Training candidates remain unreviewed.
- Preserve unrelated files. Work ownership is split by the active task.
- Use isolated test databases. Never seed tests into the user's runtime database.
