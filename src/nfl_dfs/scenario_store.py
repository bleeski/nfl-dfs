from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from .hashing import sha256_file
from .simulation import SimulationResult


def save_scenario_bank(result: SimulationResult, directory: str | Path) -> dict[str, str | int]:
    target_dir = Path(directory).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    columns = {
        person_id: pa.array(result.outcomes[:, index])
        for index, person_id in enumerate(result.person_ids)
    }
    columns["__weight__"] = pa.array(result.weights.astype(np.float64))
    table = pa.table(columns)
    metadata = {
        b"purpose": result.purpose.encode(),
        b"seed": str(result.seed).encode(),
        b"diagnostics": json.dumps(result.diagnostics, sort_keys=True).encode(),
    }
    table = table.replace_schema_metadata(metadata)
    path = target_dir / f"{result.purpose.lower()}_{result.seed}_{len(result.weights)}.parquet"
    if path.exists():
        raise FileExistsError(f"scenario bank already exists and is immutable: {path}")
    pq.write_table(table, path, compression="zstd", use_dictionary=False)
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "scenario_count": len(result.weights),
        "person_count": len(result.person_ids),
    }


def load_scenario_bank(path: str | Path) -> tuple[tuple[str, ...], np.ndarray, np.ndarray, dict]:
    table = pq.read_table(path)
    person_ids = tuple(name for name in table.column_names if name != "__weight__")
    outcomes = np.column_stack(
        [table[name].to_numpy(zero_copy_only=False) for name in person_ids]
    ).astype(np.float32)
    weights = table["__weight__"].to_numpy(zero_copy_only=False).astype(np.float64)
    metadata = table.schema.metadata or {}
    diagnostics = json.loads(metadata.get(b"diagnostics", b"{}").decode())
    return person_ids, outcomes, weights, diagnostics
