from __future__ import annotations

from .contracts import WorkflowState


class LifecycleError(ValueError):
    pass


_TRANSITIONS: dict[WorkflowState, set[WorkflowState]] = {
    WorkflowState.NEW: {WorkflowState.SNAPSHOTTED},
    WorkflowState.SNAPSHOTTED: {WorkflowState.RECONCILED, WorkflowState.DO_NOT_UPLOAD},
    WorkflowState.RECONCILED: {WorkflowState.MODELLED, WorkflowState.DO_NOT_UPLOAD},
    WorkflowState.MODELLED: {WorkflowState.CANDIDATES_READY, WorkflowState.DO_NOT_UPLOAD},
    WorkflowState.CANDIDATES_READY: {WorkflowState.SELECTED, WorkflowState.DO_NOT_UPLOAD},
    WorkflowState.SELECTED: {WorkflowState.QA_REVIEWED, WorkflowState.DO_NOT_UPLOAD},
    WorkflowState.QA_REVIEWED: {WorkflowState.CERTIFIED, WorkflowState.DO_NOT_UPLOAD},
    WorkflowState.CERTIFIED: {WorkflowState.LOCKED, WorkflowState.DO_NOT_UPLOAD},
    WorkflowState.DO_NOT_UPLOAD: set(),
    WorkflowState.LOCKED: {WorkflowState.SETTLED},
    WorkflowState.SETTLED: {WorkflowState.GRADED},
    WorkflowState.GRADED: set(),
}


def transition(current: WorkflowState, target: WorkflowState) -> WorkflowState:
    if target not in _TRANSITIONS[current]:
        raise LifecycleError(f"illegal workflow transition: {current.value} -> {target.value}")
    return target


def invalidate_certification(current: WorkflowState) -> WorkflowState:
    if current is WorkflowState.CERTIFIED:
        return WorkflowState.DO_NOT_UPLOAD
    return current
