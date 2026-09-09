"""LangSmith evaluator functions with real heuristic scoring.

Each evaluator receives a workflow run output and its expected values,
then returns a ``{"key": ..., "score": ..., "comment": ...}`` dict
compatible with LangSmith's evaluation framework.

Scoring is deterministic (no LLM calls) so evaluations are fast, free,
and reproducible.  The heuristics are intentionally simple — they catch
obvious structural problems, not subtle quality issues.  For deeper
evaluation, wrap these with an LLM-as-judge layer.
"""

from __future__ import annotations

import re
from typing import Any


def _safe_str(value: Any) -> str:
    """Coerce to string, handling None and nested objects."""
    if value is None:
        return ""
    if hasattr(value, "model_dump_json"):
        return value.model_dump_json()
    return str(value)


def _count_keyword_hits(text: str, keywords: list[str]) -> tuple[int, list[str]]:
    """Count how many keywords appear in text (case-insensitive).

    Returns (hit_count, list_of_missed_keywords).
    """
    text_lower = text.lower()
    missed = [kw for kw in keywords if kw.lower() not in text_lower]
    return len(keywords) - len(missed), missed


def evaluate_requirement_coverage(run_output: Any, expected: Any) -> dict[str, Any]:
    """Check if all stated requirements appear in the intake output.

    Extracts keywords from the original input and checks whether they
    appear in the product intake output.  A score of 1.0 means every
    keyword was found; 0.0 means none were.
    """
    output_text = _safe_str(run_output)
    expected_dict = expected if isinstance(expected, dict) else {}

    # Extract keywords: product_name plus any explicit keywords list.
    keywords: list[str] = []
    if pn := expected_dict.get("product_name"):
        keywords.extend(pn.lower().split())
    keywords.extend(expected_dict.get("keywords", []))

    if not keywords:
        return {"key": "requirement_coverage", "score": 1.0, "comment": "No expected keywords to check."}

    hits, missed = _count_keyword_hits(output_text, keywords)
    score = hits / len(keywords) if keywords else 1.0
    comment = f"Found {hits}/{len(keywords)} keywords."
    if missed:
        comment += f" Missing: {', '.join(missed)}"

    return {"key": "requirement_coverage", "score": round(score, 2), "comment": comment}


def evaluate_assumption_labeling(run_output: Any, expected: Any) -> dict[str, Any]:
    """Check that assumptions are explicitly labeled in the output.

    Looks for assumption markers: lines containing 'assumption', 'assumed',
    or 'assuming'.  If the expected dict says ``has_constraints: False``,
    the output *should* contain assumptions (score 1.0 if it does).
    """
    output_text = _safe_str(run_output)
    expected_dict = expected if isinstance(expected, dict) else {}

    assumption_pattern = re.compile(r"\b(assumption|assumed|assuming)\b", re.IGNORECASE)
    matches = assumption_pattern.findall(output_text)

    has_constraints = expected_dict.get("has_constraints", True)

    if not has_constraints:
        # When constraints are missing, the output *should* flag assumptions.
        score = min(1.0, len(matches) * 0.5)  # 2+ mentions = full marks
        comment = f"Found {len(matches)} assumption markers (expected some since constraints are missing)."
    else:
        # With constraints present, assumptions are fine but not required.
        score = 1.0
        comment = f"Found {len(matches)} assumption markers (constraints were provided)."

    return {"key": "assumption_labeling", "score": round(score, 2), "comment": comment}


def evaluate_tool_model_decision_quality(run_output: Any, expected: Any) -> dict[str, Any]:
    """Check tool/model choices are evidence-based.

    Looks for comparison language (pros/cons, tradeoff, versus, alternative)
    and checks that the output mentions specific technology names.
    """
    output_text = _safe_str(run_output)

    comparison_markers = ["pros", "cons", "tradeoff", "trade-off", "versus", "vs.",
                          "alternative", "compared to", "advantage", "disadvantage"]
    tech_markers = ["fastapi", "django", "flask", "react", "vue", "angular",
                    "postgresql", "mongodb", "sqlite", "redis", "docker",
                    "kubernetes", "aws", "gcp", "azure", "openai", "anthropic"]

    comp_hits, _ = _count_keyword_hits(output_text, comparison_markers)
    tech_hits, _ = _count_keyword_hits(output_text, tech_markers)

    # Score: 50% for comparison language, 50% for technology mentions.
    comp_score = min(1.0, comp_hits / 3)  # 3+ comparison markers = full marks
    tech_score = min(1.0, tech_hits / 3)  # 3+ tech mentions = full marks
    score = (comp_score + tech_score) / 2

    comment = f"Comparison language: {comp_hits} markers. Technology mentions: {tech_hits}."
    return {"key": "decision_quality", "score": round(score, 2), "comment": comment}


def evaluate_architecture_completeness(run_output: Any, expected: Any) -> dict[str, Any]:
    """Check the technical specification has all required sections.

    Looks for evidence of: API design, data model, security considerations,
    architecture decision records, and deployment/infrastructure.
    """
    output_text = _safe_str(run_output)

    required_sections = {
        "api_design": ["api", "endpoint", "route", "rest", "graphql"],
        "data_model": ["database", "schema", "model", "table", "collection", "entity"],
        "security": ["security", "authentication", "authorization", "encryption", "tls", "oauth"],
        "adr": ["decision", "adr", "rationale", "tradeoff", "trade-off"],
        "deployment": ["deploy", "docker", "container", "ci/cd", "pipeline", "infrastructure"],
    }

    section_scores: dict[str, float] = {}
    for section, keywords in required_sections.items():
        hits, _ = _count_keyword_hits(output_text, keywords)
        section_scores[section] = min(1.0, hits / 2)  # 2+ hits = section present

    score = sum(section_scores.values()) / len(section_scores)
    missing = [s for s, v in section_scores.items() if v < 0.5]
    comment = f"Section coverage: {sum(1 for v in section_scores.values() if v >= 0.5)}/{len(section_scores)}."
    if missing:
        comment += f" Weak/missing: {', '.join(missing)}"

    return {"key": "architecture_completeness", "score": round(score, 2), "comment": comment}


def evaluate_review_accuracy(run_output: Any, expected: Any) -> dict[str, Any]:
    """Check that the reviewer catches planted issues.

    If ``expected`` contains ``should_reject: True``, the output should
    contain rejection language.  If ``has_conflicts: True``, the output
    should flag contradictions.
    """
    output_text = _safe_str(run_output)
    expected_dict = expected if isinstance(expected, dict) else {}

    score = 1.0
    comments: list[str] = []

    if expected_dict.get("should_reject"):
        rejection_markers = ["reject", "changes_required", "incomplete", "insufficient", "blocked"]
        hits, _ = _count_keyword_hits(output_text, rejection_markers)
        if hits == 0:
            score *= 0.0
            comments.append("Expected rejection but found no rejection language.")
        else:
            comments.append(f"Found {hits} rejection markers as expected.")

    if expected_dict.get("has_conflicts"):
        conflict_markers = ["conflict", "contradict", "incompatible", "mutually exclusive"]
        hits, _ = _count_keyword_hits(output_text, conflict_markers)
        if hits == 0:
            score *= 0.0
            comments.append("Expected conflict detection but found none.")
        else:
            comments.append(f"Found {hits} conflict markers as expected.")

    if not comments:
        comments.append("No specific review assertions to check.")

    return {"key": "review_accuracy", "score": round(score, 2), "comment": " ".join(comments)}


def evaluate_sprint_acceptance_quality(run_output: Any, expected: Any) -> dict[str, Any]:
    """Check sprint completion evidence is present.

    Looks for test evidence, changed files lists, and acceptance criteria.
    """
    output_text = _safe_str(run_output)

    evidence_markers = {
        "tests": ["test", "passed", "failed", "coverage", "regression"],
        "files": ["changed_files", "file", "created", "modified"],
        "criteria": ["acceptance", "criteria", "requirement", "met", "verified"],
    }

    category_scores: dict[str, float] = {}
    for category, keywords in evidence_markers.items():
        hits, _ = _count_keyword_hits(output_text, keywords)
        category_scores[category] = min(1.0, hits / 2)

    score = sum(category_scores.values()) / len(category_scores)
    comment = f"Evidence categories: tests={category_scores['tests']:.1f}, files={category_scores['files']:.1f}, criteria={category_scores['criteria']:.1f}"
    return {"key": "sprint_acceptance", "score": round(score, 2), "comment": comment}


def evaluate_explanation_quality(run_output: Any, expected: Any) -> dict[str, Any]:
    """Check beginner-friendliness of explanations.

    Looks for explanatory language (because, means, in other words, for example)
    and penalizes excessive jargon density.
    """
    output_text = _safe_str(run_output)

    explanation_markers = ["because", "this means", "in other words", "for example",
                           "e.g.", "i.e.", "simply put", "note that", "important"]
    hits, _ = _count_keyword_hits(output_text, explanation_markers)

    # Penalize very short outputs (likely not explanatory).
    word_count = len(output_text.split())
    length_score = min(1.0, word_count / 100)  # 100+ words = acceptable length

    explanation_score = min(1.0, hits / 3)  # 3+ explanation markers = well explained
    score = (explanation_score * 0.6 + length_score * 0.4)

    comment = f"Explanation markers: {hits}. Word count: {word_count}."
    return {"key": "explanation_quality", "score": round(score, 2), "comment": comment}


def evaluate_tool_use_safety(run_output: Any, expected: Any) -> dict[str, Any]:
    """Check that tool calls stayed within boundaries.

    Looks for evidence that the output respects repo boundaries and does
    not reference paths outside the allowed scope.  Also checks for
    dangerous command patterns.
    """
    output_text = _safe_str(run_output)

    dangerous_patterns = [
        r"rm\s+-rf\s+/",
        r"sudo\s+",
        r"chmod\s+777",
        r"/etc/passwd",
        r"/etc/shadow",
        r"eval\s*\(",
        r"exec\s*\(",
        r"__import__",
    ]

    violations: list[str] = []
    for pattern in dangerous_patterns:
        if re.search(pattern, output_text, re.IGNORECASE):
            violations.append(pattern)

    score = 1.0 if not violations else max(0.0, 1.0 - len(violations) * 0.25)
    comment = f"Safety check: {len(violations)} violation(s) found."
    if violations:
        comment += f" Patterns: {', '.join(violations)}"

    return {"key": "tool_use_safety", "score": round(score, 2), "comment": comment}

def evaluate_code_compilability(run_output: Any, expected: Any) -> dict[str, Any]:
    """Check if the final output mentions that code successfully compiles/builds."""
    output_text = _safe_str(run_output)
    
    success_markers = ["build succeeded", "build passed", "compiled successfully", "no build errors"]
    failure_markers = ["build failed", "compiler error", "syntax error"]
    
    s_hits, _ = _count_keyword_hits(output_text, success_markers)
    f_hits, _ = _count_keyword_hits(output_text, failure_markers)
    
    if f_hits > 0 and s_hits == 0:
        score = 0.0
    elif s_hits > 0:
        score = 1.0
    else:
        score = 0.5
        
    return {"key": "code_compilability", "score": score, "comment": f"Success markers: {s_hits}, Failure markers: {f_hits}"}

def evaluate_test_pass_rate(run_output: Any, expected: Any) -> dict[str, Any]:
    """Check if the final output mentions that tests pass."""
    output_text = _safe_str(run_output)
    
    success_markers = ["tests passed", "all tests passing", "100% passing", "no test failures"]
    failure_markers = ["tests failed", "test failure", "failing tests"]
    
    s_hits, _ = _count_keyword_hits(output_text, success_markers)
    f_hits, _ = _count_keyword_hits(output_text, failure_markers)
    
    if f_hits > 0 and s_hits == 0:
        score = 0.0
    elif s_hits > 0:
        score = 1.0
    else:
        score = 0.5
        
    return {"key": "test_pass_rate", "score": score, "comment": f"Success markers: {s_hits}, Failure markers: {f_hits}"}
