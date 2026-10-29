"""
Models for symbolic reasoning graphs.

This package exports the schema-generated models and utility functions.
"""

# Export generated types and utility functions

from symbolic_reasoning.gen.py.srg import (
    Aggregator,
    AllStrategy,
    AtLeastStrategy,
    AtMostStrategy,
    Edge,
    ExactlyStrategy,
    Node,
    Outcome,
    Predicate,
    Root,
    Strategy,
)

from .aggregator_logic import evaluate_strategy, get_aggregator_label

# Export SRG models
from .srg import ROOT_ID, SRG, SRGBuilder, load_srg

# Export SRGExecution
from .srg_execution import (
    Answer,
    Coverage,
    ExecutionNotResolvedError,
    OutcomePath,
    ReasoningTrace,
    SRGExecution,
    TracePath,
    TraceStep,
    evaluate_symbol,
    is_resolved,
    outcomes,
    reasoning_trace,
)

__all__ = [
    "ROOT_ID",
    "SRG",
    "Aggregator",
    "AllStrategy",
    "Answer",
    "AtLeastStrategy",
    "AtMostStrategy",
    "Coverage",
    "Edge",
    "ExactlyStrategy",
    "ExecutionNotResolvedError",
    "Node",
    "Outcome",
    "OutcomePath",
    "Predicate",
    "ReasoningTrace",
    "Root",
    "SRGBuilder",
    "SRGExecution",
    "Strategy",
    "TracePath",
    "TraceStep",
    "evaluate_strategy",
    "evaluate_symbol",
    "get_aggregator_label",
    "is_resolved",
    "load_srg",
    "outcomes",
    "reasoning_trace",
]
