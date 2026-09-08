"""Evaluation dataset definitions."""

DATASETS = {
    "clear_product_doc": {
        "input": "We need a clinic booking app where patients can book appointments with doctors. It needs an MVP by Q3.",
        "expected": {
            "product_name": "Clinic Booking App",
            "has_mvp": True,
            "has_constraints": False,
        },
        "metadata": {
            "category": "baseline",
            "difficulty": "easy",
            "expected_stages": ["intake", "architecture"],
        }
    },
    "ambiguous_product_doc": {
        "input": "Make a system that does things well for people in healthcare. We want it to be fast and maybe use AI.",
        "expected": {
            "has_mvp": False,
            "has_constraints": False,
        },
        "metadata": {
            "category": "ambiguity",
            "difficulty": "medium",
            "expected_stages": ["intake"],
        }
    },
    "conflicting_requirements": {
        "input": "We need the system to be 100% offline but also sync in real-time with the central cloud database at all times.",
        "expected": {
            "has_conflicts": True,
        },
        "metadata": {
            "category": "conflicts",
            "difficulty": "medium",
            "expected_stages": ["intake", "architecture_review"],
        }
    },
    "missing_constraints": {
        "input": "Build a social network for pets. Include profiles and photo sharing.",
        "expected": {
            "has_constraints": False,
        },
        "metadata": {
            "category": "missing_info",
            "difficulty": "easy",
            "expected_stages": ["intake"],
        }
    },
    "unsupported_technologies": {
        "input": "Build a chat app using quantum entangled transmission protocol for zero-latency communication across galaxies.",
        "expected": {
            "has_unsupported_tech": True,
        },
        "metadata": {
            "category": "feasibility",
            "difficulty": "hard",
            "expected_stages": ["tools_models", "architecture_review"],
        }
    },
    "security_sensitive": {
        "input": "Healthcare app that stores PII and HIPAA data. Must handle medical records securely.",
        "expected": {
            "has_security_requirements": True,
        },
        "metadata": {
            "category": "security",
            "difficulty": "medium",
            "expected_stages": ["architecture", "security_review"],
        }
    },
    "review_rejection_case": {
        "input": "This is a deliberately incomplete specification with no architecture details, no database schema, and no API specs.",
        "expected": {
            "should_reject": True,
        },
        "metadata": {
            "category": "review",
            "difficulty": "easy",
            "expected_stages": ["architecture_review"],
        }
    },
}
