import pytest
from app.evaluation.evaluators import (
    evaluate_requirement_coverage,
    evaluate_assumption_labeling,
    evaluate_tool_model_decision_quality,
    evaluate_architecture_completeness,
    evaluate_review_accuracy,
    evaluate_sprint_acceptance_quality,
    evaluate_explanation_quality,
    evaluate_tool_use_safety,
    evaluate_code_compilability,
    evaluate_test_pass_rate,
)

def test_evaluate_requirement_coverage():
    run_output = "We will build a fast application."
    expected = {"product_name": "Fast App", "keywords": ["application", "build"]}
    result = evaluate_requirement_coverage(run_output, expected)
    assert result["key"] == "requirement_coverage"
    assert result["score"] > 0
    assert "Found 4/4 keywords" in result["comment"]

    # Missed
    result2 = evaluate_requirement_coverage(run_output, {"keywords": ["missing", "application"]})
    assert result2["score"] == 0.5
    assert "Missing: missing" in result2["comment"]

    # No expected
    result3 = evaluate_requirement_coverage(run_output, {})
    assert result3["score"] == 1.0
    assert "No expected keywords" in result3["comment"]

def test_evaluate_assumption_labeling():
    run_output = "Assuming this is fine."
    expected = {"has_constraints": False}
    result = evaluate_assumption_labeling(run_output, expected)
    assert result["score"] == 0.5
    
    expected_with_constraints = {"has_constraints": True}
    result2 = evaluate_assumption_labeling(run_output, expected_with_constraints)
    assert result2["score"] == 1.0

def test_evaluate_tool_model_decision_quality():
    run_output = "FastAPI has an advantage versus Django, tradeoff."
    result = evaluate_tool_model_decision_quality(run_output, {})
    assert result["score"] > 0
    assert "Comparison language: 3 markers" in result["comment"]
    assert "Technology mentions: 2" in result["comment"]

def test_evaluate_architecture_completeness():
    run_output = "We have an API route using a database table with OAuth security. ADR tradeoff included. Docker deploy."
    result = evaluate_architecture_completeness(run_output, {})
    assert result["score"] > 0
    assert result["key"] == "architecture_completeness"

def test_evaluate_review_accuracy():
    run_output = "I must reject this due to conflict."
    expected = {"should_reject": True, "has_conflicts": True}
    result = evaluate_review_accuracy(run_output, expected)
    assert result["score"] == 1.0
    
    run_output_fail = "Looks good"
    result_fail = evaluate_review_accuracy(run_output_fail, expected)
    assert result_fail["score"] == 0.0

def test_evaluate_sprint_acceptance_quality():
    run_output = "tests passed, 3 files modified, acceptance criteria met."
    result = evaluate_sprint_acceptance_quality(run_output, {})
    assert result["score"] > 0

def test_evaluate_explanation_quality():
    run_output = "This means we have an issue because of X. For example, note that Y is important. " * 15 # make it long
    result = evaluate_explanation_quality(run_output, {})
    assert result["score"] > 0

def test_evaluate_tool_use_safety():
    run_output = "I ran sudo rm -rf /"
    result = evaluate_tool_use_safety(run_output, {})
    assert result["score"] < 1.0

def test_evaluate_code_compilability():
    run_output = "build succeeded"
    result = evaluate_code_compilability(run_output, {})
    assert result["score"] == 1.0
    
    run_output_fail = "build failed"
    result_fail = evaluate_code_compilability(run_output_fail, {})
    assert result_fail["score"] == 0.0

def test_evaluate_test_pass_rate():
    run_output = "tests passed"
    result = evaluate_test_pass_rate(run_output, {})
    assert result["score"] == 1.0
    
    run_output_fail = "tests failed"
    result_fail = evaluate_test_pass_rate(run_output_fail, {})
    assert result_fail["score"] == 0.0
