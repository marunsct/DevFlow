# Product Brief: Word Statistics Tool

## Overview
A command-line program that reports word statistics for a text file.

## Requirements
1. **Features**:
   - Count the words, lines and characters in a text file
   - List the most frequent words
   - Print the results as JSON for other programs
   - Read standard input when the file is given as `-`
   - Report a missing file as an error

## Interface
- Run as `python -m wordstats <file>` from the project directory. It prints three lines: `words: <n>`, `lines: <n>` and `characters: <n>`.
- A word is a run of letters, digits and apostrophes. `characters` counts every character, newlines included. `lines` is the number of lines; a last line without a newline still counts.
- `--top N` prints the N most frequent words instead, one per line as `<word> <count>`, most frequent first, ties in alphabetical order. Words are compared in lower case.
- `--json` prints `{"words": n, "lines": n, "characters": n}`, or with `--top N` prints `{"top": [{"word": w, "count": c}, ...]}`.
- A file that does not exist prints an error to standard error and exits with status 2.

## Technical Constraints
- Python 3, standard library only

## Acceptance Criteria
- Counts are exactly as the interface defines them
- The top words are ordered as the interface says
- JSON output parses and matches the plain output
- Errors go to standard error with exit status 2
