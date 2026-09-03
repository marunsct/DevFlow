# Step 1.1 Configuration Explained

This document explains `src/app/config.py` for a beginner. The file does not run an AI model yet. It only collects settings, converts text into useful Python values, and rejects unsafe or incomplete configuration before later workflow code starts.

## The Main Idea

Operating systems provide configuration as text values called environment variables. For example:

```text
OPENAI_MODEL=qwen/qwen3.8-27b
WORKFLOW_REQUIRE_APPROVAL=true
```

Python receives both values as strings. The application needs to convert the second value into the Boolean value `True` and validate that the first value is not empty.

Keeping this work in one module gives the rest of the application a simple rule:

```python
settings = load_settings()
```

Later code can use `settings.model_name` without knowing where the value came from or how it was validated.

## Imports

```python
import os
```

`os` is part of Python’s standard library. It lets the program read values supplied by the operating system, including `os.environ`.

```python
from dataclasses import dataclass
```

`dataclass` is a Python helper for classes whose main purpose is storing related values. It automatically creates useful methods such as an initializer, so we can construct `Settings(...)` without writing that initializer manually.

```python
from typing import Mapping
```

`Mapping[str, str]` is a type hint. It says the function accepts a dictionary-like object whose keys and values are strings. Using a general mapping makes the function work with `os.environ` and with small dictionaries used in tests.

```python
from dotenv import load_dotenv
```

`python-dotenv` reads a local `.env` file and places its values into the process environment. The real `.env` remains untracked; only `.env.example` is safe to share.

## The Configuration Error

```python
class ConfigurationError(ValueError):
```

This creates a named error type. It inherits from Python’s `ValueError`, which means the problem is an invalid value supplied by the user or environment, not a failed network request.

Giving the error a name lets callers distinguish configuration problems and show a useful message.

## The Settings Dataclass

```python
@dataclass(frozen=True)
class Settings:
```

The `@dataclass` line is called a decorator. It asks Python to generate storage-related methods for the class. `frozen=True` makes each settings object read-only after creation. Read-only configuration is safer because one workflow stage cannot silently change settings used by another stage.

Each field has a name and a type:

- `str` means text.
- `bool` means `True` or `False`.
- `str | None` means either text or the special value `None`, which means “no value”.

The type hints help beginners, editors, and static analyzers understand expected values. They do not by themselves validate input, which is why `load_settings()` still performs explicit checks.

## Reading Boolean Values

The `_read_bool()` function accepts a mapping, a variable name, and a default value.

```python
raw_value = environment.get(name)
```

`.get()` looks up the setting. If the key does not exist, it returns `None` instead of raising an error.

```python
if raw_value is None:
    return default
```

This is the fallback path. A missing optional setting uses a safe default.

```python
normalized_value = raw_value.strip().lower()
```

`.strip()` removes accidental spaces. `.lower()` makes `TRUE`, `True`, and `true` behave the same way.

The function accepts common human forms such as `true`, `yes`, `on`, and `1`. It accepts `false`, `no`, `off`, and `0` as false. Any other value raises `ConfigurationError` instead of silently guessing.

## Loading Settings

```python
def load_settings(environment: Mapping[str, str] | None = None) -> Settings:
```

The function returns a `Settings` object. The optional `environment` argument is important for testing:

- Normal application code calls `load_settings()` and reads the real environment.
- Tests call `load_settings({"OPENAI_MODEL": "test-model"})` and avoid changing the machine environment.

When no mapping is supplied, `load_dotenv()` loads `.env` and `os.environ` becomes the source of values. When a mapping is supplied, the function uses that mapping directly and does not load `.env`, keeping tests isolated.

## Required Model Validation

```python
model_name = values.get("OPENAI_MODEL", "").strip()
```

If the setting is missing, the empty string is used. This gives the function one value to validate.

```python
if not model_name or model_name.startswith("replace-with-"):
```

This rejects both an empty model name and the placeholder from `.env.example`. The application should fail early rather than make a confusing provider request with an invalid model.

## Returning Trusted Configuration

After validation, `Settings(...)` is created. Defaults are used for local development, including LM Studio’s endpoint and placeholder key. The LangSmith API key is optional and is represented as `None` when absent.

The function never prints secret values. It returns them only to the application component that needs them.

## Why This Is The First Step

The later agents will need a model, artifact directory, approval policy, and tracing settings. If each agent reads environment variables independently, they can disagree about defaults or accidentally bypass validation. Step 1.1 creates one trusted source of configuration before we build state, tools, agents, or graph routing.

## What The Validation Proves

The Step 1.1 validation checks that:

1. Dependencies install successfully.
2. Python can compile the source.
3. The real `.env` produces a valid settings object.
4. LM Studio’s endpoint is loaded correctly.
5. Approval is enabled by default.
6. A missing or placeholder model produces a clear error.

It does not yet prove that a Deep Agent can run, that a graph can pause, or that LangSmith tracing works. Those belong to later steps.