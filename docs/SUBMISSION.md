# Loop — Your next chapter is on someone else's shelf

**Draft submission copy.** The source and reproducible prototype are ready; add the published demo URL and your recorded video before submitting on Devpost. Actual participant evaluation remains pending.

## Problem and product

A reading circle can have good books to exchange without useful pairwise swaps. Loop combines its offered shelves, uses public cultural references to rank the available book works, and proposes closed handoffs involving two to four owners. When someone passes on a book or withdraws their offered copy, the agent repairs the shared proposal within the same constraints. Each reader can review their own incoming book through a private link; physical exchanges require their acceptance and coordination.

One Gemini agent invokes planning, withdrawal, restoration, and explanation tools. Exact deterministic optimization selects feasible cycles, validates every handoff, and saves the applied workspace artifact. The app shows an exchange graph, each person's incoming book and references, Qloo rank evidence, and changes after a disruption.

## Qloo capabilities used

The app invokes the documented Qloo REST endpoints directly from Python rather than through the harness. It uses the same underlying capabilities as entity discovery and constrained insights workflows. No harness chat, plan, or build mode is used.

| Capability | Use in Loop |
|---|---|
| `/search` with `types=urn:entity:artist/movie/brand/book` | Find public references and book works; users confirm the intended result, author, and disambiguation. |
| `/v2/insights`, `filter.type=urn:entity:book` | Rank book works for public cultural inputs. |
| `signal.interests.entities` | Supply only confirmed public reference IDs; music, films, brands, or books may guide a book ranking. |
| `filter.results.entities` | Keep each query restricted to the same actual offered-title pool, rather than recommending unavailable books. |
| Returned order, scores, and evidence | Preserve actual responses and failures. Convert ordering to a relative rank utility; do not combine raw affinity scores across requests. |

Owner names, ownership, availability, language restrictions, reading history, and reviews stay in the application and are excluded from Qloo requests. Gemini receives anonymous reader codes and public cultural information for tool orchestration. Both credentials stay on the server.

See [Qloo's Insights parameter documentation](https://github.com/qloo/docs-public/blob/main/reference/parameters.md) and the concrete adapter in [shootout/clients.py](../shootout/clients.py).

## Redacted request → result → action

The reproducible evidence extract in [evidence/loop-request.json](evidence/loop-request.json) contains an actual captured request with authentication removed, a selected returned result, and the applied handoffs. All book/reference IDs are public entity IDs. Ownership in this example is fictional and is not sent to Qloo.

The music-only example uses Radiohead and Portishead for P1. Every profile ranks the same sixteen confirmed book works. Qloo's ordering for this example places **The Great Gatsby** first and **The Remains of the Day** second. The solver accounts for the other owners' interests and offered copies before selecting the closed four-owner proposal.

| Recipient | Qloo-selected incoming book | Gemini-selected incoming book |
|---|---|---|
| P1 | The Great Gatsby | Never Let Me Go |
| P2 | The Dispossessed | Beloved |
| P3 | The Stranger | The Dispossessed |
| P4 | Beloved | The Handmaid's Tale |

These are different valid decisions under the same synthetic operating conditions. They do not establish a preference win. The included baseline is Gemini 3.5 Flash-Lite; stronger Flash models were unavailable during capture. Ties are retained as midranks. [Captured findings and limitations](LIVE_EVIDENCE_2026-10-07.md).

## Demo and setup

- [Organizer screenshot](assets/organizer-desktop.png), [reader screenshot](assets/reader-desktop.png), [mobile reader](assets/reader-mobile.png).
- [Three-minute demo script](DEMO.md).
- [Source repository](https://github.com/sneaxhuh/loop).
- Clean local run: clone the repository, install Python 3.9+, run `python3 -m loop_app`, and open `http://127.0.0.1:8000`. The included saved profiles need no credentials.
- Live public-entity search and new rankings require a Qloo hackathon key. Gemini chat requires a Gemini key. Set them using the hidden prompts in [README.md](../README.md); do not enter keys in the app.
- Free hosted setup, secret configuration, and durable storage: [deployment guide](DEPLOYMENT.md). New participants need four readers and 8–20 distinct confirmed book works.

## Known limitations

The included offers and owners are fictional. Real-circle ownership and references are user declarations. Human preference agreement, real accepted exchanges, and the ten-case blinded evaluation are still pending. Qloo describes aggregate cultural patterns; a rank is not an individual satisfaction prediction. Loop makes no claim that Qloo outperforms Gemini on participants' choices.

The pilot handles four readers and one offered copy per distinct book work. Language metadata is owner-declared; a Qloo work match does not verify a physical edition. Three external ISBN probes returned no results, so the app relies on explicit title/author matching. A private reader link grants its holder that reader's role; it does not independently verify identity. The organizer may record reviews, labeled separately from reader-link reviews.

The host uses one process and one active run per workspace. Live requests are bounded; failures preserve the last applied proposal. Free Render web services sleep when idle. The free Postgres instance expires after thirty days; download a workspace backup before expiration. Credentials, private links, and real inventory do not belong in a public submission.

This draft follows [the hackathon kit's submission requirements](https://github.com/qloo/qloo-hackathon-kit/blob/main/docs/SUBMISSION.md). Add the actual demo video and human pilot evidence when available; do not invent acceptance or evaluation results.
