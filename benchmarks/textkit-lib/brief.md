# Product Brief: Text Toolkit Library

## Overview
A small Python library of text helpers for other programs to import.

## Requirements
1. **Features**:
   - Turn a title into a URL slug
   - Count the words in a text
   - Shorten a text to a maximum length
   - Put a text in title case

## Interface
- A Python package named `textkit`, used as `import textkit`.
- `textkit.slugify(text)` returns the text's letters and digits in lower case, with each run of any other characters turned into a single hyphen and no hyphen at either end: `slugify("Hello, World!")` is `"hello-world"`.
- `textkit.word_count(text)` returns the number of words, a word being a run of characters that are not whitespace: `word_count("a  b\nc")` is 3 and `word_count("")` is 0.
- `textkit.truncate(text, limit, suffix="...")` returns `text` unchanged when it has at most `limit` characters; otherwise the first `limit - len(suffix)` characters followed by `suffix`, exactly `limit` characters in all. A `limit` smaller than the suffix's length raises `ValueError`.
- `textkit.title_case(text)` upper-cases the first letter of every word and lower-cases the rest, leaving the whitespace exactly as it was.

## Technical Constraints
- Python 3, standard library only

## Acceptance Criteria
- Every function behaves exactly as the interface says, including the examples
- Invalid limits raise ValueError
