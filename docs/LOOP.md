# Loop MVP

Loop organizes reading circles of four people with 8–20 distinct offered book works. Create a circle, choose readers' references, search and confirm books, and declare the owner and language of each copy. Its central artifact is a saved exchange proposal: closed handoffs where every involved owner gives one available copy and receives one permitted book. A sixteen-title example circle is included. The screen is built with HTML, CSS, SVG, and JavaScript; Python's standard library serves the app and calls the APIs. Runtime dependencies: Python 3.9+ and a modern browser.

## Run locally

From the repository root:

```sh
python3 -m loop_app
```

Open http://127.0.0.1:8000. Options: `--host`, `--port`, and `--workspace`. The default workspace is `local/loop-workspace/`; one process owns its lock, and one action runs at a time. Stop the server with Ctrl+C. The server binds to localhost by default. Hosted organizer access uses a password; readers receive private links scoped to their own offers, references, and proposed handoffs. [Hosted setup and storage](DEPLOYMENT.md).

The original twelve Qloo profiles and matching Gemini comparisons are bundled in `loop_app/data/rankings.json`. These are successful responses captured in the October 7 evidence sprint, not invented rankings. The app starts with music-only references and can switch to music + films or music + brands from the saved evidence without making requests.

For live features, set `QLOO_API_KEY` and `GEMINI_API_KEY` in the server's environment using the hidden prompts in [README.md](../README.md). Qloo is restricted to https://hackathon.api.qloo.com. The app's default model is `gemini-3.5-flash-lite`; override it explicitly with `GEMINI_MODEL`. Keys are not stored in source files or browser assets. The app does not load `.env` files.

## Try the complete loop

Click **Start your own circle** to enter the three-step setup. Name the four readers, select their public favorites, and add 8–20 distinct books. Search matches show disambiguation; every copy needs an owner, author, and reading language. Each reader must offer at least one copy. Confirm the chosen references and offered inventory before creating the circle. New pools/reference combinations require live Qloo access; matching saved evidence can be reused. An unsuccessful creation preserves the setup draft in the current browser session and retains the previously active circle.

Click the circle name to open **Your circles**. Switch between saved circles, start another, or choose **Edit this circle** to change reader details and books. Editing preserves withdrawn copies and reading/declined-title restrictions for copies that remain on the shelf, then replans for a fresh review. Returning to the demo retains personal circles in the library.

1. **Find a loop:** ranks the fixed pool using saved evidence, solves the constrained exchange, validates every handoff, and saves the proposal.
2. **Explore taste:** click a reader. Choose demo presets or search public artists, films, brands, or books. Select the intended entity explicitly. Save to replan. New reference combinations use live Qloo Insights; returning to a cached combination reuses its evidence.
3. **Set actual restrictions:** exclude already-read titles or change reading language. These are hard constraints, separate from estimated cultural relevance.
4. **Review incoming books:** **Invite readers** creates one private review link per reader. Readers can accept, pass and automatically replan, edit their own references, and withdraw/restore their own offered copies. Organizer controls can also record acceptance, labeled separately. The example circle labels reviews simulated. Passing excludes that incoming title for that reader on the next plan; the organizer's reader profile allows reconsidering a passed-on title. Replanning clears approvals so everyone reviews the new proposal.
5. **Withdraw a selected copy:** the shelf and shared proposal update together. The graph shows removed handoffs as dashed arrows and new handoffs as solid arrows. Restore a copy from its shelf button.
6. **Inspect evidence:** the Qloo status control opens per-reader rankings and any matching saved Gemini ordering. Adjust the minimum relative rank fit or refresh all four Qloo queries. A stricter constraint may produce an explicit no-exchange result.
7. **Ask the agent:** try “Find a loop”, “Explain this exchange”, or “Please withdraw Beloved”. Gemini uses native function calls, receives the actual tool result, and explains it. The named copy and availability-change intent are checked before mutation. Without the model key, these guided commands remain usable.
8. **Download exchange:** exports the exact current proposal, copy inventory, reader details, reviews, ranking evidence, input hash, and workspace revision. **Back up circles** downloads all saved circles and live evidence, excluding private invitation tokens.

Owners, offers, and biographies in the included example are fictional. Personal-circle ownership and references are user declarations. The sixteen included book works and their confirmed Qloo IDs are real; new search results remain a user's disambiguation choice. The geometric covers are illustrative designs. Physical exchanges require actual participants' agreement. Acceptance in this shared workspace does not independently verify the participant's identity.

## Architecture and evidence

`loop_app/agent.py` is the single Gemini agent. Its four tools plan, withdraw, restore, or explain an exchange. Stateful edits from the interface use the same workspace actions directly. `loop_app/core.py` handles references, cached/live rankings, validation, proposals, reviews, and persistence. `shootout/solver.py` performs exact small-pool optimization shared with the research baseline. No separate matching agents or model-generated optimization results are used.

The solver enumerates feasible closed cycles of two to four owners and chooses disjoint cycles. Its priorities are: maximize readers served, maximize their weakest relative rank fit, then maximize total fit. A fixed ordering of handoffs breaks remaining ties. Availability, offers, ownership, language, read history, explicit declined titles, and minimum fit are checked again before applying the result.

For a common comparison pool of size N, rank utility is `(N - rank) / (N - 1)`, with midranks for ties. This is a relative index, not a probability of individual enjoyment. Raw affinities are not combined across requests. The UI exposes references and returned orderings; it does not invent a causal explanation for a ranking or claim access to hidden taste coordinates.

Qloo receives confirmed public entity IDs and the active candidate IDs through Search and constrained Insights. Ownership, language restrictions, reading history, participant names, and raw chat are excluded from Qloo requests. Gemini receives anonymous reader labels, public book information, declared public references, the user request, and actual tool results.

The server keeps the last applied workspace intact when a query or validation fails. Request/response evidence, including provider failures, is saved with credential redaction. Native Gemini function-call continuation replays the returned model steps and the corresponding tool result with `store: false`. A failed explanation after a successful tool action falls back to the actual handoffs and labels that fallback.

Workspace files, excluded from source control:

- `local/loop-workspace/state.json`: shelf, references, restrictions, proposal, reviews, messages, and tool traces.
- `local/loop-workspace/circles/`: individual saved circles, including the example.
- `local/loop-workspace/proposal.json`: current downloadable review artifact.
- `local/loop-workspace/live-rankings.json`: saved fresh Qloo responses indexed by candidate/reference IDs.
- `local/loop-workspace/evidence/requests.jsonl`: credential-redacted live requests, responses, and failures.

The HTTP interface serves only allowlisted public assets and explicit API endpoints. Hosted organizer APIs require a signed HttpOnly login cookie; mutations also require a process-specific CSRF token and a matching Origin when supplied. Separate reader APIs require a private bearer link token and enforce reader ownership. Workspace revisions reject stale actions; proposal IDs reject stale approvals. Private links are saved separately from proposal evidence, and the server uses a no-referrer policy. Optional Postgres storage keeps the hosted workspace durable across restarts.

## Verification and remaining validation

```sh
python3 -m unittest discover -s tests -v
```

The suite covers exact solver validity, withdrawal/restore repair, language and reading constraints, rejected-title exclusion, persistence, stale writes/reviews, insufficient API coverage, native Gemini tool history, and HTTP request boundaries. Browser verification exercises the desktop and mobile controls, captures screenshots, and checks for page errors. See `artifacts/loop/browser-check.json` for the recorded interaction checks.

The mechanism experiment demonstrates that cultural inputs and ranking sources change feasible decisions. It does not establish that those decisions suit actual people. Owner-attested inventory, independently recorded participant preferences, accepted multi-owner exchanges, and blinded reviewer evaluation remain pending under [PLAN.md](../PLAN.md).
