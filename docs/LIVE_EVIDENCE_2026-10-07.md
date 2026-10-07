# Live Qloo and Gemini evidence — October 7, 2026

Both supplied keys authenticated. The matched experiment now contains **48 successful ranking responses**: twelve Qloo and twelve Gemini requests for each of the artist and book pools. Both concepts pass all six shared mechanism gates. **Product selection remains pending** because ownership, offers, availability, and costs are synthetic test conditions; participant and organizer validation has not happened. This shows that the ranking source changes feasible decisions, not that Qloo predicts people's preferences better.

## Matched comparison

| Measure | Understudy | Loop public-book probe |
|---|---|---|
| Confirmed candidates | 20/20 artists | 16/16 books |
| Common candidates across all sources/profiles | 20 | 16 |
| Qloo / Gemini successful ranking responses | 12 / 12 | 12 / 12 |
| Distinct Qloo profile pairs with Spearman ≤0.60 | 5 | 5 |
| Qloo music-only versus mixed-domain ordering changes | 8/8 | 8/8 |
| Ordinal decisions changed by ranking source | 3/3 variants | 3/3 variants |
| Valid ordinal and sensitivity outcomes | 12/12 | 12/12 |
| Shared mechanism gates | All six pass | All six pass |
| Product-specific evidence | Organizer inputs pending | Real inventory, human rankings, acceptance, and participant withdrawal check pending |

The frozen inputs are unchanged from the Qloo-only run. All twenty-four Qloo rankings were replayed with `cached_from` and original evidence IDs; **no additional Qloo requests** were needed. The successful Gemini access probe was also reused for its exact matching first row. Each source uses the same pool, operational constraints, normalization, and deterministic solver.

The baseline is **`gemini-3.5-flash-lite`**, fixed before the matched comparisons. Gemini 3.8 Flash returned two HTTP 503 responses and a read timeout through Interactions, then another 503 through `generateContent`. Gemini 3.7 Flash returned 503. Flash-Lite passed the full structured-ranking access probe. This is an availability-driven substitution, and these results cannot be presented as a comparison against 3.8 Flash. Google's model catalog returned version `3.5-flash-lite-07-2026`; ranking responses identify the model as `gemini-3.5-flash-lite`. [Model documentation](https://ai.google.dev/gemini-api/docs/models), [model-selection record](../runs/baseline-settings-live-01.json), [authenticated catalog response](../runs/gemini-access-live-01/requests.jsonl)

Understudy's ordinal decisions illustrate the source difference under identical **synthetic** operating conditions:

| Reference variant | Qloo-selected program | Gemini-selected program |
|---|---|---|
| Music only | Arlo Parks + Four Tet | Jordan Rakei + Four Tet |
| Music + films | Arlo Parks + Four Tet | Mitski + FKJ |
| Music + brands | Arlo Parks + Bonobo | Little Simz + Bonobo |

All six programs are feasible. For music-only, the Gemini program costs 85 TEST_UNITS versus Qloo's 90; these units are not prices. Each system's own fit/regret index describes its own ranking and is not an independent quality score or evidence of a preference win.

For Loop's music-only variant, all four test owners receive a book in both systems:

| Hypothetical recipient | Qloo proposal | Gemini proposal |
|---|---|---|
| P1 | The Great Gatsby | Never Let Me Go |
| P2 | The Dispossessed | Beloved |
| P3 | The Stranger | The Dispossessed |
| P4 | Beloved | The Handmaid's Tale |

Qloo proposes one four-owner cycle; Gemini proposes two two-owner cycles. Neither is an accepted physical exchange. Adding film references changes Qloo's incoming books for P2 and P3; the selected Gemini exchanges remain the same. A shared injected withdrawal of the Beloved copy yields valid repairs for both sources across all three variants. This supplemental test leaves Loop's real participant withdrawal gate pending. [Withdrawal evidence](../runs/book-matched-live-01/withdrawal-probe.json)

**Baseline ties are a material limitation.** Eight of twelve Gemini responses in each pool contain ties, often large groups. The solver retains midranks; no tie is broken to favor Qloo. Only four cross-source comparisons per pool retain the required eight untied candidates for Spearman. Those correlations are saved; insufficient comparisons stay unmeasured. This does not affect the preregistered contrasting-profile gate, which tests Qloo's profile pairs. Independent human evaluation may still be inconclusive if fewer than 28 comparable untied pairs remain.

- [Loop matched report](../runs/book-matched-live-01/report.html), [ranking table](../runs/book-matched-live-01/comparison.csv), [PNG snapshot](../runs/book-matched-live-01/comparison.png), [diagnostics](../runs/book-matched-live-01/matched-diagnostics.json)
- [Understudy matched report](../runs/artist-matched-live-01/report.html), [ranking table](../runs/artist-matched-live-01/comparison.csv), [PNG snapshot](../runs/artist-matched-live-01/comparison.png), [diagnostics](../runs/artist-matched-live-01/matched-diagnostics.json)
- [Project-selection result: pending](../runs/matched-decision-live-01.json)

## What was verified

| Capability | Observed result | Evidence |
|---|---|---|
| Authentication and search | Successful authenticated search. | [Preflight](../runs/key-access-network-01/preflight.json) |
| Artist resolution | 20/20 artist candidates manually confirmed from names, types, and returned descriptions. | [Frozen artist input](../runs/artist-shootout-live-01/fixture.json), [lookup responses](../runs/artist-resolution-live-01/requests.jsonl) |
| Book resolution | 16/16 public titles matched to reviewed works using title, author/year disambiguation, and plot metadata. These are not an actual participant inventory. | [Frozen book probe](../runs/book-shootout-live-01/fixture.json), [lookup responses](../runs/book-resolution-live-01/requests.jsonl) |
| Constrained artist ranking | All 12 experimental profile/variant queries ranked all 20 frozen artists; none returned an outside-pool entity or omitted a candidate. | [Artist rankings](../runs/artist-shootout-live-01/rankings.json) |
| Constrained book ranking | All 12 queries ranked all 16 frozen books; none returned an outside-pool entity or omitted a candidate. | [Book rankings](../runs/book-shootout-live-01/rankings.json) |
| Native explainability | An additional book query with `feature.explainability=true` returned per-result explanation metadata for 16/16 books, plus aggregate input influence. | [Capability results](../runs/book-capabilities-live-01/results.json), [raw response](../runs/book-capabilities-live-01/requests.jsonl) |
| Lookup by Qloo ID | `/entities?entity_ids=...` returned the expected Dune entity. | [Identifier checks](../runs/identifier-followup-live-01/results.json) |
| External ISBN lookup | Dune ISBN-13 and The Great Gatsby ISBN-13/ISBN-10 queries each returned HTTP 200 with no matches, despite ISBN metadata in search results. The cause is unverified; do not depend on this lookup for the pilot. | [Initial ISBN probe](../runs/book-capabilities-live-01/results.json), [follow-up checks](../runs/identifier-followup-live-01/results.json) |

## The observed taste mechanism

The candidate pools and operational constraints were fixed before the ranking calls. Adding public references changed all eight music-only versus mixed-domain ordering comparisons in each pool. Exact returned-score ties were absent in the 24 experimental ranking responses.

For example, the electronic profile ranked the same sixteen books differently:

| References | First | Second | Third |
|---|---|---|---|
| Daft Punk + Aphex Twin | The Road | The Great Gatsby | The Stranger |
| Same music + Blade Runner 2049 + Tron: Legacy | The Road | The Hobbit | Frankenstein |

This shows a change in Qloo's ordering. It does not show that a person would prefer the second ordering.

For books, the alternative versus soul music-only profiles had Spearman correlation **−0.271** over sixteen untied candidates; soul versus electronic had **−0.300**. Across the three variants, five distinct profile pairs had correlation ≤0.60. Some profiles remained similar: soul versus roots was **0.847** for music-only and had identical first-three books. Artist diagnostics also found five distinct pairs ≤0.60 across variants.

The application-defined ordinal utilities changed feasible decisions under **synthetic** constraints:

- Understudy selected **Arlo Parks + Four Tet** for music-only references and **Arlo Parks + Bonobo** for music-plus-brands, with the same budget, timing, and availability conditions.
- Loop's music-only test cycle proposed Beloved → P4, The Dispossessed → P2, The Stranger → P3, and The Great Gatsby → P1. Adding film references changed the incoming books for P2 to The Secret History and P3 to The Hobbit. All ownership and offers in this coverage probe are invented test conditions.
- Removing Beloved from each test proposal produced a different valid exchange using the cached rankings. This was an injected withdrawal, not a real participant action or an accepted exchange.

Ordinal versus reciprocal-rank sensitivity is saved in both diagnostics files. It changes Loop's selections in all three variants and makes Understudy's music-plus-films case infeasible at the same numeric fit floor. These utility scales differ; no formula or threshold was tuned to favor Qloo.

Source-only diagnostics use the intersection of that source's twelve requests. The original Qloo-only reports below remain partial historical evidence. The matched reports above contain both sources and the completed shared gates.

- [Artist diagnostics](../runs/artist-shootout-live-01/qloo-only-diagnostics.json)
- [Book diagnostics](../runs/book-shootout-live-01/qloo-only-diagnostics.json)
- [Artist ranking table](../runs/artist-shootout-live-01/comparison.csv), [report](../runs/artist-shootout-live-01/report.html), [PNG](../runs/artist-shootout-live-01/comparison.png)
- [Book ranking table](../runs/book-shootout-live-01/comparison.csv), [report](../runs/book-shootout-live-01/report.html), [PNG](../runs/book-shootout-live-01/comparison.png)

## Matching decisions and exclusions

The public reference lookup resolved 23 of 24 original references. ACRONYM returned zero matches, so its exclusion was recorded before freezing. The electronic brand variant retained Adidas alone; no replacement brand was introduced after seeing rankings. All other mixed variants retained their original music anchors and two references from the additional domain.

Reviewed film matches include Her (2013), Mulholland Drive (2001), Moonlight (2016), and Little Women (2019). The experimental Fenty reference was clarified to Fenty Beauty before ranking, and Levi's matched Qloo's Levi Strauss & Co. entity. These are experimental reference choices, not claims about a participant's stated preferences.

For Frankenstein, the first two results were adaptations by Deanna McFadden and Malvina G. Vogel. The probe used **Frankenstein: The 1818 Text**, with returned disambiguation identifying Mary Wollstonecraft Shelley. Other same-work editions were not combined or substituted after rankings. Physical-copy edition matching will still be needed for real books.

The resolver preserves Qloo's `disambiguation` field so author information remains available in match choices. Partial reports display captured ranking previews while keeping missing-baseline gates pending. Reports now identify the baseline model and synthetic operational inputs prominently, and show equal midranks in previews instead of implying a strict order for ties. **37 tests pass**, including regression checks for these safeguards.

## Limits, credentials, and outstanding work

Observed headers report **5 requests per second** and **10,000 requests per month**. The last observation, October 7 at **14:30 IST**, reported **9,910 monthly requests remaining**. The live checks consumed 90 successful HTTP requests; a sandbox DNS failure never reached Qloo. The first successful artist ranking was reused and labeled with its original evidence path, rather than sent twice. Expiration was not exposed; the quota-reset header is not a key-expiration timestamp.

Both credentials were used only in process memory and authentication headers. They were not saved in source, `.env`, fixtures, prompts, or evidence. Because they were supplied in chat, replace them before public-demo use. No personal participant data was sent to either API.

Gemini used **30 HTTP attempts**: one authenticated model-list request, twenty-four successful ranking calls, four captured 503 responses, and one captured read timeout. Replay records are not additional network calls. The matched run paced new requests at twelve-second intervals as a conservative experiment setting, not a verified account limit. Actual project quota, key expiration, and billing/free-tier entitlement were not exposed. Google documents free access for this model but that does not verify this account's billing tier. No billing settings were changed. [Pricing](https://ai.google.dev/gemini-api/docs/pricing), [rate limits](https://ai.google.dev/gemini-api/docs/rate-limits)

Next requirements:

1. Gather real inputs before running a new participant pilot; keep these coverage-probe rankings separate from its evaluation.
2. Collect 12–20 actual offered books from four participants, with ownership, language restrictions, real declared references, and independent pre-reveal rankings.
3. Resolve that actual inventory, freeze a new participant experiment, collect acceptance of a precise ≥3-owner proposal, and test a withdrawal.
4. Obtain credible organizer inputs before Understudy can qualify as a product.

The mechanism passes for both public pools against the specified Flash-Lite baseline. The next evidence is independent preference agreement and acceptance on actual offered books, or credible organizer inputs. Product code remains gated on that evidence.
