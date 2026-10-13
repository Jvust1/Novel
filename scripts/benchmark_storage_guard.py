"""Same synthetic ancestry and repetitions for baseline and candidate."""
import json
import os
import statistics
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from novel_ai.storage_guard import reject_links

with tempfile.TemporaryDirectory(prefix="novel-guard-bench-") as root:
    path = Path(root) / "projects" / "synthetic" / "memory" / "chapter.json"
    path.parent.mkdir(parents=True)
    path.write_text("{}")
    count = [0]
    actual = os.lstat
    actual_stat = os.stat

    def tracked(*args, **kwargs):
        count[0] += 1
        return actual(*args, **kwargs)

    def tracked_stat(*args, **kwargs):
        count[0] += 1
        return actual_stat(*args, **kwargs)

    with patch("os.lstat", tracked), patch("os.stat", tracked_stat):
        reject_links(path)
    timings = []
    for trial in range(5):
        start = time.perf_counter()
        for iteration in range(500):
            reject_links(path)
        timings.append(time.perf_counter() - start)
    print(json.dumps({"ancestors": len(path.parents) + 1, "metadata_queries": count[0], "iterations_per_trial": 500, "seconds": timings, "median_seconds": statistics.median(timings)}))
