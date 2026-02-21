# Development

## Local Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e ".[dev]"
```

## Run Tests

Use the helper script (creates `.venv` if missing, installs dev dependencies, then runs pytest):

```bash
./run_tests.sh
```

Run a subset:

```bash
./run_tests.sh tests/test_service.py
```
