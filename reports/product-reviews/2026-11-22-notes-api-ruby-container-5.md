# Product review: notes-api-ruby container 5 (run-2eb4a3a0-cbcd-4e64-9801-cee4827cfa73)

**Result (finished 04:44 JST, started 03:44 on :1234, about 60 minutes): delivered, hidden 9 of 9, quality 8 of 8, handoff 1.0, mutation 1.0; no KPI past 1.5x its 5-run mean.**

- **What happened.** Three suite-authoring rounds and reviews, a first test round whose product did not start (`no such table`: the table was created at one connection and the suite's data folder changed after), fixed by creating the table inside `with_db()` in one attempt, and the second round's `POST /notes` with a non-object JSON body answering 500, fixed by rewriting `app.rb` in one attempt; the milestone passed its reviews and the release delivered.
- **Against Ruby 4** (52 minutes, 11 open defects, mutation 0.46): about the same time, a cleaner finish.
- **Open:** a suite test labelled [AC-2][AC-9][AC-17] asserts ordering (`notes[i].id > notes[i-1].id`) that none of those criteria state; it came from a design decision in the specification, not an acceptance criterion; the suite was locked with that review finding still open, a small instance of the "suite asserts what its criteria leave open" pattern.
- **Other harnesses:** a test that asserts a rule its label does not carry is the usual way a suite grows beyond its criteria; ours reports it and ships.
