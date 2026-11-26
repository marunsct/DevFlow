"""Pure analysis logic for word statistics."""

import re
import collections


def analyze(text: str) -> dict:
    """Count words, lines, and characters in the given text.

    Args:
        text: The text content to analyze.

    Returns:
        A dictionary with keys 'words', 'lines', and 'characters'.
    """
    # Count characters: len(text) counts every character including newlines
    characters = len(text)

    # Count lines: split by newline.
    # If text is empty, lines should be 0.
    # If text ends with newline, split produces an empty string at the end which is not a line.
    # If text does not end with newline, the last part is a line.
    # Standard definition: number of newline characters, or 1 if there is content but no newline.
    if not text:
        lines = 0
    else:
        lines = text.count('\n')
        if not text.endswith('\n'):
            lines += 1

    # Count words: runs of [a-zA-Z0-9']+
    # Using findall to get all matching tokens
    words_list = re.findall(r"[a-zA-Z0-9']+", text)
    words = len(words_list)

    return {
        'words': words,
        'lines': lines,
        'characters': characters,
    }


def get_top_words(text: str, n: int) -> list:
    """Get the top N most frequent words.

    Words are compared case-insensitively. The returned word preserves the
    original case of its first occurrence. Ties are broken by alphabetical
    order (case-insensitive).

    Args:
        text: The text content to analyze.
        n: The number of top words to return.

    Returns:
        A list of dictionaries with keys 'word' and 'count', sorted by
        count descending, then word ascending (case-insensitive).
    """
    # Tokenize into words
    words_list = re.findall(r"[a-zA-Z0-9']+", text)

    if not words_list:
        return []

    # Count frequencies and track first occurrence
    # We need to preserve the original case of the first occurrence
    word_counts = collections.Counter()
    first_occurrence = {}

    for word in words_list:
        word_lower = word.lower()
        if word_lower not in first_occurrence:
            first_occurrence[word_lower] = word
        word_counts[word_lower] += 1

    # Create list of (word_lower, count, original_word)
    items = []
    for word_lower, count in word_counts.items():
        items.append({
            'word': first_occurrence[word_lower],
            'count': count,
            'sort_key': (word_lower, first_occurrence[word_lower])
        })

    # Sort by count descending, then word ascending (case-insensitive)
    # The brief says: "Sorts by count descending, then word ascending (case-insensitive)"
    # And "Words are compared in lower case" for tie-breaking
    items.sort(key=lambda x: (-x['count'], x['word'].lower()))

    # Return at most n entries
    result = []
    for item in items[:n]:
        result.append({
            'word': item['word'],
            'count': item['count']
        })

    return result
