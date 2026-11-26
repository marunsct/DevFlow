## Domain Model
- TextFile: A text file or stdin input. Identified by a file path string or the sentinel '-' for stdin. Contains raw text content as a string.
- WordStatistics: The result of analyzing a text file. Fields: word_count (int), line_count (int), character_count (int). Character count equals len(text) including newlines. Line count is the number of newline-separated segments; a last segment without a trailing newline still counts as one line.
- TopWordEntry: A single entry in the top-N frequent words output. Fields: word (str, original case from first occurrence), count (int).
- TopWordsResult: The result of top-N analysis. Contains a list of TopWordEntry objects sorted by frequency descending, then alphabetically ascending on lowercased word form for ties.
- OutputMode: Enum-like concept with three values: 'plain' (default, prints three count lines), 'top' (--top N set, replaces basic counts), 'json' (prints JSON object). When both --json and --top are set, the JSON output shape matches top mode.
- WordToken: A match of the regex [a-zA-Z0-9']+ against the input text. Represents a single word unit for counting purposes.
- ErrorState: The state when a file does not exist or cannot be read. Stderr receives 'Error: '<path>' not found\n'. Exit status is 2. stdout is empty.

