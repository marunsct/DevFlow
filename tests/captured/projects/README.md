# Captured projects

Source files of products the harness built, copied verbatim from stored workspaces of notes-api runs and one word-statistics run (2026-11), for
the code graph's tests (KG.2, KG.3): each folder is one product's files in one language, kept to the files its edges need.

| Folder | Language | What its imports show |
|---|---|---|
| `go-notes-api` | Go | `notes-api/store` under the module `go.mod` declares |
| `java-notes-api` | Java | packages per folder, a controller importing a service importing a repository |
| `csharp-notes-api` | C# | top-level `Program.cs` with `using` of two declared namespaces |
| `rust-notes-api` | Rust | `mod` in `lib.rs`, `use crate::...`, and `main.rs` calling the crate by its name |
| `ruby-notes-api` | Ruby | `require_relative` from the app, the library and its modules |
| `php-notes-api` | PHP | `use` of classes under the `psr-4` prefix of `composer.json`, and a fully qualified name |
| `typescript-notes-api` | TypeScript | routes calling the store and the validation by name (KG.3) |
| `python-wordstats` | Python | a command line calling its analyser through `from wordstats import analyzer` (KG.3) |
| `kotlin-notes-api` | Kotlin | **not captured**: no Kotlin product exists in any stored workspace, so this is `java-notes-api`'s model, repository and service written in Kotlin, with one wildcard import |
| `react-to-do-list-app` | TypeScript (React) | a page product: components rendering the labels and names its acceptance suite selects (KG.4), and unit tests importing them |
| `browser-to-do-list-app` | JavaScript (no framework) | a page product whose markup renders the form's labels and loads its script; the suite selects controls by label and name (KG.4) |

When a Kotlin run is stored, replace `kotlin-notes-api` with its files.

`../project-tests/<folder>/` holds, for five of these products, the acceptance suite and some unit tests the same run stored (KG.4); a test lays them over the product, so the import edges above stay as they are.
