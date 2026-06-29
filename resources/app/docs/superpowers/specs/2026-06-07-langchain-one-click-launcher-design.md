# Langchain One-Click Launcher Design

## Goal

Provide a Windows double-click launcher for the downloaded `MaLunan/langchain` digital-human workflow in `third_party/langchain`.

## User Experience

The user opens a `.bat` file from the project root. The batch file runs a Python launcher that checks Python dependencies, creates `.env` from `.env.example` when missing, starts the workflow backend on `127.0.0.1:8000`, waits until `/health` responds, then opens the browser at the workflow UI. The terminal remains open to show status and can be closed with `Ctrl+C`.

## Architecture

The downloaded project already has a FastAPI backend and a built Vue frontend in `frontend/dist`. The backend will serve that built frontend directly so the launcher only has to run one service. API routes such as `/workflow/*`, `/rewrite-styles`, `/uploads/*`, and `/generated/*` remain unchanged.

## Files

- `third_party/langchain/server.py`: mount `frontend/dist` as a fallback static UI.
- `third_party/langchain/tests/test_server.py`: verify `/` returns the built frontend.
- `start_langchain_digital_human.bat`: Windows double-click launcher.
- `start_langchain_digital_human.py`: Python launcher with dependency check, health-check wait loop, browser open, and backend shutdown.

## Error Handling

If Python is missing, dependency installation fails, required API keys are missing, or the backend never becomes healthy, the launcher prints a clear message and keeps the terminal open. If port `8000` is already used, uvicorn reports the bind failure in the same terminal.

## Testing

Run the downloaded project's server tests, then compile the changed Python file. Finally, launch the service long enough to verify `/health` and `/` respond locally.
