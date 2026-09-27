# Optional integration dependencies

The default `requirements.txt` stays intentionally small and stable.

Install only the capability group you are evaluating:

```bash
pip install -r requirements-extras/nlp.txt
pip install -r requirements-extras/reference.txt
pip install -r requirements-extras/memory.txt
pip install -r requirements-extras/eval.txt
pip install -r requirements-extras/provider.txt
```

`all.txt` exists for disposable experiment environments, not as the recommended production install.

Heavy runtimes such as vLLM, Qdrant server, Ollama, KoboldCpp, Promptfoo and graph databases are normally run externally. Their Python/client packages are optional and the Novel core must continue to work without them.
