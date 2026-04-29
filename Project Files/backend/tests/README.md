# Backend Tests

Pure-Python unit tests run with [pytest](https://docs.pytest.org/). No Finch hardware required — these are intended to be safe to run in CI.

```powershell
cd "Project Files/backend"
python -m pytest tests
```

Hardware-in-the-loop tests (`test_heading.py`, `test_pid.py`) live one directory up in `Project Files/backend/` because they require a connected Finch and shouldn't be picked up by the CI pytest run.
