# The Hub — planning docs

Start here if this is your first time in this folder.

## Read in this order

1. **[the-hub-glossary.md](./the-hub-glossary.md)** — plain-English definitions
   of every tool and term used in the other docs (Docker, Prisma, presigned
   URLs, queues, JWTs, etc.). Start here if you're not already familiar with
   this stack.
2. **[the-hub-implementation-plan.md](./the-hub-implementation-plan.md)** — the
   source of truth: product vision, requirements, the data model, the API
   design, and the architecture. Read this fully before writing code.
3. **[the-hub-engineering-checklist.md](./the-hub-engineering-checklist.md)** —
   the same roadmap as 13 milestones, each with a checklist and a "definition of
   done." Good for tracking day-to-day progress.
4. **[the-hub-sprint-breakdown.md](./the-hub-sprint-breakdown.md)** — the same
   roadmap again, regrouped into 12 time-boxed sprints. Use this instead of the
   checklist if you're planning work in sprints.

Documents 2–4 describe the *same* plan at three levels of granularity — pick
whichever matches how your team likes to track work. If any of them ever
disagree, the implementation plan (#2) is correct.

## About the `.docx` files in this folder

`Basic Product info.docx` and `Detailed viability and product info.docx` are the
original source documents this plan was built from (a product/technical spec and
a market-viability writeup). Their useful content — the data model, API
examples, code samples, tech-choice rationale, and competitive analysis — has
been merged into the four `.md` files above, with terminology reconciled where
the two source docs disagreed with each other (e.g. two different lists of
thread statuses, two different sets of user roles). The `.md` files are what you
should actually build from; the `.docx` files are kept for background/history
only.
