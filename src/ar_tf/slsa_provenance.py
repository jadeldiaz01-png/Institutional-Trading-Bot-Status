from __future__ import annotations
from typing import Any, Mapping

IN_TOTO_STATEMENT_V1="https://in-toto.io/Statement/v1"
SLSA_PROVENANCE_V1="https://slsa.dev/provenance/v1"
BUILD_TYPE="https://github.com/jadeldiaz01-png/Institutional-Trading-Bot-Status/blob/main/docs/AR_TF_SCIENTIFIC_BUILD_TYPE_V1.md"

def slsa_statement(*, subject_name:str, subject_sha256:str, builder_id:str, invocation_id:str,
                   external_parameters:Mapping[str,Any], resolved_dependencies:list[dict[str,Any]],
                   started_on:str|None=None, finished_on:str|None=None) -> dict[str,Any]:
    if len(subject_sha256)!=64: raise ValueError("subject sha256 required")
    metadata={"invocationId":invocation_id}
    if started_on: metadata["startedOn"]=started_on
    if finished_on: metadata["finishedOn"]=finished_on
    return {
      "_type":IN_TOTO_STATEMENT_V1,
      "subject":[{"name":subject_name,"digest":{"sha256":subject_sha256}}],
      "predicateType":SLSA_PROVENANCE_V1,
      "predicate":{
        "buildDefinition":{"buildType":BUILD_TYPE,"externalParameters":dict(external_parameters),
                           "internalParameters":{},"resolvedDependencies":resolved_dependencies},
        "runDetails":{"builder":{"id":builder_id},"metadata":metadata,"byproducts":[]},
      },
    }
