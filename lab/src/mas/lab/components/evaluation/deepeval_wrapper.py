#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""
DeepEval Wrapper for LLM-as-a-Judge Metrics.

This module provides an adapter to use DeepEval metrics (or mock them)
within the mas-lab evaluation framework.

It allows the User Emulation Agent to judge the quality of responses.
"""

from typing import Any, Dict, List, Optional
import random
import time

# Try to import deepeval, else provide mock
try:
    from deepeval.metrics import AnswerRelevancyMetric
    from deepeval.test_case import LLMTestCase
    DEEPEVAL_AVAILABLE = True
except ImportError:
    DEEPEVAL_AVAILABLE = False
    
    # Mock classes for demonstration without dependency
    class AnswerRelevancyMetric:
        metric_id = "answer_relevancy"

        def __init__(self, threshold: float = 0.5, **kwargs: Any):
            self.threshold = threshold
            self.score = 0.0
            self.reason = ""
            
        def measure(self, test_case: Any):
            time.sleep(0.1)
            self.score = random.uniform(0.6, 1.0)
            self.reason = "Mock relevancy score."
            return self.score

        def compute(self, *, run_id: str, level: str, context: dict) -> dict:
            """Interface expected by AnnotateMetricsStep."""
            self.score = random.uniform(0.6, 1.0)
            self.reason = "Mock relevancy score."
            import datetime
            return {
                "run_id": run_id,
                "metric": self.metric_id,
                "level": level,
                "score": self.score,
                "reasoning": self.reason,
                "model": "mock",
                "computed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "error": None,
            }

        def is_successful(self):
            return self.score >= self.threshold

    class LLMTestCase:
        def __init__(self, input: str, actual_output: str, retrieval_context: List[str] = None):
            self.input = input
            self.actual_output = actual_output
            self.retrieval_context = retrieval_context or []


class DeepEvalEvaluator:
    """
    Evaluator that uses DeepEval metrics to judge agent performance.
    """
    
    def __init__(self):
        self.relevancy_metric = AnswerRelevancyMetric(threshold=0.7)
        
    def evaluate_response(self, input_prompt: str, output_response: str, context: List[str] = None) -> Dict[str, Any]:
        """
        Evaluate a single response using LLM-as-a-Judge.
        
        Args:
            input_prompt: The user's original query.
            output_response: The agent's final answer.
            context: (Optional) Retrieved context chunks.
            
        Returns:
            Dictionary with score and reason.
        """
        test_case = LLMTestCase(
            input=input_prompt,
            actual_output=output_response,
            retrieval_context=context
        )
        
        score = self.relevancy_metric.measure(test_case)
        
        return {
            "answer_relevancy": score,
            "reason": self.relevancy_metric.reason
        }
