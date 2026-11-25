# Product review: L notes-api-php container 8 (run-f4bab632-fed8-4deb-a72b-997a7474e875)

**Result: delivered with cuts - hidden 9 of 9, quality 8 of 8, handoff 1.0; locked suite 10 of 10.** Started 09:3x JST 11-25 on
the old :8888, paused 10:04-02:00 JST (owner: :8888 held, then the inference engine change), resumed on the olla endpoint
(parallel mode, at most two runs); finished 02:34 JST 11-26. Mixed versions (several deploys while paused).

- **What happened after the resume:** two fix rounds with fixers side by side (parallel mode): `rowCount()` for
  UPDATE/DELETE fixed, AC-13/18 and AC-16 closed on the next measurement, AC-1/AC-8 moved forward. At 02:32 JST the third
  attempt ended with every due acceptance test passing and only a unit test failing; the sprint was accepted at the
  escalation with the unit test set aside (DR-17).
- **Lost:** nothing hidden or in quality.
- **Gaps the release recorded:** 23, most of them design-review contradictions settled or left open at the escalation, three
  criteria (AC-6, AC-15, AC-17) shipped unproven by the suite, and no code review read the product (accepted at an
  escalation - the PQ.4 review-after-escalation is built, not yet deployed).
- **Parallel mode:** fixer pairs overlapped with no write conflicts; one GPU served both for part of the time until the
  session header (LF.1407) spread conversations across instances.
