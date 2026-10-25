"""A naming standard per language, stated once in the specification and again in every draft's request (behind `NAMING_STANDARD`).

Measured over one night with a small model: seven test files imported `createApp` from a module that exported `app`;
a router imported `create_access_token` from a module that defined `create_token`. The specification already had the
sections that fix names (a file plan with each export, function contracts, data contracts), but a section came back
"Not specified" and nothing told the writers that one concept is one name. Two things follow: one standard that every
writer reads in the same words, and, as the compiler finds a name that does not exist, the names that do
(`app.analysis.language_service.the_names_the_module_has`). Off, the requests are as they were.
"""
from __future__ import annotations

from typing import Any

from app.switches import is_on

#: Off in code like every switch; the compose file turns it on.
ON_BY_DEFAULT = False


def enabled() -> bool:
    return is_on("NAMING_STANDARD", ON_BY_DEFAULT)


#: How each language spells what it names; a table, as the per-language knowledge in this harness is.
CONVENTIONS = {
    "python": "Python: modules, functions, methods and variables in snake_case; classes in PascalCase; "
              "constants in UPPER_SNAKE_CASE; a file's name is the name it is imported by.",
    "typescript": "TypeScript: functions, methods and variables in camelCase; classes, types, interfaces and "
                  "components in PascalCase; constants in UPPER_SNAKE_CASE; one style for file names throughout.",
    "javascript": "JavaScript: functions, methods and variables in camelCase; classes and components in "
                  "PascalCase; constants in UPPER_SNAKE_CASE; one style for file names throughout.",
    "go": "Go: exported names in PascalCase, unexported in camelCase; package names short, lower case, one word.",
    "rust": "Rust: functions, modules and variables in snake_case; types and traits in PascalCase; "
            "constants in UPPER_SNAKE_CASE.",
    "java": "Java: methods and variables in camelCase; classes and interfaces in PascalCase; constants in UPPER_SNAKE_CASE.",
    "kotlin": "Kotlin: functions and variables in camelCase; classes in PascalCase; constants in UPPER_SNAKE_CASE.",
    "csharp": "C#: types, methods and properties in PascalCase; locals and parameters in camelCase.",
    "ruby": "Ruby: methods, variables and files in snake_case; classes and modules in PascalCase.",
    "php": "PHP: classes in PascalCase; methods and variables in camelCase; constants in UPPER_SNAKE_CASE.",
}

#: What holds in every language: one concept, one name.
ONE_NAME = (
    "One concept has one name everywhere: a function, class, field, route, command, environment variable or element "
    "id is spelled the same in the specification, in its own file, in every file that imports or tests it. A name "
    "another file already defines is imported as it is defined, never renamed, pluralised or abbreviated; a name "
    "that is needed and not defined yet is defined in the file the specification gives it."
)


def standard_for(stack: Any) -> str:
    """The naming standard for a stack, as one short block; "" when off or the language is not known."""
    if not enabled():
        return ""
    try:
        from app.stacks import _languages

        languages = sorted(_languages(stack))
    except Exception:  # noqa: BLE001 - the request goes out without it
        return ""
    rules = [CONVENTIONS[name] for name in languages if name in CONVENTIONS]
    if not rules:
        return ""
    return "--- Naming ---\n" + "\n".join(rules) + "\n" + ONE_NAME


__all__ = ["CONVENTIONS", "ONE_NAME", "enabled", "standard_for"]
