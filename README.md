```bash
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

----

`uv run` → runs the command inside the virtual environment uv created.

`main:app` → look in main.py for the variable named app.

`--reload` → restarts on file changes.

`--port 8000` → serves on localhost port 8000.
