# Product review: notes-api-csharp container 15 (run-244ac383-dab4-4d43-967c-80074e014878)

**Result (started 23:28 JST 11-23 on :8888, finished 00:46 JST 11-24, about 78 minutes; mixed versions): delivered, hidden 9 of 9, quality 8 of 8, handoff 1.0, mutation 1.0.** KPI regression: identical calls 5.5% (5-run mean 2.1%).

- **What happened.** The first attempt drafted the project files with `Microsoft.EntityFrameworkCore.Sqlite` 11.0.0 on net8.0 - offered by the NuGet lookup, which read only the six newest releases (all for .NET 10 and 11) and fell back to the newest - and every restore failed NU1202; a web lookup and two rewrites did not change it; a fixer pinned 8.0.0 at 00:12 JST. After a re-plan the second attempt closed three defects in six minutes (the database never created at start, updates lost to no-tracking loads, JSON options set on the MVC type minimal APIs ignore) and delivered.
- **Fixes from this run:** LF.1248 (the lookup reaches the older major line this SDK runs; the C# pack names NU1202's cause), deployed 00:18 JST.
- **Gaps noted:** four contract lines not checked at release (writes that need a body the probe does not send).
