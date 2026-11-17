from app.evaluation.evaluators import evaluate_requirement_coverage

def test_evaluators():
    result = evaluate_requirement_coverage({}, {})
    assert result["score"] == 1.0
