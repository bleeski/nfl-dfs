"""The gate registry (Session 03b, R28): every blocker code's class, provenance and stops.

`config/gate_registry_v1.json` (`nfl_gate_registry_v1` in `docs/DATA_CONTRACTS.md`)
names every blocker code emitted under `src/nfl_dfs/` and gives it a family. A
family carries the metadata its codes share: the audit's class (`V`, `S`, `P`),
what a gate that fires stops, and the authority it answers to. This module loads
and validates that file and builds a `contracts.DeliveryLimitation` from a code.

Exactly three class and `stops` pairs exist, one per class of rule in `CLAUDE.md`:

- `V` stops the `FILE`: an integrity gate withholds the file, or the rows it
  names, because withholding is what keeps the boundary;
- `S` stops a `CONSTRUCTION_PREFERENCE`: relaxable under a lock clock;
- `P` stops `CERTIFICATION`: a truth claim or process prerequisite, which under
  R28 travels with the file as a named limitation.

Every entry in `codes` is one exact code, and a limitation is built only from an
exact code. An f-string code whose interpolation the source does not fix is a
template, with `*` for one or more upper-snake segments; it appears only as a
key of `expansions`, which lists the exact codes it produces. A template never
resolves a code itself, so no pattern can absorb a code nobody registered.

Nothing on the operating path reads this file yet; Sessions 04 to 09 build their
limitations through `GateRegistry.limitation`. It changes no gate's behaviour.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from pydantic import ValidationError

from .contracts import DeliveryLimitation, GateClass, GateProvenance, GateStops

SCHEMA_VERSION = "nfl_gate_registry_v1"
DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parents[2] / "config" / "gate_registry_v1.json"

# The only class and `stops` pairs a registry entry may carry (Session 03b).
ALLOWED_PAIRS: Mapping[GateClass, GateStops] = {
    GateClass.V: GateStops.FILE,
    GateClass.S: GateStops.CONSTRUCTION_PREFERENCE,
    GateClass.P: GateStops.CERTIFICATION,
}

_TOP_LEVEL = frozenset({"schema_version", "registered_at", "families", "codes", "expansions"})
_FAMILY_FIELDS = frozenset({"class", "stops", "provenance", "covers"})
_FAMILY_NAME = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*")
_CODE = re.compile(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+")
_TEMPLATE = re.compile(r"(?:[A-Z][A-Z0-9]*|\*)(?:_(?:[A-Z0-9]+|\*))+")


class GateRegistryError(ValueError):
    """The registry cannot be trusted, or it cannot name the code asked for."""


@dataclass(frozen=True)
class GateFamily:
    name: str
    gate_class: GateClass
    stops: GateStops
    provenance: GateProvenance
    covers: str


def template_bindings(template: str, code: str) -> Iterator[tuple[str, ...]]:
    """Every way `code` fills the `*` segments of `template`, one segment or more each."""

    pattern, parts = template.split("_"), code.split("_")

    def walk(i: int, j: int, bound: tuple[str, ...]) -> Iterator[tuple[str, ...]]:
        if i == len(pattern):
            if j == len(parts):
                yield bound
            return
        if pattern[i] != "*":
            if j < len(parts) and parts[j] == pattern[i]:
                yield from walk(i + 1, j + 1, bound)
            return
        for end in range(j + 1, len(parts) + 1):
            yield from walk(i + 1, end, bound + ("_".join(parts[j:end]),))

    yield from walk(0, 0, ())


def _matches(template: str, code: str) -> bool:
    return next(template_bindings(template, code), None) is not None


@dataclass(frozen=True)
class GateRegistry:
    sha256: str
    families: Mapping[str, GateFamily]
    codes: Mapping[str, str]
    expansions: Mapping[str, tuple[str, ...]]

    def family_of(self, code: str) -> GateFamily:
        """The family of an emitted code, looked up exactly."""

        if not isinstance(code, str) or not _CODE.fullmatch(code):
            raise GateRegistryError(f"GATE_REGISTRY_CODE_INVALID:{code!r}")
        name = self.codes.get(code)
        if name is None:
            raise GateRegistryError(f"GATE_REGISTRY_CODE_UNREGISTERED:{code}")
        return self.families[name]

    def limitation(
        self,
        code: str,
        *,
        entry_ids: Iterable[str] = (),
        people: Iterable[str] = (),
        detail: str = "",
    ) -> DeliveryLimitation:
        """A `DeliveryLimitation` for `code`, its class, stops and provenance from the registry."""

        family = self.family_of(code)
        return DeliveryLimitation(
            code=code,
            gate_class=family.gate_class,
            stops=family.stops,
            provenance=family.provenance,
            entry_ids=tuple(entry_ids),
            people=tuple(people),
            detail=detail,
        )


def _refuse_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    seen: dict[str, object] = {}
    for key, value in pairs:
        if key in seen:
            raise GateRegistryError(f"GATE_REGISTRY_DUPLICATE_KEY:{key}")
        seen[key] = value
    return seen


def _family(name: str, raw: object) -> GateFamily:
    if not _FAMILY_NAME.fullmatch(name):
        raise GateRegistryError(f"GATE_REGISTRY_FAMILY_INVALID:{name!r}")
    if not isinstance(raw, dict) or set(raw) != _FAMILY_FIELDS:
        raise GateRegistryError(f"GATE_REGISTRY_FAMILY_INVALID:{name}:fields={sorted(raw) if isinstance(raw, dict) else raw!r}")
    try:
        gate_class = GateClass(raw["class"])
        stops = GateStops(raw["stops"])
        provenance = GateProvenance.model_validate(raw["provenance"])
    except (ValueError, ValidationError) as exc:
        raise GateRegistryError(f"GATE_REGISTRY_FAMILY_INVALID:{name}:{exc}") from exc
    if not provenance.ref.strip():
        raise GateRegistryError(f"GATE_REGISTRY_FAMILY_INVALID:{name}:provenance ref is blank")
    if ALLOWED_PAIRS[gate_class] is not stops:
        raise GateRegistryError(
            f"GATE_REGISTRY_CLASS_STOPS_INVALID:{name}:{gate_class.value} stops "
            f"{ALLOWED_PAIRS[gate_class].value}, never {stops.value}"
        )
    covers = raw["covers"]
    if not isinstance(covers, str) or not covers.strip():
        raise GateRegistryError(f"GATE_REGISTRY_FAMILY_INVALID:{name}:covers is blank")
    return GateFamily(name, gate_class, stops, provenance, covers)


def parse_gate_registry(raw: bytes) -> GateRegistry:
    """Validate registry bytes: schema, class pairs, no duplicate, orphan or unused entry."""

    try:
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_refuse_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GateRegistryError(f"GATE_REGISTRY_JSON_INVALID:{exc}") from exc
    if not isinstance(payload, dict) or set(payload) != _TOP_LEVEL:
        raise GateRegistryError(f"GATE_REGISTRY_SCHEMA_INVALID:fields={sorted(payload) if isinstance(payload, dict) else payload!r}")
    if payload["schema_version"] != SCHEMA_VERSION:
        raise GateRegistryError(f"GATE_REGISTRY_SCHEMA_INVALID:schema_version={payload['schema_version']!r}")
    try:
        date.fromisoformat(payload["registered_at"])
    except (TypeError, ValueError) as exc:
        raise GateRegistryError(
            f"GATE_REGISTRY_SCHEMA_INVALID:registered_at={payload['registered_at']!r} is not a date"
        ) from exc
    families_raw, codes_raw, expansions_raw = payload["families"], payload["codes"], payload["expansions"]
    if not all(isinstance(part, dict) for part in (families_raw, codes_raw, expansions_raw)) or not families_raw:
        raise GateRegistryError("GATE_REGISTRY_SCHEMA_INVALID:families, codes and expansions are objects")
    families = {name: _family(name, raw_family) for name, raw_family in families_raw.items()}

    codes: dict[str, str] = {}
    for code, name in codes_raw.items():
        if not _CODE.fullmatch(code):
            raise GateRegistryError(f"GATE_REGISTRY_CODE_INVALID:{code!r} is not one exact code")
        if not isinstance(name, str) or name not in families:
            raise GateRegistryError(f"GATE_REGISTRY_FAMILY_UNKNOWN:{code}:{name!r}")
        codes[code] = name

    expansions: dict[str, tuple[str, ...]] = {}
    for template, listed in expansions_raw.items():
        if "*" not in template or not _TEMPLATE.fullmatch(template) or not re.search(r"[A-Z]", template):
            raise GateRegistryError(f"GATE_REGISTRY_EXPANSION_INVALID:{template!r} is not a template")
        if not isinstance(listed, list) or not listed or len(set(listed)) != len(listed):
            raise GateRegistryError(f"GATE_REGISTRY_EXPANSION_INVALID:{template}:codes must be a non-empty list without repeats")
        for code in listed:
            if not isinstance(code, str) or "*" in code or code not in codes or not _matches(template, code):
                raise GateRegistryError(f"GATE_REGISTRY_EXPANSION_INVALID:{template}:{code!r}")
        expansions[template] = tuple(listed)

    unused = sorted(set(families) - set(codes.values()))
    if unused:
        raise GateRegistryError(f"GATE_REGISTRY_FAMILY_UNUSED:{unused}")
    return GateRegistry(hashlib.sha256(raw).hexdigest(), families, codes, expansions)


def load_gate_registry(
    path: str | Path = DEFAULT_REGISTRY_PATH, *, expected_sha256: str | None = None
) -> GateRegistry:
    """Read, hash and validate the registry; refuse bytes other than `expected_sha256`."""

    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        raise GateRegistryError(f"GATE_REGISTRY_UNREADABLE:{path}:{exc}") from exc
    digest = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise GateRegistryError(f"GATE_REGISTRY_SHA256_MISMATCH:actual={digest}:expected={expected_sha256}")
    return parse_gate_registry(raw)
