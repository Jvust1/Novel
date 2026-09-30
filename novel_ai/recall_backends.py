from __future__ import annotations
from dataclasses import dataclass
import importlib.util
from typing import Sequence
from .semantic import Encoder, vector_cosine

@dataclass(frozen=True)
class RecallHit:
    item_id: str
    score: float
    text: str

class LocalSemanticRecall:
    def __init__(self, encoder: Encoder):
        self.encoder=encoder; self.ids=[]; self.texts=[]; self.vectors=[]; self._faiss=None; self._index=None
    def add(self, ids: Sequence[str], texts: Sequence[str]) -> None:
        if len(ids)!=len(texts): raise ValueError("ids 与 texts 数量必须一致")
        if not ids: return
        rows=[list(map(float,row)) for row in self.encoder.encode(list(texts))]
        if self.vectors and rows and len(rows[0])!=len(self.vectors[0]): raise ValueError("embedding 维度发生变化")
        self.ids.extend(map(str,ids)); self.texts.extend(map(str,texts)); self.vectors.extend(rows); self._rebuild()
    def _rebuild(self) -> None:
        if not self.vectors or importlib.util.find_spec("faiss") is None: return
        try:
            import faiss, numpy as np
            matrix=np.asarray(self.vectors,dtype="float32"); faiss.normalize_L2(matrix)
            index=faiss.IndexFlatIP(matrix.shape[1]); index.add(matrix)
            self._faiss=faiss; self._index=index
        except Exception:
            self._faiss=None; self._index=None
    def search(self, query: str, k: int=5) -> list[RecallHit]:
        if not self.vectors: return []
        q=list(map(float,self.encoder.encode([query])[0])); k=max(1,min(int(k),len(self.ids)))
        if self._index is not None:
            import numpy as np
            matrix=np.asarray([q],dtype="float32"); self._faiss.normalize_L2(matrix)
            scores,idxs=self._index.search(matrix,k)
            return [RecallHit(self.ids[i],round(float(s),6),self.texts[i]) for s,i in zip(scores[0],idxs[0]) if i>=0]
        rows=[RecallHit(self.ids[i],vector_cosine(q,v),self.texts[i]) for i,v in enumerate(self.vectors)]
        return sorted(rows,key=lambda x:x.score,reverse=True)[:k]

def recall_backend_capabilities() -> dict[str,bool]:
    modules={"faiss":"faiss","qdrant":"qdrant_client","graphrag":"graphrag","lightrag":"lightrag","graphiti":"graphiti_core"}
    return {k: importlib.util.find_spec(v) is not None for k,v in modules.items()}
