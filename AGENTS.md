# YanTian OS local integration

The original visitor-h5 and Core are the parent platform. Civilization Studio is
a mounted module, not a separate OS or second editable knowledge store.

- LOCAL_OS_MODE requires an explicit CIVILIZATION_DB_PATH and fixed yantian /
  yantian-main scope. One Core-owned CultureService serves Studio, legacy
  knowledge APIs, NPC answers and tool retrieval. Preserve original IDs/versions.
- Culture knowledge, designs, exact-version approvals and learning candidates
  share one SQLite transaction boundary. Never add independent PG/Evidence writes
  or claim PG and SQLite form a single atomic transaction.
- Keep source/rights/region gates, stale-version 409s, SVG sanitation and local
  same-origin write checks. A local role declaration is not verified identity.
- Machines, external models, embeddings and Qdrant are disabled in local mode.
- Local cultural-document intake retains source hashes, paragraph locators and
  immutable knowledge versions in the existing culture SQLite. A faithfully
  extracted document statement is not an independently verified historical fact.
  Show pending claims and competing passages with their labels; do not silently
  promote them through legacy edits or reviews. Missing material stays missing.
  Registered source/passages APIs may return selected local excerpts, never an
  arbitrary filesystem read or private absolute path. Local intake authorization
  does not grant public, commercial or training use.
- Use scripts/local_os.py and an isolated dedicated PostgreSQL cluster. Do not
  run original tests/conftest.py against its hard-coded existing test database;
  it drops tables. Use Core local_tests and Studio temporary-DB tests.
- Preserve ordinary profile behavior. Local schema bootstrap does not repair,
  stamp or authorize historical production migration graphs.
- Never commit local data, environment files, dependency symlinks, credentials,
  logs, browser sessions, or raw private records. Keep foreground apps untouched.

- Local operations are under `/api/local-os/operations` and `/operations`. Keep business inventory, holds, orders and receipt records in one dedicated operations SQLite transaction boundary. Do not turn manual receipt records into verified bank/platform payments, create synthetic business facts, or duplicate culture knowledge.
- The local `/stay` catalog/inquiry preview is not a public deployment or confirmed booking. Platform accounts, publication and payment adapters remain disconnected.

- Growth `/growth` and `/api/local-os/growth` reuse DDT workflow semantics with YanTian inputs only. Keep gr_* in operations SQLite, exact-hash material versions and local operator review distinct from finished video, publication or verified acquisition. Imported local configurations, historical photos and generated concepts retain source/type/date; current owner confirmation does not upgrade old model prices or historical execution states.

- Source room-state observations use rs_* in the same operations SQLite and `/api/local-os/room-status`. Preserve blanks, source reservation status, source dates and resolved-year provenance. Never turn aggregate room-type observations into fabricated room IDs, confirmed orders, payment or cleared sellable inventory. Source-bound growth campaigns/packages must retain snapshot/window identity; a new active source version invalidates old approval and requires selection from the new source.

- The local homepage is layer-one `/workspace`: sentence/photo/attachment to operating proposal. `ws_*` versions stay in the operations SQLite. Photos are references/OCR until a visual model is explicitly integrated; extracted raw private records do not enter plans, logs or provider requests. Reuse the existing CREATE context and room-source readers.
- Confirming an exact proposal hash adopts only its planning direction. A separate explicit handoff creates one deduplicated layer-two growth task; it does not compile scripts, reserve rooms, publish or collect money. Revisions and changed inputs/sources invalidate confirmation. Third-layer village-management model remains planned, not an implemented large model.

- Second-layer local rendering has a separate exact-package-hash confirmation. It approves script/storyboard/reference labels for a local preview, not publication rights or product delivery. Render jobs and confirmation records stay in the existing operations SQLite; artifact files stay under its local data directory and are excluded from source archives.
- Queue and encode outside SQLite transactions and the request event loop. Snapshot and revalidate source, asset and version fingerprints; changed inputs invalidate current confirmation/output, while old artifacts remain labeled history. Interrupted or failed jobs require an explicit retry. Run bounded offline FFmpeg argument lists, with fixed job-owned paths, cancellation and media integrity checks; never accept browser-supplied commands or output paths. Rendering cannot write business inventory, payment, publication or machine state.

## Recent changes (2026-10-28)

- Current model scope has 19 capabilities after video creation was removed on
  2026-10-22. Preserve historical content/render code and results; do not infer a
  request to resume video work from their presence in the repository.
- Cited culture QA and local document intake were exercised on 2026-10-23.
  Historical acceptance, today's service availability and cultural fact review
  are separate states. See docs/local-handoff.md before resuming local work.
