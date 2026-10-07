# Experiment contract and interpretation

The evidence sprint compares Understudy and Loop before authorizing product work. No product frontend, booking system, payments, or multi-agent system is implemented.

## Frozen input

`version: 1`, an anonymous `id`, `kind` (`understudy` or `loop`), `provenance`, 1–20 candidates, public cultural `references`, exactly four `profiles`, and operational `constraints`. The intended pilot sizes are 15–20 artists and 12–20 distinct books. Each profile supplies `music_only`, `music_movies`, and `music_brands`; mixed variants retain the music anchors. Experimental profiles are probes, not inferred demographics. Loop adds four anonymous participants and their own `declared` references.

Every candidate/reference has a stable local `id`, public `name`, Qloo entity `type`, and, after manual matching, a UUID `qloo_id` and `confirmed: true`. Qloo match choices are saved but never automatically accepted. A book's physical owner and language remain local. Only public cultural names/IDs reach Qloo. Distinct candidates must resolve to distinct cultural entities; this sprint deliberately avoids duplicate editions/copies of the same work.

Freeze the complete input after collecting human rankings and confirming identities. The SHA-256 hash includes all constraints, reference variants, and participant rankings. Changing any of those requires a new experiment. Comparisons reject rankings from a different frozen fixture.

## Shared ranking and mathematical policy

Qloo ranks the supplied IDs through `/v2/insights`; Gemini ranks the same resolved pool and public references. Gemini does not receive owners, human rankings, or reviewer decisions. Cost and availability are handled downstream for both versions. The primary ranking uses returned order, with exact returned-score ties grouped. Missing scores are retained as unknown; raw affinities are never treated as probabilities.

Only the intersection ranked in every required source/profile/variant is solved, with all exclusions visible. Incomplete requests keep the comparison pending. For a common pool of size N, midrank r gives `q = (N-r)/(N-1)`. Sensitivity uses `q = 1/r`. Both sources use the same normalization and solver. Spearman diagnostics exclude tied candidates and require at least eight untied common entries per profile pair. Count distinct profile pairs, not several variants of one pair.

Understudy enumerates ordered one- and two-act programs. Fee units are integers; availability windows and times are minutes relative to the affected slot's start. Check budget, expiry, equipment, original/protected exclusions, minimum performance time, and changeovers. Program utility is the best included candidate per profile. Among programs meeting all fit floors, maximize worst fit, then weighted average fit, then minimize changes and cost, with a canonical tie-break. The individually ideal feasible program ignores other profiles' cultural floors while retaining operational constraints; regret is ideal minus selected utility. The original outline is a relative rank-based reference, not a measured embedding or recovered percentage of culture.

Loop enumerates closed 2–4-owner, one-for-one exchanges. Each person sends and receives at most one offered physical copy. Require availability, correct ownership, language compatibility, no already-read titles, explicit acceptability restrictions if supplied, and the same fit floor. Optimize participants served, then worst recipient fit, then total fit, with a canonical tie-break. Preserve Pareto states during disjoint-cycle selection so local tie-breaking cannot discard a globally optimal result. Proposals are internal artifacts, not executed transfers. Every actual participant must accept before a physical exchange.

## Preregistered gates

Require ≥80% candidate resolution, ≥8 common candidates, two distinct contrasting profile pairs with Spearman ≤0.60, a cross-domain ordering change, a different feasible decision between ranking sources, and valid operational proposals. Synthetic recordings cannot pass any live gate. Missing keys, unconfirmed identities, and unavailable human evidence remain pending.

Understudy additionally requires credible organizer inputs to be selected as a product. A synthetic operational fixture with live Qloo results proves only a mechanism.

Loop additionally requires owner-attested inventory, independently recorded rankings of the entire pool, real declared references, higher pairwise agreement for at least three of four participants, an accepted Qloo-proposed cycle of ≥3 owners, and successful withdrawal repair (or an explicit no-exchange outcome). Human rankings must predate the recorded run. Both systems are scored on the same untied pairs; require at least 28 such comparisons per participant to prevent a result based on a handful of comparisons. This conservative pilot default is not a statistical significance threshold. Record baseline wins and participant ties.

Acceptance reviews refer to the exact proposal ID and must be recorded after the run started. Withdrawal tests explicitly inject removal of a selected copy and use the same cached ranking matrix. This tests the solver's recovery, not a real participant cancellation. Choose Loop if eligible, otherwise Understudy if eligible; keep a decision pending while required evidence is missing; reopen ideation when both complete experiments fail.

## Evidence and failures

Every attempted HTTP request records provider, timestamp, method, URL parameters, request body, status, response, observable limit headers, duration, and evidence ID. Keys stay in environment variables and authentication headers. Known key values and sensitive fields are redacted even if a provider echoes them. Redirects are blocked. No implicit retries occur. HTTP 401/403/429 and request-budget exhaustion pause a provider. Key expiration and account quota remain unverified unless the provider exposes them or the organizer supplies them; API access does not establish free-tier billing entitlement.

One workspace lock prevents simultaneous runs. After an abrupt process kill, inspect the PID in `.shootout.lock` before deleting a stale lock. Use a fresh output directory per run; evidence files are not overwritten. Refreshing reports uses saved responses and sends no requests. This is deliberately local research tooling, not a production recovery framework.

## Evaluation

The ten-case manifest has 3 straightforward, 3 conflicting, 2 cross-domain, and 2 disruption cases. Supply actual captured cases; template slots are not evaluated cases. Five reviewer packs randomize both case order and source labels. Keep `private-mapping.json` private until votes are recorded. Reviewers receive the same neutral title information, constraints, and public references, with prediction scores hidden. Preferences allow A, B, tie, or neither and require reasons. Fifty judgments from five reviewers are not fifty independent participants. Human rankings measure anticipated interest, not pleasure after reading or event attendance.

## Primary documentation

- [Qloo parameter reference](https://github.com/qloo/docs-public/blob/main/reference/parameters.md)
- [Qloo entity identifiers](https://github.com/qloo/docs-public/blob/main/reference/get-entities.md)
- [Qloo score interpretation](https://github.com/qloo/docs-public/blob/main/docs/interpreting-affinity-scores.md)
- [Qloo taste analysis](https://github.com/qloo/docs-public/blob/main/reference/taste-analysis.md)
- [Gemini structured output](https://ai.google.dev/gemini-api/docs/structured-output)
- [Gemini Interactions REST API](https://ai.google.dev/api/interactions-api-v1)
- [Anthropic Project Swap](https://www.anthropic.com/research/project-swap)
- [Earlier Qloo TasteSwap submission](https://devpost.com/software/tastemate-ygufsc)
