# Medical necessity review example

A synthetic medical necessity review for orthopedic care: a policy and a case to evaluate it against.

- `policy.srg`: four independently requested services, 25 predicates. Each service branch applies only when the record documents a request, treatment plan or referral for it. Home support can fall back to a facility plan. The rehabilitation and support rules are synthetic, and the guideline PDF the policy cites is not included.
- `clinical_record_synthetic.md`: the case input, a fictional admission record.
- `replay.json`: a recorded run for the viewer. It assumes rehabilitation clearance, facility acceptance and transport that the record does not contain, so its outcomes are not the expected results for the record alone.

View the replay without API credentials:

```bash
uv run python -m symbolic_reasoning.viewer examples/data/medical-necessity/replay.json --open
```

Run the policy against the record with the [Jev integration](../../integrations/jev).
