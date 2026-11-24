# Working in reglens

A regulatory-change investment-decision agent built on DataHub — discovers impact via lineage, costs ACT NOW / DEFER / MIN. COMPLIANCE, and writes the decision back into the graph.

## Run the tests

You need Python 3.10 or newer.

```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q
```

Every test should pass before you start and after you finish.

## Where things are

- `tests/`: the tests
- `examples/`: worked examples
- `demo/`: demo material

## Before you commit

- Make sure the tests pass.
- Put changes people will notice in `CHANGELOG.md`.
- Do not put real passwords, keys or private data in test files or examples. Use made-up ones.
