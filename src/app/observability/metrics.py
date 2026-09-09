import logging
from typing import Dict, Any
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

logger = logging.getLogger(__name__)

# Basic Prometheus metrics definitions
DEFECTS_RESOLVED = Counter('defects_resolved_total', 'Total number of defects resolved')
DEFECTS_FAILED = Counter('defects_failed_total', 'Total number of defects failed to resolve')
STAGE_DURATION = Histogram('stage_duration_seconds', 'Time spent in each workflow stage', ['stage'])
RUN_TOTAL = Counter('run_total', 'Total number of agentic workflow runs')

class MetricsTracker:
    @staticmethod
    def record_stage_duration(stage_name: str, duration_seconds: float) -> None:
        STAGE_DURATION.labels(stage=stage_name).observe(duration_seconds)
        
    @staticmethod
    def record_defect_resolution(resolved: bool) -> None:
        if resolved:
            DEFECTS_RESOLVED.inc()
        else:
            DEFECTS_FAILED.inc()
            
    @staticmethod
    def record_run() -> None:
        RUN_TOTAL.inc()

def get_metrics_payload() -> tuple[bytes, str]:
    """
    Returns the prometheus metrics payload and content type.
    Suitable for serving on a /metrics HTTP endpoint.
    """
    return generate_latest(), CONTENT_TYPE_LATEST
