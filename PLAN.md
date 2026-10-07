# Revised direction: prove the taste mechanism before choosing the product

## 1. Decision and research findings

Replace the unconditional “Build Understudy” decision with an **October 7–8 evidence sprint**. The former proposal is preserved in [the original design](docs/UNDERSTUDY_ORIGINAL.md) as conditional historical reference.

**Current implementation direction:** the user subsequently authorized building a seeded Loop demo. The shared live mechanism checks have passed, and `loop_app/` now implements a working exchange workspace and agent. Genuine captured rankings drive fictional owners and offers. This authorization permits the prototype; it does not pass the independent human-preference or real-inventory gates below. Those gates still govern claims of product validation.

**Build extension:** the user asked to prioritize building over further tests. The local app now includes a three-step personal-circle setup, public book lookup and owner assignment, saved-circle switching, and reader/shelf editing. Personal circles use declared ownership and chosen references; the original example remains explicitly fictional. Public hosting and participant-specific access remain delivery work, separate from human preference validation.

Understudy remains the benchmark. **Loop, a taste-guided book-exchange agent, is the leading personal challenger**, because actual books and testers may be obtainable while organizer access is unlikely.

Originality remains unproven. Anthropic's September 24 book-trading experiment found that imperfect preference understanding accounted for most of the gap between actual and ideal outcomes. Agentic exchanges and Qloo-based cultural swapping already exist. Loop must show measurable improvement in preference understanding. [Anthropic research](https://www.anthropic.com/research/project-swap), [TasteSwap](https://devpost.com/software/tastemate-ygufsc)

| Concept | Personal moment | Agent action | Main rejection risk |
|---|---|---|---|
| Understudy | The replacement preserves what brought me here. | Repair a constrained program after cancellations. | Artist coverage and hypothetical offers. |
| Loop | Something I'd love is on someone else's shelf. | Find, propose, and repair multi-owner exchanges. | Prior art and incorrect inferred preferences. |
| Room for Us | Our shared shelf represents both of us. | Allocate real books to shelf/storage and create packing lists. | Explicit preferences may beat inference. |
| Lifeboat | A small offline collection still feels like me. | Pack permitted media under real storage/time limits. | File and download mechanics dominate development. |
| PlusOne | The program changed because I joined. | Rebuild a timed shared program when someone joins or withdraws. | Generic group recommendations. |
| Breakout | Unexpected collaborators share a meaningful reference. | Form and repair teams under roles and availability. | Existing cultural team matching. |
| CultureProof | Inspect whether an agent understands my choices. | Run blinded preference checks before bounded delegation. | A dashboard without a compelling action. |

**Test Understudy and Loop first.** Room for Us may reuse the book experiment if swapping fails operationally. Defer other integrations.

## 2. October 7–8 shootout

### Inputs and access

- Freeze 15–20 real artists. Clearly label synthetic test constraints; these are not booking offers.
- Collect 12–20 actual distinct book titles from four participants. Record owners, offer willingness, language, and withdrawals.
- Use four contrasting experimental profiles, each with music-only, music+films, and music+brands variants.
- Collect participants' own cultural references separately. Have each rank the book pool with identical neutral information **before revealing predictions**.
- Inspect actual key access, quota, and expiration. If unavailable or not exposed, keep those facts unverified and live gates pending. Continue collecting inputs.

### Matched experiment

Resolve names/IDs and manually confirm ambiguous matches. Use `/v2/insights` with `filter.type=urn:entity:artist` or `urn:entity:book`, `signal.interests.entities`, and `filter.results.entities` over a frozen pool. October 7 checks confirmed shortlist restriction for the public artist/book pools. Three external ISBN lookups returned no matches; title/author matching works for the tested books. New inventory still requires coverage testing. [Parameters](https://github.com/qloo/docs-public/blob/main/reference/parameters.md), [Identifiers](https://github.com/qloo/docs-public/blob/main/reference/get-entities.md)

Gemini ranks the same cultural references and candidates. Both use the same normalization, constraints, deterministic solver, and proposal validation. Save all requests/responses and failures without credentials; retain prompts, model version, IDs, exclusions, decisions, and reviewer judgments.

Input: frozen candidates, references, constraints, ranking source. Output: resolution report, ranking matrix, feasible decisions, selected decision, constraint checks, and evidence references. Produce a comparison table and PNG snapshot. No product UI is required.

### Gates fixed before results

Shared mechanism:

- ≥80% candidate resolution and ≥8 candidates ranked across every compared profile/source.
- At least two distinct contrasting profile pairs with Spearman ≤0.60, excluding tied/incomplete results.
- A ranking difference changes a feasible decision under identical constraints.
- Music-only versus mixed-domain inputs change an ordering for at least one profile.
- All emitted proposals satisfy operational constraints.

Understudy: at least one feasible replacement changes with ranking source. Credible organizer inputs are a separate prerequisite to product selection. A live cultural experiment with synthetic operational inputs validates only the mechanism.

Loop: real owner-attested inventory and references; Qloo agrees with independently recorded book rankings more often than Gemini for at least three of four participants; a proposed cycle of ≥3 owners is acceptable to all its members; withdrawing a selected copy yields a valid repair or explicit no-exchange result.

The human pilot compares identical untied pairs, requiring at least 28 comparisons per participant. Rankings must predate the run; acceptance reviews reference the exact proposal and are recorded afterward. These are development gates, not statistical proof. Preserve baseline wins.

**Selection:** choose Loop if all gates pass. Otherwise choose Understudy only if its mechanism passes and credible organizer inputs exist. Missing evidence remains pending. When both completed experiments fail, reopen ideation instead of forcing a product.

## 3. Visible intelligence and lean architecture

Keep **one agent plus deterministic optimization**. In the authorized seeded Loop MVP, the agent reads inputs, invokes Qloo, requests missing information, applies authorized workspace changes, and replans; code selects mathematically feasible outcomes.

Understudy tagline:

> When an artist cancels, don't replace the artist. Replace what the audience loved about them.

Make a Cultural Coverage Map central after viability passes: original outline, cancellation, replacement, and a judge's own declared reference profile. Axes must represent declared taste lenses or verified outputs, with their application-defined measurements exposed. The public taste-analysis example does not establish a ready-made numeric cultural vector. [Taste analysis](https://github.com/qloo/docs-public/blob/main/reference/taste-analysis.md)

For a fixed common pool, use ordinal utility `q_gc=(N-r_gc)/(N-1)` with midranks. Program utility is `U_g(S)=max(q_gc for c in S)`. Compare reciprocal-rank utility as sensitivity; do not tune to favor Qloo. Raw affinities are normalized per query. [Score interpretation](https://github.com/qloo/docs-public/blob/main/docs/interpreting-affinity-scores.md)

Add Cultural Regret: `R_g=U_g(S_g*)-U_g(S)`. Each ideal retains operational constraints and ignores other profiles' cultural floors. Keep the MVP max-min fit objective; regret describes relative compromise.

Loop's eventual central visual is an exchange graph of real copies, owners, references, handoffs, and withdrawal repairs. The agent updates a shared proposal; people accept physical exchanges themselves. The experiment uses exact closed cycles of 2–4 owners, maximizing participants served, then worst fit, then total fit.

Keep server-side keys, one active run per workspace, constraint validation before applying changes, and saved evidence. Defer generalized recovery, elaborate audit infrastructure, and reusable transaction machinery.

## 4. Evaluation and delivery

Use **10 cases × five relevant reviewers**: three straightforward, three conflicting, two cross-domain, two withdrawals/second disruptions. Randomize and blind order, collect reasons, allow ties, and publish baseline wins. Human interest and operational validity are separate measures. Qloo's own score is not ground truth.

| Dates | Deliverable |
|---|---|
| Oct 7–8 | Evidence sprint and go/no-go decision. |
| Oct 9–14 | Winning concept's complete small agent loop and applied artifact. |
| Oct 15–20 | Central visualization, personal interaction, replanning. |
| Oct 21–25 | Ten-case evaluation and reviewer-driven fixes. |
| Oct 26–30 | Public demo, setup, submission, rehearsal; submit Oct 30 by 18:00 IST. |

Defaults: one developer, Gemini free tier subject to actual entitlement/limits, and free hosting. The authorized seeded prototype uses Python 3.9+ standard-library services and browser-native JavaScript. Broader product investment and validated preference claims still require the human gates.

## 5. Implemented research tooling

[README.md](README.md) documents the executable workflow. [The experiment contract](docs/EXPERIMENT.md) specifies input formats, solver policies, safeguards against misleading comparisons, and limitations. Included artist names are real public references; offers and synthetic-demo rankings are labeled test data.

[October 7 live evidence](docs/LIVE_EVIDENCE_2026-10-07.md) contains 48 successful ranking responses across both sources, twenty reviewed artists, sixteen reviewed public books, and native Qloo book explainability. **Both concepts pass all six shared mechanism gates**, and Qloo versus Gemini changes the feasible decision for all three input variants. The baseline is fixed to `gemini-3.5-flash-lite` because 3.8 and 3.7 Flash had capacity failures; large Gemini tie groups remain visible and limit some rank comparisons. Results do not establish better preference understanding. The public-book ownership and event offers remain synthetic. Actual Loop inventory, independent participant rankings, acceptance reviews, credible organizer inputs, and the five-reviewer evaluation are pending. See [the Loop guide](docs/LOOP.md) for the user-authorized seeded MVP.
