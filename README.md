# Loop — taste-guided book exchanges

**Live app:** [loop-qloo.onrender.com](https://loop-qloo.onrender.com). The organizer password is `LOOP_ADMIN_PASSWORD` in the [Render service's Environment tab](https://dashboard.render.com/web/srv-db32vlcs728c73b5s4o0/env). Readers use private links from **Invite readers**. The hosted workspace uses Postgres; the included example has fictional owners and genuine saved Qloo rankings.

Loop is a working web app: create a four-reader circle, add 8–20 owned book titles, choose cultural references, find closed book exchanges, and repair the proposal after a withdrawal. Invite readers through private links so they can accept, pass and replan, edit their own favorites, or withdraw their own copies. Circles can be saved, switched, edited, and backed up. One Gemini agent invokes workspace tools; an exact deterministic solver selects the handoffs. The example circle uses genuine captured Qloo rankings with **fictional owners and offers**; personal circles use owner-declared inventory and chosen references. The app does not claim Qloo outperforms Gemini on people's preferences.

```sh
python3 -m loop_app
```

Open **http://127.0.0.1:8000**. Saved Qloo results power the original profiles without credentials or network calls. Server-side `QLOO_API_KEY` enables public-entity search and new taste profiles; `GEMINI_API_KEY` enables natural-language tool use. Without a Gemini key, guided commands and all workspace controls remain available. Set credentials using the hidden shell prompts below before starting the server. Nothing loads keys from a file.

The app saves its shared workspace, individual circles, and downloadable proposal in `local/loop-workspace/`. Click **Start your own circle** to add readers and books; click the circle name to switch or edit saved circles. See [the app guide](docs/LOOP.md) for controls and architecture. No additional Codex plugin is required. [Organizer preview](docs/assets/organizer-desktop.png) · [reader preview](docs/assets/reader-desktop.png) · [mobile reader](docs/assets/reader-mobile.png).

Free hosting is configured in [render.yaml](render.yaml), with a password-protected organizer workspace and Postgres storage. Hosted setup installs `requirements.txt`; the local saved-profile demo still uses only Python's standard library. Read [deployment instructions](docs/DEPLOYMENT.md), [the three-minute demo script](docs/DEMO.md), and [draft submission materials](docs/SUBMISSION.md).

## Qloo evidence sprint

The research toolkit below tests whether Qloo changes a personally meaningful decision before choosing between **Understudy** (event cancellation recovery) and **Loop** (book exchanges). The user authorized a seeded Loop MVP after the live mechanism checks; real inventory, independent preference judgments, and participant acceptance remain pilot requirements.

Runs on **Python 3.9+ with the standard library only**. No npm installation, database, hosted frontend, or additional packages are required.

**October 7 live checks:** both concepts pass all six shared mechanism gates using twenty artists, sixteen public books, and 48 successful Qloo/Gemini rankings. Both sources produce different valid decisions in all three variants. The baseline is **Gemini 3.5 Flash-Lite** after stronger Flash models returned capacity errors. Native Qloo explainability worked; three external ISBN lookups returned no matches. Read [the captured findings](docs/LIVE_EVIDENCE_2026-10-07.md), [Loop report](runs/book-matched-live-01/report.html), or [Understudy report](runs/artist-matched-live-01/report.html). Ownership and offers remain synthetic; preference quality and product selection remain pending. Keys were used at runtime and are not stored here.

## Run the verified synthetic example

```sh
python3 -m unittest discover -s tests -v
python3 -m shootout status
python3 -m shootout demo --out artifacts/synthetic-demo
```

Open `artifacts/synthetic-demo/understudy/report.html` or `artifacts/synthetic-demo/loop/report.html`. Each directory contains the frozen fixture, captured synthetic ranking records, comparison CSV, decision CSV, report JSON, and a standalone **comparison.png** snapshot. The rankings and UUIDs in this demonstration are hand-authored test data. Every live gate stays pending; no model/API improvement is claimed.

## Prepare actual inputs

Understudy starts with twenty real public artist names and four experimental profiles in `fixtures/understudy.json`. Costs, availability, durations, and equipment are explicitly synthetic **TEST_UNITS**, not prices or booking offers. One artist is the canceled original and remains in the comparison pool while being excluded from feasible replacement programs. Matching and graph coverage are unknown.

For Loop, copy `fixtures/book-inventory-template.csv` to `local/books.csv`, fill 12–20 actual distinct titles and authors, and correct owner labels P1–P4, language, availability, and willingness to offer each copy. Empty template titles are deliberately invalid. ISBN and neutral descriptions are optional. Then:

```sh
python3 -m shootout init-loop --inventory local/books.csv --out local/loop.json
python3 -m shootout collect local/loop.json --out local/participant-cards.json
```

Before revealing predictions, have each participant rank **all book IDs** by anticipated reading interest using the same neutral information. In `local/loop.json`:

- Set `inventory_attested: true` only after confirming actual ownership and offers.
- Fill each participant's `human_ranking` and timezone-aware `ranking_recorded_at`, e.g. `2026-10-07T09:00:00+00:00`.
- Add that person's own public artist/film/brand/book references to `references`; add a `declared` variant containing those reference IDs to their profile. The supplied experimental variants remain separate probes.
- Set `references_attested: true` only after the participant confirms those declared references. Set language restrictions and `already_read_ids` as needed. An optional `acceptable_ids` list is a hard restriction; an empty list means no books are acceptable.

Example participant reference:

```json
{"id":"p1-reference-1","name":"PUBLIC CULTURAL TITLE OR ARTIST","type":"movie"}
```

Use anonymous labels locally. Do not put personal names, email addresses, device identifiers, or contacts into cultural reference fields. Availability, ownership, participant rankings, and consent are never sent to Qloo or Gemini. Neither API receives human ground-truth rankings.

## Configure keys and inspect access

Set keys in the current shell. For zsh, these prompts hide input:

```sh
read -rs "QLOO_API_KEY?Qloo API key: "
export QLOO_API_KEY
read -rs "GEMINI_API_KEY?Gemini API key: "
export GEMINI_API_KEY
export QLOO_BASE_URL=https://hackathon.api.qloo.com
export QLOO_TRUSTED_BASE_URL=https://hackathon.api.qloo.com
export GEMINI_MODEL=gemini-3.5-flash-lite
python3 -m shootout status
python3 -m shootout preflight --out runs/preflight-01
```

The runner intentionally does not load `.env` files. No credentials appear in prompts, URLs, reports, or saved request headers. Provider-echoed key values are redacted. Preflight records authentication/access and any returned rate-limit/expiration headers. **Unexposed quota, key expiration, and free-tier entitlement remain unverified**; record organizer-supplied limits separately. A successful search/model-list request does not prove ranking capability. The example explicitly selects the verified October 7 baseline; the code's unset default remains `gemini-3.8-flash`. Model changes are explicit and recorded, with no automatic fallback. The current adapter uses the official Interactions REST API with structured output and `store: false`.

## Resolve, confirm, freeze, compare

For Understudy (substitute your Loop fixture for book experiments):

```sh
python3 -m shootout resolve fixtures/understudy.json --out local/artist-choices.json --evidence runs/artist-resolution-01 --max-requests 60
```

Inspect `resolution_options` in the resulting JSON. Manually verify names, entity types, and book authors/editions. No search result is automatically accepted. Either edit `qloo_id` and `confirmed: true`, or create `local/confirmed-artists.csv`:

```csv
id,qloo_id,unresolved
act-01,REPLACE_WITH_CONFIRMED_UUID,
act-02,,true
```

Include reference IDs in the same CSV. Explicit `unresolved=true` records a failed match; an unreviewed match remains pending. ISBN lookup uses `/entities`; if an edition fails, remove its ISBN and explicitly run name search in a new resolution attempt rather than accepting another work silently.

```sh
python3 -m shootout confirm local/artist-choices.json --csv local/confirmed-artists.csv --out local/artist-resolved.json
python3 -m shootout validate local/artist-resolved.json
python3 -m shootout freeze local/artist-resolved.json --out local/artist-frozen.json
python3 -m shootout run local/artist-frozen.json --out runs/artist-shootout-01 --max-requests 40
```

The four experimental profiles generate 24 total ranking calls across both sources; four `declared` participant profiles add eight calls. Resolution and preflight have separate explicit budgets. Set `--qloo-interval` and `--gemini-interval` (minimum seconds between that provider's calls, 0–60) from the actual key/account rate limits, particularly for Gemini's free tier. The default zero adds no guessed pacing. There are no automatic retries. Authentication/access/quota failures pause the affected source. Missing credentials still produce a pending report without network calls; successful but empty Qloo results fail coverage. Use a **fresh directory** for each run. If interrupted, the frozen input and completed rows remain saved; use `analyze` to report incomplete evidence, or start a new run in another directory.

Each run produces:

- `requests.jsonl`: complete, credential-redacted HTTP request/response evidence, including failures.
- `fixture.json` and `rankings.json`: frozen input, source/profile/variant rankings, exclusions, evidence IDs, model responses.
- `comparison.csv`: candidate-by-profile ranks for both sources.
- `decisions.csv`: matching-source decisions, feasibility, ordinal/reciprocal sensitivity, and Understudy regret.
- `report.json`, `report.html`, `comparison.png`: gate evidence and readable comparison artifacts.

Partial reports show captured ranking previews even when the other source is unavailable. Previews preserve tied midranks. Every report names the recorded Gemini model and labels synthetic operating conditions. Previews use each request's own pool; matched comparison and participant preference gates remain pending until the required evidence exists.

Loop additionally generates `acceptance-template.json` for the exact Qloo/declared/ordinal proposal. Participants review their proposed incoming book before accepting. Copy it to `local/acceptance.json`, fill true/false judgments, reasons, and `recorded_at`, then:

```sh
python3 -m shootout analyze runs/loop-shootout-01 --feedback local/acceptance.json
python3 -m shootout decision runs/artist-shootout-01/report.json runs/loop-shootout-01/report.json
```

The withdrawal test removes one selected physical copy from availability and solves again using cached rankings. It is labeled an injected test, not a real cancellation or physical handoff. A book exchange remains a proposal until the people involved accept and carry it out.

## Blinded evaluation

Fill `evaluation/cases-template.json` with ten actual captured cases: three straightforward, three conflicting, two cross-domain, two disruptions. Each case's `report_path` is relative to the manifest's location. Cases are preregistered fixtures; changing constraints requires freezing a new case. Do not label repeated copies of one case as ten independent scenarios.

```sh
python3 -m shootout review-pack local/cases.json --out local/reviewer-pack --seed 7
python3 -m shootout score-reviews local/reviewer-pack local/responses.csv --out local/evaluation-results.json
```

Give each reviewer only their `reviewer-N.json`; keep the source mapping private until judgments are recorded. Copy `responses-template.csv`, fill A/B/tie/neither and reasons. The scorer reports partial completion and all baseline wins. Fifty judgments from five reviewers do not constitute fifty independent participants.

See [PLAN.md](PLAN.md) for the current direction and [the experiment contract](docs/EXPERIMENT.md) for normalization, solvers, gates, limitations, and primary API references. The previous Understudy proposal is preserved in `docs/UNDERSTUDY_ORIGINAL.md` as historical design material.
