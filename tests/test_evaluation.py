from app.evaluation.datasets import DATASETS
from app.evaluation.evaluators import evaluate_requirement_coverage

def test_datasets():
    assert "clear_product_doc" in DATASETS
    assert DATASETS["clear_product_doc"]["metadata"]["difficulty"] == "easy"

def test_evaluators():
    result = evaluate_requirement_coverage({}, {})
    assert result["score"] == 1.0
