"""
Symbolic Reasoning - A library for symbolic reasoning on policy documents
"""

from symbolic_reasoning.compiler import (
    CompilerError,
    ParseError,
    compile_srg_file,
    compile_srg_string,
)
from symbolic_reasoning.errors import InvalidAnswerError
from symbolic_reasoning.models import (
    SRG,
    Answer,
    Coverage,
    ExecutionNotResolvedError,
    Outcome,
    OutcomePath,
    Predicate,
    ReasoningTrace,
    SRGBuilder,
    SRGExecution,
    TracePath,
    TraceStep,
    is_resolved,
    load_srg,
    outcomes,
    reasoning_trace,
)
from symbolic_reasoning.recording import (
    ExecutionHistory,
    ExecutionRecorder,
    load_history_file,
    record_execution,
    save_history_file,
    snapshot,
)
from symbolic_reasoning.solvers import (
    AsyncOracle,
    Oracle,
    OracleRequest,
    PredicateRequest,
    apply_answers,
    asolve,
    next_request,
)
from symbolic_reasoning.validation import SRGValidationError

__all__ = [
    "SRG",
    "Answer",
    "AsyncOracle",
    "CompilerError",
    "Coverage",
    "ExecutionHistory",
    "ExecutionNotResolvedError",
    "ExecutionRecorder",
    "InvalidAnswerError",
    "Oracle",
    "OracleRequest",
    "Outcome",
    "OutcomePath",
    "ParseError",
    "Predicate",
    "PredicateRequest",
    "ReasoningTrace",
    "SRGBuilder",
    "SRGExecution",
    "SRGValidationError",
    "TracePath",
    "TraceStep",
    "apply_answers",
    "asolve",
    "compile_srg_file",
    "compile_srg_string",
    "is_resolved",
    "load_history_file",
    "load_srg",
    "next_request",
    "outcomes",
    "reasoning_trace",
    "record_execution",
    "save_history_file",
    "snapshot",
]
