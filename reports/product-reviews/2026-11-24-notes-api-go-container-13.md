# Product review: notes-api-go container 13 (run-127780fe-5fa4-4e72-b7ef-c18d804d5dd3)

**Result (started 09:04 JST 11-24 on :1234, finished 10:55, about 111 minutes): not deliverable, hidden 9 of 9, quality 7 of 8, handoff 0.86, mutation 0.80.**

- **Why not deliverable:** the suite was locked "with this still open: This repair was sent for `[AC-7]` ... and has not changed it". A false finding of the harness's own check (`typeof n.title === 'string'` read as a title equal to "string"; fixed by LF.1256 at 09:42) reopened a right suite, and the repair rule kept sending the unchanged test back until the repair budget ran out (about 80 minutes of acceptance-author passes). LF.1267 (a repair whose finding no longer holds is settled) is built, not yet deployed.
- **Lost quality test:** notes created at the same moment are not all kept. The concurrent-write probe caught exactly this ("16 creates at once"), raised it three times, and the fixers did not close it.
- **What worked:** every release probe reached its writes (server error 12, bad body 2, wrong shape 2, concurrent write 1, round trip 2, emptied field 4).
