# Captured projects

Source files of products the harness built, copied verbatim from stored workspaces of notes-api runs (2026-11), for
the code graph's tests (KG.2): each folder is one product's files in one language, kept to the files its edges need.

| Folder | Language | What its imports show |
|---|---|---|
| `go-notes-api` | Go | `notes-api/store` under the module `go.mod` declares |
| `java-notes-api` | Java | packages per folder, a controller importing a service importing a repository |
| `csharp-notes-api` | C# | top-level `Program.cs` with `using` of two declared namespaces |
| `rust-notes-api` | Rust | `mod` in `lib.rs`, `use crate::...`, and `main.rs` calling the crate by its name |
| `ruby-notes-api` | Ruby | `require_relative` from the app, the library and its modules |
| `php-notes-api` | PHP | `use` of classes under the `psr-4` prefix of `composer.json`, and a fully qualified name |
| `kotlin-notes-api` | Kotlin | **not captured**: no Kotlin product exists in any stored workspace, so this is `java-notes-api`'s model, repository and service written in Kotlin, with one wildcard import |

When a Kotlin run is stored, replace `kotlin-notes-api` with its files.
