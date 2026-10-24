# Loop — Your next chapter is on someone else's shelf

## Inspiration

Most book exchanges assume a simple trade: I want your book, and you want mine. Real groups rarely work that neatly.

A reading circle may contain plenty of books people would enjoy, but no useful one-to-one swaps. Ava might want Noor's book, Noor might prefer Milo's, and Milo might want something from Ava. The right exchange is a loop.

That led to **Loop**, a taste-guided book-exchange agent built around one idea:

> **Your next chapter is on someone else's shelf.**

Qloo made the concept more interesting because reading taste does not exist in isolation. The music, films, brands, and books someone loves can provide cultural signals for discovering an unexpected next read.

## What it does

Loop helps a four-person reading circle turn its offered books into a valid multi-owner exchange.

Each participant contributes:

- The books they are willing to offer
- Their reading language and previously read titles
- Public cultural references they choose, such as artists, films, brands, or books
- Their response to a proposed incoming book

Loop then:

1. Resolves the selected cultural references and book works through Qloo.
2. Uses Qloo Insights to rank the same offered-book pool for each reader.
3. Finds closed exchange cycles involving two or more owners.
4. Validates ownership, availability, language, history, exclusions, and handoff balance.
5. Presents each reader with their proposed incoming and outgoing book.
6. Replans when someone passes or withdraws a copy.
7. Saves a reviewable exchange artifact with its ranking evidence and constraint checks.

A proposal remains provisional until every involved reader accepts it. Loop never claims that a cultural prediction is the reader's decision.

## Why Qloo matters

A generic language model can recommend famous books or explain why two works appear similar. Loop asks a harder and more useful question:

> Given these exact available copies, these owners, these restrictions, and these different cultural references, which valid exchange should this group make?

Loop uses Qloo's cross-domain taste graph to rank books from signals that may come from music, cinema, brands, or literature. Every ranking is restricted to the books actually offered in the circle.

For example, the application can use references such as Radiohead, Portishead, *Her*, *Mulholland Drive*, and Adidas to rank the same fixed shelf. Changing from music-only inputs to music-and-film inputs can change the ordering and therefore change the feasible exchange selected by the solver.

Qloo receives only public cultural entity IDs and candidate book IDs. Participant names, ownership, reviews, availability, and private links remain inside Loop.

## How we built it

Loop uses one Gemini agent with deterministic planning tools.

The agent can inspect the workspace, request Qloo rankings, withdraw or restore a copy, run the exchange solver, validate a proposal, apply it, and explain the result. Gemini orchestrates those actions, while deterministic code makes the final mathematical selection.

This separation matters. The language model interprets requests such as:

> “Please withdraw Beloved and find another exchange.”

It does not invent a replacement or decide whether the constraints were satisfied. The solver computes the feasible outcome, and the validator checks it before anything is saved.

The application is built with:

- Python for the web application, Qloo adapter, agent tools, and optimizer
- Qloo Search for resolving public cultural references and book works
- Qloo Insights for constrained, cross-domain ranking
- Gemini for natural-language tool orchestration and explanations
- PostgreSQL for durable hosted workspace storage
- Render for the public deployment
- A server-rendered interface with an exchange graph, reader pages, evidence tables, and downloadable artifacts

### Ranking utility

Raw affinity scores from separate Qloo requests should not automatically be treated as directly comparable probabilities. Loop therefore uses each reader's ordering within the same fixed book pool.

For reader $g$ and candidate book $c$, the default utility is:

$$
q_{gc}=\frac{N-r_{gc}}{N-1}
$$

where:

- $N$ is the number of commonly ranked candidate books
- $r_{gc}$ is the candidate's rank for that reader
- $q_{gc}=1$ represents the first-ranked book
- $q_{gc}=0$ represents the last-ranked book

The solver searches for closed cycles where every participant gives one available copy and receives one permitted copy. It prioritizes:

1. The number of readers served
2. The weakest reader fit
3. Total fit across the exchange

This keeps the optimization explainable and prevents one excellent recommendation from hiding a poor outcome for another participant.

## The product experience

The organizer sees the complete exchange graph and evidence behind the proposal. Solid arrows show the current handoffs, while dashed arrows show what changed after replanning.

Each reader receives a private page showing:

- Their proposed incoming book
- Who is offering it
- Which of their books would move onward
- The public references used for matching
- The book's relative Qloo rank
- Controls to accept, pass, or update their own offers and references

If a reader passes, that incoming copy is excluded for them and Loop searches again. If an offered book is withdrawn, the agent repairs the exchange or explicitly reports that no valid exchange exists.

## Challenges we faced

### Book identity and coverage

Titles can be ambiguous, editions differ, and external identifiers are not uniformly available. We addressed this by requiring explicit title-and-author confirmation, storing Qloo entity IDs, and keeping physical-copy information separate from the cultural work.

### Keeping the comparison fair

A recommendation system can look impressive simply because it saw different candidates. We froze the same offered-book pool and operational constraints for Qloo and the Gemini baseline. We also preserved ties, failures, resolved IDs, and evidence instead of selecting only favorable examples.

The current demonstration shows that ranking sources and cultural inputs can change valid exchange decisions. It does **not** yet prove that participants prefer Qloo's choices more often.

### Combining taste with hard constraints

The highest-ranked book may be unavailable, already read, in an unsupported language, owned by the recipient, or impossible to place inside a closed exchange. Cultural ranking alone cannot solve the problem.

We therefore separated preference ordering from operational optimization. Qloo supplies cultural relevance; the deterministic solver decides what can actually happen.

### Safe agent actions

An unconstrained agent changing shared inventory would be difficult to trust. Loop limits the agent to explicit tools, validates every proposed exchange before applying it, allows only one active workspace operation, and records the evidence behind each decision.

### Privacy

Qloo does not need participant identities to rank public cultural entities. Loop sends public reference and candidate IDs while retaining names, ownership, restrictions, reader responses, credentials, and invitation links on the application side.

## What we learned

We learned that cultural intelligence becomes more meaningful when it changes a constrained decision instead of producing another list of recommendations.

The most interesting result was not “Qloo suggested this book.” It was:

> “Because this reader's cultural inputs changed the ranking, a different set of books could move through the whole group.”

We also learned to distinguish three separate questions:

1. **Cultural relevance:** How does Qloo order these available books for the declared references?
2. **Operational validity:** Can the group perform the exchange without violating its constraints?
3. **Human acceptance:** Does each reader actually want the proposed book?

Qloo helps with the first question. Loop's optimizer handles the second. Only the readers can answer the third.

That distinction shaped the interface: evidence is visible, predictions are described as relative rankings, and every participant retains the final choice.

## Accomplishments we are proud of

- Built and deployed a complete organizer-to-reader workflow
- Ranked a fixed sixteen-book pool using real Qloo requests
- Supported cross-domain signals from music, films, brands, and books
- Created valid exchanges involving multiple owners
- Added automatic replanning after a pass or withdrawal
- Used a real Gemini tool call to withdraw a copy and repair the proposal
- Exposed Qloo and Gemini rankings side by side without hiding baseline wins or ties
- Kept credentials and personal operational data on the server
- Produced downloadable evidence for the applied exchange

## What is next

The next step is a real reading-circle pilot.

Participants will contribute actual offered copies and record their book preferences before seeing either system's predictions. We will compare blinded Qloo and Gemini proposals, allow ties, collect the reasons behind each choice, and measure operational acceptance separately from predicted taste.

Future versions could support larger circles, several copies of the same work, pickup locations, exchange deadlines, accessibility needs, and repeated exchanges that learn only from feedback participants explicitly choose to provide.

Loop's goal is not to automate someone's taste. It is to find possibilities hidden across several shelves—and let the people involved decide whether those possibilities become their next chapter.
