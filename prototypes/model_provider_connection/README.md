# Model Provider Connection Prototype

Standalone local prototype for testing a model provider Base URL, discovering OpenAI-compatible or Anthropic models, and selecting models in the current browser session.

```powershell
python -m pip install -r requirements.txt
python server.py
```

The server binds to `127.0.0.1:8024` by default. Set `MODEL_PROVIDER_PORT` to use another port. API keys are held in memory for each request and are not persisted by this prototype.
