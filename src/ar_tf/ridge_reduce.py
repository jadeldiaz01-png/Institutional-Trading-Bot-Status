from __future__ import annotations

from .classical_tournament import adjudicate_ridge_outputs
from .ridge_resume import validate_trials


def reduce_and_adjudicate(*,panel,registry,folds_path,structural_base,structural_stressed,structural_severe,shards):
    rb,rs,rv,failures=validate_trials(registry,shards)
    return adjudicate_ridge_outputs(
        panel=panel,folds_path=folds_path,
        structural_base=structural_base,structural_stressed=structural_stressed,structural_severe=structural_severe,
        ridge_base=rb,ridge_stressed=rs,ridge_severe=rv,ridge_failures=failures,
    )
