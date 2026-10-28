# Local V1 API contract (frozen first slice)

All JSON keys below are stable. Backend may add fields but must not rename them.
Local FastAPI app with static HTML/CSS/JS at /. No external model or machine calls.
Every mutating request must carry X-Yantian-Local: 1. Reject a foreign Origin.
Validation errors return HTTP 4xx and {detail: human-readable message}.

GET /api/status -> {app_name,version,mode:"local",model:{connected:false,mode:"extractive"},machine:{enabled:false},counts:{sources,knowledge,designs,reviews},data_path_label}
GET /api/sources -> array
POST /api/sources -> {id,title,url,source_kind,scope,rights_scope,created_at}; input {title,url,source_kind:"public"|"local"|"oral"|"project",scope,rights_scope:"internal"|"unknown",locator?}. URL empty permitted for local source; only http(s) URLs accepted. Never fetch remote URLs.

GET /api/knowledge -> array of {id,title,content,source_id,locator,region_scope,domain,kind,review_status,rights_scope,version,source:{id,title,url},created_at}
POST /api/knowledge -> same; input {title,content,source_id,locator,region_scope,domain:"humanities"|"nature"|"craft"|"project",kind:"fact"|"interpretation"|"requirement",review_status:"draft"|"source_checked"|"approved"|"disputed"|"retired",rights_scope:"internal"|"unknown"}
PUT /api/knowledge/{id} -> new version, same input plus {base_version}; preserve old versions and reject stale base_version409. Source_checked means publication checked, not confirmed Yantian fact or artisan approval.
POST /api/ask input {question} -> {id,question,answer,status:"answered"|"insufficient_evidence",mode:"extractive",model_connected:false,citations:[{knowledge_id,knowledge_version,title,source_title,url,locator,region_scope,review_status,excerpt}],limitations:[string]}. Cite every selected factual excerpt. No match/rights unknown/draft/retired/disputed returns insufficient. For question specifically about 严田 facts, regional 徽州 material alone cannot answer as Yantian fact. Queries are recorded without fake model claims.

GET /api/designs -> array current design summaries
POST /api/designs/preview -> {svg,hash?}, same design input; validate/generate/sanitize only, do not persist a design/version/review.
POST /api/designs -> design detail; input {title,purpose:"print_block"|"decorative"|"undecided",label,width_mm,height_mm,motif:"geometric"|"leaf"|"wave",mirror_choice:"yes"|"no"|"unconfirmed",knowledge_ids:[id],note,svg?}. These patterns are original design exercises, not historical motifs. Width/height describe requested design dimensions, not machine capability. Validate finite 30..500 mm; label <=30 characters, title <=120. Backend generates safe SVG when svg omitted; optional user SVG must use strict allowlist and no resources/scripts/events. No fabrication parameters/G-code.
GET /api/designs/{id} -> {id,title,purpose,label,width_mm,height_mm,motif,mirror_choice,knowledge_ids,note,version,hash,svg,status:"draft"|"needs_revision"|"approved"|"source_changed",versions:[{version,hash,created_at}],reviews:[{id,version,design_hash,reviewer_role,decision,comment,created_at}],created_at}
PUT /api/designs/{id} same input plus {base_version} -> immutable new version. Reject base_version stale with409. Old reviews retained but never approve new version.
GET /api/designs/{id}/svg?version=N -> sanitized SVG attachment, supports current or historical version, filename woodcut-ID-vN.svg
POST /api/designs/{id}/reviews input {version,reviewer_role,decision:"approve"|"revise",comment,confirmations:{culture:boolean,rights:boolean,craft:boolean}} -> {review,design}. Approve requires all confirmations, nonempty comment and role, defined purpose, explicit mirror_choice for print_block, unchanged usable source versions, exact current version/hash. No source required for original geometric exercise; if source selected it must be usable. A review is a local declaration, not independently authenticated artisan identity. Preserve all comments including requests for revision.
GET /api/learning-candidates -> array {id,design_id,design_version,review_id,comment,state:"pending_review",training_rights:"unknown",created_at}; reviews generate candidates only, never automatically train.
GET /api/export -> downloadable JSON of sources, knowledge versions, designs/versions/reviews/candidates and cited QA history; no secrets or runtime paths.
GET /api/machines/capabilities -> {enabled:false,route:"hand_woodcut",state:"not_configured",operations:[],message}
POST /api/machines/jobs (any payload) -> HTTP423 {detail:"机器接口未启用；本版仅支持手工稿样与审阅。"}; no queued job or device event.

Backend seed: only root-provided seed.json, initialize once. No simulated orders,
historian approval, artisan identities, production receipts or metrics. Public
facts and project requirements may be source_checked; distinct scopes shown.
Home should show four working modules: knowledge, cited QA, woodcut drafts,
artisan reviews/feedback; a dashboard may use real local record counts only.

## Local document intake and cited cultural QA (2026-10-23)

The earlier no-draft-answer rule continues to apply to `curated_claim` (the
backwards-compatible default). A separate `document_statement` is **an exact
original-document excerpt, not an approved cultural fact**. Only the local CLI
can create these records after original-file SHA256 and paragraph/JSON-pointer
quote verification. POST knowledge with this type is rejected422; PUT of an
imported document statement is rejected409, even if the caller omits its type.
Legacy edit/verify cannot upgrade it either. Original corrections are reimported
as immutable versions; no permissions for training/publication are inferred.

Operator CLI, against the existing canonical culture SQLite only:

```
python ingest.py --db /operator/selected/studio.sqlite3 --bundle /operator/selected/intake.json --receipt /operator/selected/receipt.json
```

`import_bundle(db_path, bundle)` is the same Python entry point. The caller must
initialize canonical schema first with `create_app`; no second database is
created. The CLI always verifies local originals. Its optional `verify_files=False`
Python parameter is reserved for synthetic temporary-DB tests. There is no HTTP
path/import endpoint. Original paths exist only in the selected input package;
they do not enter SQLite, public responses, exports or receipts.

Input schema `yantian-culture-intake.v1`:
- `batch_key`: stable operator label.
- `sources`: SourceInput fields plus id, document_key, sha256, filename (basename
  only), temporal_scope, region_scope.
- `documents`: source_id, absolute local path, sha256 (one per source).
- `knowledge`: KnowledgeInput fields plus stable id; evidence_type must be
  document_statement; kind interpretation/requirement; review_status draft or
  disputed; issue_ids and aliases are optional bounded string arrays. Content is
  exact original text, never a summary. Every entry has an explicit locator.
- `issues`: id,title,description,kind (missing/disputed/unreadable/verification/
  rights),status open,source_ids,knowledge_ids,topics,scope. A disputed issue must
  identify at least two original viewpoints.

Supported fixed original readers: DOC via `/usr/bin/textutil` (20-second timeout),
DOCX `word/document.xml` text paragraphs (no macro/external-resource execution),
JSON via JSON Pointer to a string, TXT/MD nonempty lines. File/text/XML and record
sizes are bounded. Locators are `文本提取非空段 Pnnn，字符 A—B（Unicode字符，含首尾）`,
`文本提取非空段 Pnnn—Pnnn，各段原文按顺序换行连接`, `第N段` for text fixtures, or
`JSON Pointer /path/to/value`. Any quote/hash/locator failure rejects all record
writes. Unsupported/unreadable inputs must remain a gap; no placeholder facts.

Original source snapshots are immutable with version and SHA256. Replaying the
same semantic bundle returns the same receipt with replayed true; changing only
the batch label creates a new receipt but no duplicate source/passage/knowledge
versions. Changing a logical entry appends its version; old source, paragraph,
issue and QA snapshots remain readable. A newer original-document version makes
old-version excerpts ineligible for current question retrieval.

Additional read-only endpoints (all IDs are stable database IDs; no paths):
- GET /api/sources/{id} -> `{source,passages,issues}`. Source adds filename,
  document_key,sha256,version,temporal_scope,region_scope,local_use_scope
  local_excerpt_only,fact_verification unverified,training_rights unknown,
  is_current_version. Passage adds id,source_id,source_sha256,source_version,
  locator,text,sha256,section_title,aliases,created_at,fact_verification.
- GET /api/passages/{id} -> passage fields plus source.
- GET /api/issues -> current immutable-version issue snapshots.
- GET /api/imports -> receipts with id,batch_key,bundle_hash,source_ids,
  knowledge_ids,passage_ids,issue_ids,counts,replayed,original_files_verified,
  original_fragments_verified,model_connected false,training_performed false.
- GET /api/status retains exact old counts and adds culture_coverage with
  passages,open_issues,imports,document_statement_notice.
- GET /api/export additionally includes passages,issue_versions,imports.

POST /api/ask keeps its original keys. It additionally returns:
- evidence_state: document_statement / curated_claim / insufficient;
- disputed:boolean; issues: matched issue snapshots; gaps: string array;
- citations add source_id,filename,source_version,source_sha256,source_scope,
  temporal_scope,evidence_type,fact_verification,passage_id,passage_sha256,
  issue_ids. excerpt is the **complete selected original fragment**; its hash,
  original source version and locator are saved in QA history.

Document draft/disputed excerpts can answer only as attributed, unverified
"资料记载". Topic-relevant disputed viewpoints are displayed together without
resolving chronology, numbers or attribution. Generic place/culture words do not
establish a subject match. Current opening, availability/pricing and heritage
practitioner identity questions fail closed with a specific gap. Regional or
project evidence cannot establish a Yantian origin/history claim. No match gives
insufficient_evidence, never a fabricated synthesis. There is no LLM/provider,
training job, video creation, network lookup or machine call in this workflow.
