"""Original small PDF resource regressions through the real reference reader.

Malformed font metadata runs only in a resource-limited child, never in pytest's
own process. No private documents, external model or network is involved.
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


def sparse_width_pdf(subtype: str) -> bytes:
    """Build a tiny, readable page with an absurd declared simple-font range."""
    stream = b"BT /F1 12 Tf 60 700 Td (The ferry register remains closed.) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
         b"/Resources << /Font << /F1 5 0 R >> >> >>"),
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /" + subtype.encode() + b" /BaseFont /OriginalAudit "
        b"/FirstChar 0 /LastChar 999999999 /Widths [500] >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode() + b"0000000000 65535 f \n"
    out += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    return bytes(out)


@pytest.mark.skipif(importlib.util.find_spec("resource") is None, reason="POSIX child resource limits unavailable")
@pytest.mark.parametrize("subtype", ["Type1", "TrueType"])
def test_sparse_font_range_is_bounded_and_keeps_complete_text(tmp_path, subtype):
    raw = sparse_width_pdf(subtype)
    assert len(raw) < 1024
    source = tmp_path / "original-synthetic.pdf"
    source.write_bytes(raw)
    worker = """
import json, resource, sys
from pathlib import Path
resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
resource.setrlimit(resource.RLIMIT_CPU, (2, 3))
def offline(event, args):
    if event.startswith('socket.'):
        raise AssertionError('PDF resource regression must remain offline')
sys.addaudithook(offline)
from novel_ai import reading
# Exercise the installed lightweight dependency regardless of optional adapters.
reading._advanced_extract = lambda *args: None
result = reading.extract_reference('original-synthetic.pdf', Path(sys.argv[1]).read_bytes())
print(json.dumps({'text': result.text, 'backend': result.backend}))
"""
    completed = subprocess.run(
        [sys.executable, "-c", worker, str(source)],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=8,
        check=False,
    )
    assert completed.returncode == 0, (completed.returncode, completed.stdout, completed.stderr)
    assert json.loads(completed.stdout) == {
        "text": "The ferry register remains closed.", "backend": "pypdf",
    }
    assert source.read_bytes() == raw
