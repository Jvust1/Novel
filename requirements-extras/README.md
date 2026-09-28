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

## Document readers

The dependency-light built-in reader remains the default so frozen benchmark parsing does not change when optional packages are installed. Advanced readers are selected explicitly:

```python
from novel_ai.reading import extract_reference_text

text = extract_reference_text("chapter.pdf", data, backend="markitdown")
text = extract_reference_text("chapter.pdf", data, backend="docling")
```

Both adapters use a temporary file and return derived text only; they do not persist the uploaded document. Missing optional packages produce an actionable install error.
