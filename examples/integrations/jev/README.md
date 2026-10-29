# Jev agent integration

Run an SRG policy against Markdown case documents using [TypeSafe's Jev](https://docs.typesafe.ai/concepts/system-one).

From the repository root, add your API key to `.env` (gitignored):

```dotenv
TYPESAFE_API_KEY=your-key-here
```

Run the synthetic underwriting example:

```bash
uv run --env-file .env --project examples/integrations/jev --locked \
  python examples/integrations/jev/agent.py \
  --policy examples/data/underwriting/policy.srg \
  --case examples/data/underwriting/application.md
```

Or run the [MSK example](../../data/msk-review/README.md):

```bash
uv run --env-file .env --project examples/integrations/jev --locked \
  python examples/integrations/jev/agent.py \
  --policy examples/data/msk-review/policy.srg \
  --case examples/data/msk-review/clinical_record_synthetic.md
```

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/); `uv run` installs dependencies automatically. Each run makes live API calls and prints the outcomes and answer probabilities.

For your own inputs, `--policy` accepts `.srg` source or compiled SRG JSON; repeat `--case` for multiple Markdown files. Case files are untrusted: the agent passes them to Jev inside a labelled block with a random boundary, after the policy context, and tells the model that instructions inside them are not guidance. Probabilities of 0.5 or higher become Yes. Low-confidence annotations do not automatically trigger manual review.

Add `--record` to save answer batches to `recordings/<UTC-timestamp>-<random-id>.json` under the current directory. The directory is created automatically and gitignored; the saved path is printed when the run completes. Partial progress is saved if an API call fails.

Use `--record execution.json` to choose a path explicitly; an existing file at that path is replaced. Omit `--record` to skip saving. View a saved run with the command below, substituting its path if you used an automatic filename:

```bash
uv run --locked python -m symbolic_reasoning.viewer execution.json --open
```
