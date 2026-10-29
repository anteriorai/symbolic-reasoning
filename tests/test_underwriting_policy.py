"""The shared underwriting policy fixture makes one consistent decision per case."""

from itertools import product

import pytest

from symbolic_reasoning import (
    SRG,
    Answer,
    Coverage,
    SRGExecution,
    apply_answers,
    next_request,
    outcomes,
    reasoning_trace,
)


@pytest.mark.parametrize("coverage", list(Coverage))
@pytest.mark.parametrize("values", list(product((False, True), repeat=8)))
def test_underwriting_truth_table(
    underwriting_policy: SRG, coverage: Coverage, values: tuple[bool, ...]
) -> None:
    credit, employment, dti, appraisal, title, deposit, reserves, cosigner = values
    if not all((credit, employment, dti, appraisal, title)):
        expected = "denied"
    elif deposit:
        expected = "approved"
    elif reserves or cosigner:
        expected = "manual_review"
    else:
        expected = "denied"

    facts = dict(zip(underwriting_policy.predicates, values, strict=True))
    execution = SRGExecution(srg=underwriting_policy)
    while (request := next_request(execution, coverage)) is not None:
        answers = {
            item.predicate.id: Answer(
                is_met=facts[item.predicate.id], reasoning="Scripted application"
            )
            for item in request.predicate_requests
        }
        execution = apply_answers(execution, answers)

    assert {outcome.id for outcome in outcomes(execution)} == {expected}
    assert all(
        path.outcome_id == expected for path in reasoning_trace(execution).outcome_paths
    )


def test_policy_keeps_question_metadata_and_context(underwriting_policy: SRG) -> None:
    assert list(underwriting_policy.predicates) == [
        "has_good_credit",
        "has_stable_income",
        "has_low_dti",
        "appraisal_supports_price",
        "has_clear_title",
        "has_down_payment",
        "has_reserves",
        "has_co_signer",
    ]
    assert underwriting_policy.policy_context
    assert all(p.label and p.context for p in underwriting_policy.predicates.values())
    assert {a.label for a in underwriting_policy.aggregators.values() if a.name} == {
        "Borrower risk",
        "Collateral risk",
        "Compensating factors",
        "Insufficient down payment",
    }


def test_underwriting_keeps_shared_aggregators(underwriting_policy: SRG) -> None:
    assert len(underwriting_policy.nodes) == 9
    assert len(underwriting_policy.edges) == 10
    assert len(underwriting_policy.aggregators) == 10
    assert (
        len([e for e in underwriting_policy.edges.values() if e.source == "Root"]) == 5
    )
    negated_deposit = [
        a
        for a in underwriting_policy.aggregators.values()
        if not a.truth_value and a.argument_ids == ["has_down_payment"]
    ]
    assert len(negated_deposit) == 1
    assert (
        sum(
            negated_deposit[0].id in a.argument_ids
            for a in underwriting_policy.aggregators.values()
        )
        == 2
    )
