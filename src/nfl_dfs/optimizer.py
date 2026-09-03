from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Iterable, Mapping

import highspy
import numpy as np

from .contracts import EngineMode, SalaryPlayer, SlateContract
from .lineups import ValidationResult, validate_lineup


@dataclass(frozen=True)
class SolverResult:
    status: str
    roster: tuple[str, ...] | None
    objective: float | None
    elapsed_seconds: float
    mip_gap: float | None
    node_count: int | None
    validation: ValidationResult | None


class LineupOptimizer:
    """Persistent direct-HiGHS lineup MILP with objective updates and MIP starts."""

    def __init__(
        self,
        slate: SlateContract,
        *,
        excluded_ids: Iterable[str] = (),
        time_limit_seconds: float = 5.0,
        mip_gap: float = 0.001,
    ) -> None:
        self.slate = slate
        self.players = list(slate.players)
        self.player_count = len(self.players)
        if not np.isfinite(time_limit_seconds) or time_limit_seconds <= 0:
            raise ValueError("time limit must be positive and finite")
        if not np.isfinite(mip_gap) or not 0 <= mip_gap <= 1:
            raise ValueError("MIP gap must be finite and inside [0,1]")
        excluded = set(excluded_ids)
        unknown_excluded = excluded.difference(player.dk_id for player in self.players)
        if unknown_excluded:
            raise ValueError(f"excluded IDs are outside the salary pool: {sorted(unknown_excluded)}")
        self._highs = highspy.Highs()
        self._highs.setOptionValue("output_flag", False)
        self._highs.setOptionValue("time_limit", float(time_limit_seconds))
        self._highs.setOptionValue("mip_rel_gap", float(mip_gap))
        self._highs.setOptionValue("random_seed", 0)
        self._last_selected: np.ndarray | None = None
        self._build(excluded)

    def _add_row(self, lower: float, upper: float, coefficients: Mapping[int, float]) -> None:
        indices = np.array(list(coefficients), dtype=np.int32)
        values = np.array([coefficients[index] for index in indices], dtype=np.float64)
        self._highs.addRow(lower, upper, len(indices), indices, values)

    def _build(self, excluded_ids: set[str]) -> None:
        game_ids = sorted({player.game_id for player in self.players})
        game_offset = self.player_count
        game_var = {game: game_offset + i for i, game in enumerate(game_ids)}
        team_ids = sorted({player.team for player in self.players})
        team_offset = game_offset + len(game_ids)
        team_var = {team: team_offset + i for i, team in enumerate(team_ids)}
        variable_count = team_offset + len(team_ids)
        lower = np.zeros(variable_count, dtype=np.float64)
        upper = np.ones(variable_count, dtype=np.float64)
        self._highs.addVars(variable_count, lower, upper)
        indices = np.arange(variable_count, dtype=np.int32)
        integrality = np.full(variable_count, highspy.HighsVarType.kInteger)
        self._highs.changeColsIntegrality(variable_count, indices, integrality)
        self._highs.changeObjectiveSense(highspy.ObjSense.kMaximize)

        for index, player in enumerate(self.players):
            if player.dk_id in excluded_ids:
                self._add_row(0.0, 0.0, {index: 1.0})
        self._add_row(
            -highspy.kHighsInf,
            float(self.slate.salary_cap),
            {i: float(player.salary) for i, player in enumerate(self.players)},
        )
        roster_size = 9 if self.slate.mode is EngineMode.CLASSIC else 6
        self._add_row(
            float(roster_size), float(roster_size), {i: 1.0 for i in range(self.player_count)}
        )

        if self.slate.mode is EngineMode.CLASSIC:
            position_bounds = {
                "QB": (1, 1),
                "RB": (2, 3),
                "WR": (3, 4),
                "TE": (1, 2),
                "DST": (1, 1),
            }
            for position, (minimum, maximum) in position_bounds.items():
                self._add_row(
                    float(minimum),
                    float(maximum),
                    {
                        i: 1.0
                        for i, player in enumerate(self.players)
                        if player.position == position
                    },
                )
            for game, y_index in game_var.items():
                player_indices = [
                    i for i, player in enumerate(self.players) if player.game_id == game
                ]
                self._add_row(
                    0.0,
                    highspy.kHighsInf,
                    {**{i: 1.0 for i in player_indices}, y_index: -1.0},
                )
                for player_index in player_indices:
                    self._add_row(-highspy.kHighsInf, 0.0, {player_index: 1.0, y_index: -1.0})
            self._add_row(
                2.0, highspy.kHighsInf, {index: 1.0 for index in game_var.values()}
            )
        else:
            self._add_row(
                1.0,
                1.0,
                {i: 1.0 for i, player in enumerate(self.players) if player.role == "CPT"},
            )
            self._add_row(
                5.0,
                5.0,
                {i: 1.0 for i, player in enumerate(self.players) if player.role == "FLEX"},
            )
            people: dict[str, list[int]] = {}
            for index, player in enumerate(self.players):
                people.setdefault(player.underlying_id, []).append(index)
            for role_indices in people.values():
                self._add_row(
                    -highspy.kHighsInf,
                    1.0,
                    {index: 1.0 for index in role_indices},
                )
            for team, y_index in team_var.items():
                player_indices = [i for i, player in enumerate(self.players) if player.team == team]
                self._add_row(
                    0.0,
                    highspy.kHighsInf,
                    {**{i: 1.0 for i in player_indices}, y_index: -1.0},
                )
                for player_index in player_indices:
                    self._add_row(-highspy.kHighsInf, 0.0, {player_index: 1.0, y_index: -1.0})
            self._add_row(
                2.0, highspy.kHighsInf, {index: 1.0 for index in team_var.values()}
            )

    def update_objective(self, scores: Mapping[str, float]) -> None:
        unknown = set(scores).difference(player.dk_id for player in self.players)
        if unknown:
            raise ValueError(f"objective IDs are outside the salary pool: {sorted(unknown)[:10]}")
        costs = np.array([float(scores.get(player.dk_id, 0.0)) for player in self.players])
        if not np.isfinite(costs).all():
            raise ValueError("objective scores must be finite")
        indices = np.arange(self.player_count, dtype=np.int32)
        self._highs.changeColsCost(self.player_count, indices, costs)

    def add_no_good(self, roster: Iterable[str]) -> None:
        selected = {str(dk_id) for dk_id in roster}
        unknown = selected.difference(player.dk_id for player in self.players)
        if unknown:
            raise ValueError(f"no-good roster IDs are outside the salary pool: {sorted(unknown)}")
        indices = [i for i, player in enumerate(self.players) if player.dk_id in selected]
        if indices:
            self._add_row(-highspy.kHighsInf, float(len(indices) - 1), {i: 1.0 for i in indices})

    def solve(self, scores: Mapping[str, float]) -> SolverResult:
        started = time.perf_counter()
        self.update_objective(scores)
        if self._last_selected is not None and len(self._last_selected):
            self._highs.setSolution(
                len(self._last_selected),
                self._last_selected,
                np.ones(len(self._last_selected), dtype=np.float64),
            )
        self._highs.run()
        elapsed = time.perf_counter() - started
        model_status = self._highs.getModelStatus()
        info = self._highs.getInfo()
        solution = self._highs.getSolution()
        feasible = bool(solution.value_valid) and model_status not in {
            highspy.HighsModelStatus.kInfeasible,
            highspy.HighsModelStatus.kUnboundedOrInfeasible,
        }
        if not feasible:
            return SolverResult(
                "INFEASIBLE" if model_status == highspy.HighsModelStatus.kInfeasible else "NO_SOLUTION",
                None,
                None,
                elapsed,
                None,
                None,
                None,
            )
        selected = np.flatnonzero(np.asarray(solution.col_value[: self.player_count]) > 0.5).astype(
            np.int32
        )
        self._last_selected = selected
        chosen = [self.players[index] for index in selected]
        roster = self._slot_roster(chosen)
        validation = validate_lineup(self.slate, roster)
        if not validation.valid:
            return SolverResult(
                "NO_SOLUTION",
                roster,
                None,
                elapsed,
                float(info.mip_gap) if np.isfinite(info.mip_gap) else None,
                int(info.mip_node_count),
                validation,
            )
        status = "OPTIMAL" if model_status == highspy.HighsModelStatus.kOptimal else "FEASIBLE_LIMIT"
        objective = sum(float(scores.get(player.dk_id, 0.0)) for player in chosen)
        return SolverResult(
            status,
            roster,
            objective,
            elapsed,
            float(info.mip_gap) if np.isfinite(info.mip_gap) else None,
            int(info.mip_node_count),
            validation,
        )

    def _slot_roster(self, chosen: list[SalaryPlayer]) -> tuple[str, ...]:
        if self.slate.mode is EngineMode.SHOWDOWN:
            captain = next(player for player in chosen if player.role == "CPT")
            flex = sorted(
                (player for player in chosen if player.role == "FLEX"),
                key=lambda player: (player.position, player.name, player.dk_id),
            )
            return (captain.dk_id,) + tuple(player.dk_id for player in flex)
        positions: dict[str, list[SalaryPlayer]] = {
            position: sorted(
                [player for player in chosen if player.position == position],
                key=lambda player: (-player.salary, player.name, player.dk_id),
            )
            for position in ("QB", "RB", "WR", "TE", "DST")
        }
        roster: list[str] = []
        roster.append(positions["QB"].pop(0).dk_id)
        roster.extend(positions["RB"].pop(0).dk_id for _ in range(2))
        roster.extend(positions["WR"].pop(0).dk_id for _ in range(3))
        roster.append(positions["TE"].pop(0).dk_id)
        flex = [player for position in ("RB", "WR", "TE") for player in positions[position]]
        if len(flex) != 1:
            raise RuntimeError("Classic MILP did not produce exactly one FLEX")
        roster.append(flex[0].dk_id)
        roster.append(positions["DST"].pop(0).dk_id)
        return tuple(roster)


def generate_candidates(
    slate: SlateContract,
    objectives: Iterable[Mapping[str, float]],
    *,
    maximum: int,
    excluded_ids: Iterable[str] = (),
    per_solve_seconds: float = 3.0,
) -> tuple[SolverResult, ...]:
    if maximum < 1:
        return ()
    optimizer = LineupOptimizer(
        slate, excluded_ids=excluded_ids, time_limit_seconds=per_solve_seconds
    )
    results: list[SolverResult] = []
    seen: set[tuple[str, ...]] = set()
    objective_list = list(objectives)
    if not objective_list:
        raise ValueError("at least one candidate objective is required")
    cycle = 0
    while len(results) < maximum:
        base = objective_list[cycle % len(objective_list)]
        # Deterministic vanishing perturbation diversifies repeated objective families.
        scores = {
            player.dk_id: float(base.get(player.dk_id, 0.0))
            + 1e-6 * ((cycle + 1) * (index + 17) % 997)
            for index, player in enumerate(slate.players)
        }
        result = optimizer.solve(scores)
        if result.roster is None or result.status in {"INFEASIBLE", "NO_SOLUTION"}:
            break
        if result.roster not in seen:
            results.append(result)
            seen.add(result.roster)
        optimizer.add_no_good(result.roster)
        cycle += 1
    return tuple(results)
