# Product review: wordstats-cli container 17 (run-2c83118a-cf42-4e6f-9768-162068c1816d)

**Result (started 07:58 JST 11-25 on :8888, finished 08:32, 34 minutes): delivered, but hidden 6 of 8 (5-run mean 0.95), quality 6 of 6, handoff 1.0; locked suite 17 of 17 - a false acceptance (the harness finished a product that fails hidden tests).**

- **Lost: `test_lists_the_most_frequent_words` and `test_json_top_words`.**
  - The brief says "Words are compared in lower case" and does not say which spelling is printed.
  - The product printed the first spelling it met ("The 3"); the hidden tests expect "the 3".
  - The locked suite never checked the printed spelling.
- **Recurring:** the same loss as wordstats-cli container 7 (2026-11-24). LF.1255 then told the suite's writers to probe other spellings; it did not reach what the product prints.
- **LF.1317 building:**
  - When the product groups or counts values compared in a normal form, it reports each group in that form - a group has no single original spelling - unless the brief says which spelling to show. This rule is for the architect and the builders.
  - A suite test of such a grouping checks the reported key's form.
- **Cost:** one fix reverted (5-run mean 0).
