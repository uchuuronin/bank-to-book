# How this was built with AI

I built this with Claude as the engineering partner throughout — design, code, and the
diagnostic work that drove the design. This is an honest account of where that helped,
where it led me wrong, and how I caught it. The short version: AI was fastest and most
useful when I made it interrogate the data before writing code, and most dangerous when it
produced confident, plausible output that didn't survive a look at the actual numbers.

## The workflow, not just the prompts

The pattern that worked was diagnose-before-build. Before writing the matcher I had it
write throwaway scripts to profile the real BenchRec data — what the columns are, how rows
split into ledger and statement sides, what the allocation label looks like, whether
reference text actually joins the two sides. Those are the scripts now living in
`matching/diagnostics/`. They exist because every time I was tempted to design against an
assumption, the more useful move was to make the model check the assumption against the
data first. Several of them killed an idea I was about to build.

The prompts that mattered were rarely "write me X." They were "before we build X, what does
the data actually say about the assumption X depends on?" That reframing is most of why the
final design is what it is.

## Where AI led me astray, and how I caught it

These are the moments worth reporting, because they're where judgment had to override the
model's confident output.

**The matcher's first design assumed reference text joins the two sides.** It seemed
obvious — match transactions by their reference codes. The diagnostic script said otherwise:
for about three-quarters of true matches, the bank reference and the ledger reference share
nothing. The model had produced a reasonable-sounding plan built on a false premise. Reading
the real rows is what overturned it. The whole architecture changed as a result — amount,
date and sign became the join, with reference codes as corroboration rather than the key.

**Three hypotheses for the matcher's errors, two of them wrong.** When the scored tier was
making mistakes, the model proposed plausible explanations: the errors lack reference-token
support; the errors come from candidate competition. Both sounded right. Both were wrong
when measured — the errors turned out to be irreducible coincidental twins, transactions
genuinely indistinguishable in the data. The lesson I kept relearning: a plausible
explanation from the model is a hypothesis to test, not a finding. The right response to
those was not to "fix" them but to band them amber and route them to a human, which is what
the tool does.

**The LLM briefing tier, version one: confident filler.** I first had the model write a
short explanation for each review-queue row. Run on real data, it produced the same sentence
fifty times — "possible match on amount and date, no reference code" — dressed up as
insight. It wasn't lying, exactly; it was restating the band definition because the per-row
signal is genuinely identical across rows. I cut it. The replacement (see below) computes
the interesting facts in code and lets the model only phrase them. This was the single
biggest correction in the project, and it came from reading the output and refusing to ship
something that looked useful but said nothing.

**The duplicate detector, over-firing.** Once the briefing computed real findings, the
duplicate detector reported "441 lines in 123 groups." That's the kind of confident,
specific-sounding number that's worse than vague filler, because a reviewer would chase it.
Reading the underlying rows showed why it was wrong: it keyed on amount + date + account,
and on a single busy feed day with 640 lines in one account, exact-amount collisions are
ordinary, not suspicious. I tightened it to require a shared distinctive reference code —
the same identity signal the matcher already trusts — and the finding collapsed to 5 lines
in 2 genuine groups. The fix was consistency, not cleverness: make the detector obey the
rule the rest of the system already used.

**The recurring-reference detector, same mistake in a different place.** It surfaced a word
("Volery") that recurred on 941 of 954 rows and called it a counterparty worth batching. But
a token on almost every row identifies nothing — it's boilerplate, like a bank's standing
text. Same fix as the duplicates: rank recurring tokens by rarity using the existing IDF
model, so a distinctive code that recurs wins and ubiquitous boilerplate is rejected. Two
detectors, one lesson, applied consistently.

There's a pattern across all of these: the model is good at producing something plausible
and bad at knowing whether it's true. The value I added was insisting on measurement, and
cutting things that looked good but didn't hold up — including a round-number detector I
removed entirely once I saw it was reporting trivia against a billion-scale queue.

## Using research to make a real decision

When the briefing was still weak, instead of guessing at prompt tweaks I had the model run a
deep research pass on the actual question: how do you get a small local model to produce
grounded, specific output over aggregate data? The finding reshaped the design — the problem
wasn't phrasing, it was content selection, and the production pattern (Power BI, Arria, and
others) is to compute the insight deterministically and let the model only render it. That's
exactly the split the briefing tier now uses: `insights.py` decides what's worth saying in
code, the model phrases it, and a schema with no numeric field means it can't fabricate a
number into the ledger. Knowing when to do the analysis in code rather than ask the model to
do it is the main thing that research changed.

## What I'd tell someone using AI on the same brief

Make it look at the data before it writes code. Treat every confident explanation as a
hypothesis, not an answer. Read the real output, not just the summary stats — the duplicate
and Volery problems were both invisible in the headline numbers and obvious the moment I
looked at rows. And be willing to cut things the model produced, even good-looking ones,
when they don't survive scrutiny. The model is a fast, tireless collaborator with no
instinct for whether it's right. That instinct is the part that was mine to bring.
