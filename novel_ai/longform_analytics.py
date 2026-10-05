from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import importlib.util
import math
import re
from typing import Any, Sequence

from .quality_gate import analyze_prose_quality
from .reference_similarity import event_sequence_similarity


@dataclass(frozen=True)
class ChapterAnalytics:
    chapter_id: str
    scene_count: int
    event_count: int
    hook_count: int
    choice_count: int
    cost_count: int
    state_change_count: int
    tension_curve: str
    sentence_length_mean: float
    sentence_length_std: float
    paragraph_length_cv: float
    bigram_diversity: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DriftAlert:
    metric: str
    chapter_id: str
    value: float
    baseline: float
    severity: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def chapter_analytics(chapter_id: str, text: str, story_dna: dict[str, Any]) -> ChapterAnalytics:
    q = analyze_prose_quality(text)
    beats = list(story_dna.get("beats") or [])
    return ChapterAnalytics(
        chapter_id=str(chapter_id),
        scene_count=len(beats),
        event_count=len(story_dna.get("event_sequence") or []),
        hook_count=int(story_dna.get("hook_count", 0) or 0),
        choice_count=int(story_dna.get("choice_count", 0) or 0),
        cost_count=int(story_dna.get("cost_count", 0) or 0),
        state_change_count=int(story_dna.get("state_change_count", 0) or 0),
        tension_curve=str(story_dna.get("tension_curve", "") or ""),
        sentence_length_mean=float(q.sentence_length_mean),
        sentence_length_std=float(q.sentence_length_std),
        paragraph_length_cv=float(q.paragraph_length_cv),
        bigram_diversity=float(q.bigram_diversity),
    )


def trope_frequency(history: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate interpretable long-form pattern counts from persisted Story DNA."""
    tension = Counter()
    structure = Counter()
    hooks = Counter()
    for row in history:
        dna = row.get("story_dna") or row
        tension[str(dna.get("tension_curve", "") or "(未标注)")] += 1
        scenes = len(dna.get("beats") or [])
        key = (
            f"场景{scenes}/选择{int(dna.get('choice_count',0) or 0)}/"
            f"代价{int(dna.get('cost_count',0) or 0)}/变化{int(dna.get('state_change_count',0) or 0)}"
        )
        structure[key] += 1
        for beat in dna.get("beats") or []:
            hook = str(beat.get("end_hook", "") or "").strip()
            if hook:
                # Keep only a short normalized surface category. Full prose is not
                # needed for aggregate statistics.
                norm = re.sub(r"\s+", "", hook)[:18]
                hooks[norm] += 1
    return {
        "chapter_count": len(history),
        "tension_curves": dict(tension.most_common()),
        "structure_patterns": dict(structure.most_common()),
        "repeated_end_hooks": {k:v for k,v in hooks.most_common() if v >= 2},
    }


def _fallback_clusters(history: Sequence[dict[str, Any]], threshold: float = 0.72) -> list[dict[str, Any]]:
    """Connected components over event-sequence similarity."""
    n=len(history)
    graph={i:set() for i in range(n)}
    for i in range(n):
        a=(history[i].get("story_dna") or history[i]).get("event_sequence") or []
        for j in range(i+1,n):
            b=(history[j].get("story_dna") or history[j]).get("event_sequence") or []
            if event_sequence_similarity(a,b) >= threshold:
                graph[i].add(j); graph[j].add(i)
    seen=set(); clusters=[]
    for i in range(n):
        if i in seen: continue
        stack=[i]; comp=[]; seen.add(i)
        while stack:
            cur=stack.pop(); comp.append(cur)
            for nxt in graph[cur]:
                if nxt not in seen: seen.add(nxt); stack.append(nxt)
        clusters.append({
            "cluster": len(clusters),
            "chapters":[str(history[x].get("chapter_id","")) for x in comp],
            "size":len(comp),
            "backend":"event-similarity",
        })
    return sorted(clusters,key=lambda x:x["size"],reverse=True)


def cluster_story_dna(history: Sequence[dict[str, Any]], max_clusters: int = 8) -> list[dict[str, Any]]:
    """Cluster historical Story DNA.

    scikit-learn TF-IDF + KMeans is used when available. The deterministic
    event-similarity fallback keeps the feature usable without optional deps.
    """
    rows=list(history)
    if len(rows)<2:
        return _fallback_clusters(rows)

    if importlib.util.find_spec("sklearn") is not None:
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.cluster import KMeans
            corpus=[
                " ".join((r.get("story_dna") or r).get("event_sequence") or [])
                for r in rows
            ]
            k=max(2,min(int(math.sqrt(len(rows))) or 2,max_clusters,len(rows)))
            matrix=TfidfVectorizer(analyzer="char",ngram_range=(2,4),max_features=1024).fit_transform(corpus)
            labels=KMeans(n_clusters=k,random_state=42,n_init=10).fit_predict(matrix)
            groups:dict[int,list[str]]={}
            for label,row in zip(labels,rows):
                groups.setdefault(int(label),[]).append(str(row.get("chapter_id","")))
            return sorted(
                [{"cluster":cid,"chapters":chapters,"size":len(chapters),"backend":"sklearn-kmeans"} for cid,chapters in groups.items()],
                key=lambda x:x["size"],reverse=True,
            )
        except Exception:
            pass
    return _fallback_clusters(rows)


def project_story_dna_2d(history: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Optional UMAP visualization coordinates; returns [] when unavailable."""
    rows=list(history)
    if len(rows)<4 or importlib.util.find_spec("umap") is None or importlib.util.find_spec("sklearn") is None:
        return []
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        import umap
        corpus=[" ".join((r.get("story_dna") or r).get("event_sequence") or []) for r in rows]
        matrix=TfidfVectorizer(analyzer="char",ngram_range=(2,4),max_features=1024).fit_transform(corpus)
        reducer=umap.UMAP(n_components=2,random_state=42,n_neighbors=min(8,len(rows)-1))
        coords=reducer.fit_transform(matrix)
        return [
            {"chapter_id":str(row.get("chapter_id","")),"x":float(x),"y":float(y)}
            for row,(x,y) in zip(rows,coords)
        ]
    except Exception:
        return []


def detect_longform_drift(history: Sequence[dict[str, Any]], window: int = 6) -> list[DriftAlert]:
    """Detect chapter-level rhythm/style drift from persisted analytics.

    Uses River ADWIN when installed; otherwise a rolling z-score style fallback.
    This is chapter-level style/rhythm drift, not per-character dialogue drift.
    """
    rows=[r.get("analytics") or r for r in history]
    metrics=["sentence_length_mean","paragraph_length_cv","bigram_diversity","scene_count","hook_count"]
    alerts:list[DriftAlert]=[]

    if importlib.util.find_spec("river") is not None:
        try:
            from river import drift
            detectors={m:drift.ADWIN() for m in metrics}
            for row in rows:
                cid=str(row.get("chapter_id",""))
                for metric in metrics:
                    value=float(row.get(metric,0.0) or 0.0)
                    det=detectors[metric]
                    det.update(value)
                    if det.drift_detected:
                        alerts.append(DriftAlert(metric,cid,value,float(det.estimation),"medium",f"{metric} 出现在线漂移"))
            return alerts
        except Exception:
            alerts=[]

    for i,row in enumerate(rows):
        if i < max(3,window):
            continue
        cid=str(row.get("chapter_id",""))
        prev=rows[max(0,i-window):i]
        for metric in metrics:
            vals=[float(x.get(metric,0.0) or 0.0) for x in prev]
            value=float(row.get(metric,0.0) or 0.0)
            baseline=sum(vals)/len(vals)
            variance=sum((v-baseline)**2 for v in vals)/len(vals)
            std=variance**0.5
            if std>1e-9 and abs(value-baseline) >= 2.5*std:
                alerts.append(DriftAlert(metric,cid,value,baseline,"medium",f"{metric} 偏离近 {len(vals)} 章基线超过 2.5σ"))
    return alerts


def analytics_backend_capabilities() -> dict[str,bool]:
    return {
        "scikit_learn": importlib.util.find_spec("sklearn") is not None,
        "river": importlib.util.find_spec("river") is not None,
        "plotly": importlib.util.find_spec("plotly") is not None,
        "umap": importlib.util.find_spec("umap") is not None,
    }
