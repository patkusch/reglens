# Adding to reglens

Small, focused changes are welcome. Open an issue first for anything large, so nobody builds what will not be merged.

## Before you push

```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m compileall -q reglens
python -m pytest -q
```

Push only when all of it passes. Never pipe the test output into something that hides a failure.

## What every change comes with

- A test that fails without the change and passes with it.
- Rules of law and regulation are named, never stated as settled fact. A qualified person confirms them.
- Plain English in anything a person reads: say what it does and why, and put the plain meaning next to every number.
- No invented figures. A number in the README comes from a run you can repeat, and a result that showed no benefit still goes in.
