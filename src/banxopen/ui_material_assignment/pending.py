"""The pending list: changes staged in the dialog and not yet applied to the part.

A body is claimed by at most one entry; the latest action replaces an earlier claim. There is at most one removal
entry. A body Apply could not change stays in its entry as NOT_APPLIED, with the reason.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from enum import Enum

from banxopen.foundation import BodyId, BodyInfo
from banxopen.materials import BodyVerdict, Material, VerdictStatus
from banxopen.sheetmetal import PendingSheetMetal, SheetMetalMaterialRow


class PendingBodyStatus(Enum):
    """What the rules said about one body when it was staged, or NOT_APPLIED when Apply left it behind."""

    OK = "ok"
    NEEDS_CONFIRMATION = "needs_confirmation"
    BLOCKED = "blocked"
    NOT_APPLIED = "not_applied"


_FROM_VERDICT = {
    VerdictStatus.OK: PendingBodyStatus.OK,
    VerdictStatus.NEEDS_CONFIRMATION: PendingBodyStatus.NEEDS_CONFIRMATION,
    VerdictStatus.BLOCKED: PendingBodyStatus.BLOCKED,
}


@dataclass(frozen=True, slots=True)
class PendingBodyRow:
    body: BodyInfo
    status: PendingBodyStatus
    message: str | None = None
    """The rules' wording (a warning, or what needs confirming), or why Apply did not change the body."""

    @staticmethod
    def of(verdict: BodyVerdict) -> PendingBodyRow:
        return PendingBodyRow(verdict.body, _FROM_VERDICT[verdict.status], verdict.message)

    def not_applied(self, reason: str | None) -> PendingBodyRow:
        return dataclasses.replace(self, status=PendingBodyStatus.NOT_APPLIED, message=reason)


# eq=False: an entry is identified by the object, so "remove this entry" never removes an equal-looking other one.
@dataclass(frozen=True, slots=True, eq=False)
class PendingRemoval:
    """Remove the material from these bodies."""

    rows: tuple[PendingBodyRow, ...]
    confirmed: frozenset[BodyId] = frozenset()

    @property
    def body_ids(self) -> tuple[BodyId, ...]:
        return tuple(r.body.id for r in self.rows)


@dataclass(frozen=True, slots=True, eq=False)
class PendingAssignment:
    """Assign `material` (with the sheet metal `row` picked with it, or None) to these bodies. Only bodies that will be
    assigned are staged; Apply re-plans against the part as it then stands, reusing `confirmed`."""

    material: Material
    row: SheetMetalMaterialRow | None
    rows: tuple[PendingBodyRow, ...]
    confirmed: frozenset[BodyId] = frozenset()
    """Bodies whose rules asked for confirmation and the user said yes, so Apply does not ask again."""

    @property
    def body_ids(self) -> tuple[BodyId, ...]:
        return tuple(r.body.id for r in self.rows)

    def is_confirmed(self, row: PendingBodyRow) -> bool:
        return row.status is PendingBodyStatus.NEEDS_CONFIRMATION and row.body.id in self.confirmed


PendingEntry = PendingRemoval | PendingAssignment


def claims_by_body(entries: Iterable[PendingEntry]) -> dict[BodyId, PendingEntry]:
    """The entry each pending body is claimed by."""
    return {row.body.id: entry for entry in entries for row in entry.rows}


def without_bodies(entries: Iterable[PendingEntry], body_ids: Collection[BodyId]) -> list[PendingEntry]:
    """`entries` with `body_ids` taken out, dropping any entry left with no body. Not re-planned: Apply re-plans."""
    if not body_ids:
        return list(entries)
    kept: list[PendingEntry] = []
    for entry in entries:
        rows = tuple(r for r in entry.rows if r.body.id not in body_ids)
        if rows:
            kept.append(entry if len(rows) == len(entry.rows) else dataclasses.replace(entry, rows=rows))
    return kept


def removal_of(entries: Sequence[PendingEntry]) -> PendingRemoval | None:
    return next((e for e in entries if isinstance(e, PendingRemoval)), None)


def for_sheet_metal(entries: Iterable[PendingEntry]) -> tuple[PendingSheetMetal, ...]:
    """The pending list as the sheet metal conflict check sees it: a removal leaves its bodies with no material."""
    return tuple(
        PendingSheetMetal(e.body_ids, None)
        if isinstance(e, PendingRemoval)
        else PendingSheetMetal(e.body_ids, e.material.name, e.row)
        for e in entries
    )
