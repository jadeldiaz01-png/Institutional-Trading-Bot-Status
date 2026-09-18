from __future__ import annotations
import hashlib, json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

def _canon(v: Any) -> bytes:
    return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()

def sha256_bytes(b: bytes)->str: return hashlib.sha256(b).hexdigest()
def sha256_file(p: str|Path)->str:
    h=hashlib.sha256()
    with Path(p).open("rb") as f:
        for c in iter(lambda:f.read(1024*1024),b""): h.update(c)
    return h.hexdigest()

def merkle_root_hex(leaves: Iterable[str]) -> str:
    level=[bytes.fromhex(x) for x in leaves]
    if not level: raise ValueError("empty merkle tree")
    while len(level)>1:
        if len(level)%2: level.append(level[-1])
        level=[hashlib.sha256(level[i]+level[i+1]).digest() for i in range(0,len(level),2)]
    return level[0].hex()

def inventory(records:list[Mapping[str,Any]], *, identity_fields:tuple[str,...], expected_count:int)->dict[str,Any]:
    rows=[dict(r) for r in records]
    if len(rows)!=expected_count: raise ValueError(f"inventory count mismatch {len(rows)} != {expected_count}")
    ids=[tuple(r[k] for k in identity_fields) for r in rows]
    if len(ids)!=len(set(ids)): raise ValueError("duplicate inventory identity")
    for r in rows:
        d=str(r.get("sha256",""))
        if len(d)!=64: raise ValueError("inventory record missing sha256")
    rows.sort(key=lambda r: tuple(r[k] for k in identity_fields))
    inv_sha=sha256_bytes(_canon(rows))
    return {"count":len(rows),"inventory_sha256":inv_sha,"merkle_root":merkle_root_hex([r["sha256"] for r in rows]),"records":rows}

@dataclass(frozen=True)
class GateEvidence:
    gate_id:str
    passed:bool
    implementation_sha256:str
    input_sha256:tuple[str,...]
    metrics:Mapping[str,Any]
    thresholds:Mapping[str,Any]
    lineage:Mapping[str,str]
    def __post_init__(self):
        for d in (self.implementation_sha256,*self.input_sha256):
            if len(d)!=64: raise ValueError("gate evidence digest invalid")
    @property
    def evidence_sha256(self)->str:
        return sha256_bytes(_canon({"gate_id":self.gate_id,"passed":self.passed,
          "implementation_sha256":self.implementation_sha256,"input_sha256":self.input_sha256,
          "metrics":dict(self.metrics),"thresholds":dict(self.thresholds),"lineage":dict(self.lineage)}))
