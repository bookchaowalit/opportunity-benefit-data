# book-benefit-data

Discover entitlements and support by jurisdiction and eligibility.

Status: **local source pilot**. Original v1 demo/validation remains available.
The live lane uses v2 to distinguish unknown domain terms from false and program
directories from actual awards. Seven reviewed official sources are enabled for
explicit manual acquisition; no scheduler, remote deployment or application submission.

## Users and boundary

For people and small teams discovering public and membership benefits.
Rule-based entitlement programs; marketing promotions belong to deal/freebie.

Subcategories: public-assistance, utility-support, housing-support, member-benefit, accessibility, fee-waiver.

Domain-specific terms: `jurisdiction`, `beneficiary_group`, `eligibility_evidence`, `renewal_rule`.
Each record represents one program/offer intake window. A repeat intake receives
a distinct source record ID. Cross-domain packages use `related_records` rather
than copying the same award into several products.

## Run locally

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
book-benefit-data contract              # v1 (demo)
book-benefit-data contract --version v2 # v2 (captured records)
book-benefit-data demo --open-only
book-benefit-data demo --version v2 --open-only  # v2 fixture with availability windows
book-benefit-data demo --query "public-assistance"
book-benefit-data validate src/book_benefit_data/demo.json
python -m unittest discover -s tests -v
python -m pip install -e ".[dev]"  # pytest + pinned ruff
ruff check . && python -m pytest -q
uv sync --frozen --all-extras && uv run mypy  # locked env (uv.lock) as CI installs it
```

CI (`.github/workflows/ci.yml`) runs `ruff check`, the offline test suite and a
CLI smoke test on Python 3.10 and 3.13. `tests/test_registry.py` keeps
`sources.json`, the packaged `source*.json` configs and the contract in sync.

With dependencies already available, use `PYTHONPATH=src python3 -m book_benefit_data`.
`demo` uses the fixed synthetic clock 2026-09-07T00:00:00Z unless `--as-of` is
provided. `--open-only` excludes closed, unknown-deadline, expired, stale (72h
default), and future-checked records. A v2 benefit with no application deadline
is included only while its explicit `availability` window has started and not
ended (for example the existing-beneficiary welfare variant). This is an
availability filter; it does not assert personal eligibility, selection
probability, or a guaranteed payout.

`demo --version v2` replays `demo-v2.json`, a synthetic v2 fixture with a
continuous benefit (included), a scheduled window that starts 2026-10-01 00:00
Bangkok time (included from `--as-of 2026-09-30T17:00:00Z`), an ended fixed
window and an unknown window (both excluded). Its records were checked at the
demo clock, so pass `--max-age-hours` when moving `--as-of` more than 72h later.

Contract: `src/book_benefit_data/schema.json` (`benefit.v1`).
Unknown amounts, currencies, eligibility and deadlines remain unknown. Cash,
credit, discount, in-kind benefits and access are different value kinds. Never
sum them as cash income. Queries and validation are read-only and do not persist
provided files. The `live` label requires captured lineage, but validation alone
does not verify that referenced lake objects exist or prove source truth.

## Data ownership and source policy

Owner: bookchaowalit. Public program metadata only; no applications, personal
screening answers, financial credentials, cookies, or private transcripts.
See `sources.json` and the source policy below. Select official API/export, then feed,
then bounded permitted scraping. Exact source permission and retention must be
reviewed before network ingestion. No spending, account creation or messaging.

Implemented capture flow: approved source pull → immutable landing bytes
and checksum → Bronze Parquet and manifest through the shared lake runtime →
versioned read-only contract → consumer pull. Each product owns its source
adapters and lake prefix. Producers never write into another app's database,
CRM, tasks, application tracker, or notification system.

## Remaining implementation gates

1. Keep the seven source adapters fresh and add jurisdiction-specific parser fixtures as new programs are reviewed.
2. Expand domain field extraction and live quality monitoring.
3. Package the local shared capture runtime for independent deployment.
   Current source capture and replay use the explicit data-lake runtime.
4. Add live source tests, retention/access controls and runtime monitoring.
5. Connect a read-only consumer. Personal eligibility, ranking, deadlines and
   application workflow belong to consumers with separate private storage.

No runtime port is reserved. The former `opportunity.v1` is archival; `job.v1` remains a separate job-data contract.
Breaking contract changes require a new version and a consumer migration.
There is no production deployment to roll back; discard demo output or restore
the previous contract version locally. Source permission, live availability,
real eligibility and production operations are **unverified**, not passing gates.

## Official source pilots

Sources: [GOV.UK / DWP Universal Credit](https://www.gov.uk/universal-credit),
[GOV.UK Housing Benefit](https://www.gov.uk/housing-benefit),
[GOV.UK Disabled Students' Allowance](https://www.gov.uk/disabled-students-allowance-dsa),
[GOV.UK help with court and tribunal fees](https://www.gov.uk/get-help-with-court-fees),
[NHS Healthcare Travel Costs Scheme](https://www.nhs.uk/nhs-services/help-with-health-costs/healthcare-travel-costs-scheme-htcs/),
[Royal Thai Government State Welfare Card 2569](https://www.thaigov.go.th/th/news/166567),
and [Royal Thai Government water-bill support](https://www.thaigov.go.th/th/news/166622).
The exact source configurations live in `src/book_benefit_data/source*.json`;
the enabled IDs and capture status are recorded in `sources.json`.
GOV.UK content attribution: Crown copyright, Open Government Licence v3.0.
Other providers' content remains subject to the terms recorded in each source's
`permission_evidence`. Only private source archival and bounded program metadata
extraction; no public mirror of the source body.

Run from this repo with the existing data-lake Python environment:

```bash
export SOLO_DATA_LAKE_ROOT=/path/to/solo-data-lake
PYTHONPATH=src "$SOLO_DATA_LAKE_ROOT/.venv/bin/python" -m book_benefit_data.capture acquire --lake "$PWD/data/lake" --state-dir "$PWD/data/control"
PYTHONPATH=src "$SOLO_DATA_LAKE_ROOT/.venv/bin/python" -m book_benefit_data.capture records --lake "$PWD/data/lake" --state-dir "$PWD/data/control"
PYTHONPATH=src "$SOLO_DATA_LAKE_ROOT/.venv/bin/python" -m book_benefit_data.capture acquire --source-id thaigov-state-welfare-2569 --lake "$PWD/data/lake" --state-dir "$PWD/data/control"
```

This lane depends on the explicit local shared `discovery.capture_runtime` v1
and existing `data_lake.product_adapter`. No parent-path auto-discovery, cloud
target, credentials or environment-selected lake is used. It is not a standalone
deployed ingestion package yet. The pure v1/v2 contract CLI remains standalone.

Capture preserves exact bytes, a Bronze document-metadata row and manifest before
domain parsing. Records are replayed from checksum-verified landing and Bronze
objects. The per-source control state records a fresh check even when unchanged
bytes reuse an existing immutable batch. Failed latest fetches fail closed;
parser failures leave a quarantined capture reference and no synthetic fallback.

There are at most two source GET attempts (15-second timeout each), a 2 MB
response cap and a six-hour cooldown under a local file lock. HTML sources
recheck robots.txt; API sources use their documented public API and license.
429/auth failures are not retried. Redirects need explicit policy review.
Sensitive session-token markers are refused before archive. GOV.UK sources are
read through the public GOV.UK Content API; adapters for unregistered source IDs
fail closed instead of falling back to a generic parser.

The benefit pilot is an entitlement directory, not a personal eligibility decision.
The Thai announcement is normalized into two availability variants: existing
beneficiaries start on 2026-08-01 and new or reviewed beneficiaries start on
2026-10-01. The water-support announcement is normalized as a continuous utility
credit starting 2026-07-20, with a published maximum of THB 100 per household per
month under its billing conditions. Amounts, qualification results and claim
outcomes remain subject to the official terms and identity verification.
`records` reports the captured check time; callers must apply their freshness
window. No personal eligibility decision is inferred from country or page title.
Retention is operational in a private local archive; cleanup is manual under the
repository data lifecycle policy. No automatic deletion or source republication.
