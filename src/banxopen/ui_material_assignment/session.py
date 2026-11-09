"""The Material Assignment dialog's state and gestures, NX-free.

Changes are staged. "Add to pending" and "Remove material" only list the change in the pending list; the part is not
touched, so the current-assignment tree keeps showing what the bodies really have. A body has at most one pending
change, and the latest action replaces an earlier one. Apply/OK apply the pending list, and Apply is final: whatever
does not apply stays pending with the reason. Cancel, "Remove from pending" and "Clear all pending" only drop entries.
The decision tree is in README.md.

What a rule allows, what needs confirming, the sheet metal conflict and every per-body reason come from the libraries
(`MaterialAssignmentService`, `SheetMetalAssignmentSupport`) and are shown as they word them. What is left here is the
pending list itself: what is staged, replaced and reported, which is this dialog's design.
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

from banxopen.foundation import BodyId, BodyInfo, BodyKind, OperationResult
from banxopen.materials import (
    AssignmentReport,
    BodyMaterialAssignment,
    Material,
    MaterialAssignmentService,
    MaterialCategoryNode,
    MaterialLibrary,
    MaterialLibraryId,
    MaterialLibraryReference,
    MaterialsCodes,
    MaterialsText,
    OutcomeStatus,
)
from banxopen.sheetmetal import (
    NO_FILTER,
    BodyCheck,
    SheetMetalAssignmentSupport,
    SheetMetalMaterialRow,
    SheetMetalPartPreference,
    SheetMetalPreferenceCheckResult,
    SheetMetalPreferenceStatus,
    SheetMetalRowFilter,
    SheetMetalStandardSelection,
    SheetMetalText,
    SyncAction,
    thickness_matches,
)
from banxopen.ui_material_assignment.pending import (
    PendingAssignment,
    PendingBodyRow,
    PendingBodyStatus,
    PendingEntry,
    PendingRemoval,
    claims_by_body,
    for_sheet_metal,
    removal_of,
    without_bodies,
)
from banxopen.ui_material_assignment.text import UiText

_log = logging.getLogger(__name__)


class Dialogs(Protocol):
    """How the session talks to the user. `NxMessenger` is one."""

    def show_result(self, result: OperationResult[Any], success_message: str | None = None) -> None: ...
    def ask(self, question: str) -> bool: ...
    def show_error(self, message: str) -> None: ...
    def show_info(self, title: str, message: str) -> None: ...


class SheetMetalPort(Protocol):
    """What the dialog uses of `banxopen.sheetmetal.nx.SheetMetalServices`."""

    @property
    def standard_selection(self) -> SheetMetalStandardSelection: ...
    def read_part_preference(self) -> SheetMetalPartPreference | None: ...
    def body_thickness_of(self, body_id: BodyId) -> float | None: ...
    def set_preferences(self, row: SheetMetalMaterialRow) -> OperationResult[str]: ...


@dataclass(frozen=True, slots=True)
class AssignmentServices:
    materials: MaterialAssignmentService
    sheet_metal: SheetMetalPort
    support: SheetMetalAssignmentSupport
    is_sheet_metal_application: bool
    materials_text: MaterialsText = field(default_factory=lambda: MaterialsText.DEFAULT)
    sheet_metal_text: SheetMetalText = field(default_factory=lambda: SheetMetalText.DEFAULT)


@dataclass(frozen=True, slots=True)
class MaterialPick:
    """A material tree row: a physical material, or one of its rows in the sheet metal standards file, which is what
    the part's Sheet Metal Preferences are set to. A row carries the physical material it is made of, since that is
    what the bodies are assigned."""

    material: Material
    row: SheetMetalMaterialRow | None = None

    @property
    def display_name(self) -> str:
        return self.row.name if self.row is not None else self.material.name


class Section(Enum):
    """What a gesture changed, so the dialog redraws only that (a rebuilt tree loses its selection)."""

    LIBRARIES = "libraries"
    FILTERS = "filters"
    MATERIALS = "materials"
    ASSIGNMENTS = "assignments"
    PENDING = "pending"


def same_name(a: str | None, b: str | None) -> bool:
    return a is not None and b is not None and a.casefold() == b.casefold()


class AssignmentSession:
    """One dialog session. Every gesture says what it shows through `Dialogs` and records what it changed (see
    `take_changes`); the presenter redraws from the properties below."""

    def __init__(self, services: AssignmentServices, dialogs: Dialogs, text: UiText | None = None) -> None:
        self._materials = services.materials
        self._sheet_metal = services.sheet_metal
        self._support = services.support
        self._is_sheet_metal_application = services.is_sheet_metal_application
        self._materials_text = services.materials_text
        self._sheet_metal_text = services.sheet_metal_text
        self._dialogs = dialogs
        self.text = text or UiText.DEFAULT
        self.support = services.support
        self.show_grade_column = services.is_sheet_metal_application
        """The current-assignment tree's SheetMetal Grade column: in the NX Sheet Metal application only."""

        self.libraries: tuple[MaterialLibraryReference, ...] = ()
        self.current_reference: MaterialLibraryReference | None = None
        self.library: MaterialLibrary | None = None
        self.selected_pick: MaterialPick | None = None

        # Only meaningful while a sheet metal library is selected: the standards file rows made of its materials, the
        # filters the user set on them, and the rows those filters leave.
        self.is_sheet_metal_library = False
        self.library_rows: tuple[SheetMetalMaterialRow, ...] = ()
        self.filter: SheetMetalRowFilter = NO_FILTER
        self.filtered_rows: tuple[SheetMetalMaterialRow, ...] = ()

        self.bodies: tuple[BodyInfo, ...] = ()
        self.assignments: dict[BodyId, BodyMaterialAssignment] = {}
        self.part_preference: SheetMetalPartPreference | None = None
        """Re-read with the bodies. None outside sheet metal parts."""
        self.preference_checks: dict[BodyId, SheetMetalPreferenceCheckResult] = {}
        """How each sheet metal body stands against `part_preference`."""

        self.pending: list[PendingEntry] = []
        """At most one PendingRemoval (first), any number of PendingAssignment; each body in at most one entry."""

        self._filter_seeded = False
        self._initial_sync_checked = False
        self._changes: set[Section] = set()

    # ---- What changed ----

    def take_changes(self) -> set[Section]:
        changes, self._changes = self._changes, set()
        return changes

    def _changed(self, *sections: Section) -> None:
        self._changes.update(sections)

    # ---- Lifecycle ----

    def show(self) -> None:
        """The dialog was shown. This may fire again on a tab switch, so the library and filters in use are kept."""
        self.libraries = tuple(self._materials.list_libraries())
        self._changed(Section.LIBRARIES)
        self._refresh_body_state()
        if self.libraries:
            current = self.current_reference
            keep = current is not None and any(r.id == current.id for r in self.libraries)
            self.select_library(current.id if keep and current is not None else self.libraries[0].id)

    @property
    def selected_library_index(self) -> int | None:
        current = self.current_reference
        if current is None:
            return None
        return next((i for i, r in enumerate(self.libraries) if r.id == current.id), None)

    def apply(self, selected_ids: Sequence[BodyId]) -> bool:
        """Apply. With nothing pending and a sheet metal material picked, applies that instead. False keeps the dialog
        from treating it as done."""
        if self.pending:
            self._commit()
            return True
        pick = self.picked_sheet_metal_material()
        if pick is not None:
            return self._apply_picked(pick, selected_ids)
        self._dialogs.show_error(self.text.nothing_pending(self.is_sheet_metal_library))
        return False

    def ok(self, selected_ids: Sequence[BodyId]) -> bool:
        """OK: True lets the dialog close. An empty pending list is a normal end. A picked sheet metal material is
        applied as Apply would when it has somewhere to go; with bodies in the part but none selected there is nothing
        for it to go on, so OK just closes. Anything left pending keeps the dialog open, to show what did not apply."""
        if self.pending:
            return self._commit()
        pick = self.picked_sheet_metal_material()
        if pick is not None and (selected_ids or not self.part_has_solid):
            return self._apply_picked(pick, selected_ids)
        return True

    def cancel(self) -> bool:
        """Cancel or close: True lets the dialog close. Apply is final, so nothing applied is reverted; pending changes
        were never applied, so they are discarded after a warning."""
        if self.pending and not self._dialogs.ask(self.text.discard_pending(len(self.pending))):
            return False
        self.pending.clear()
        return True

    def refresh(self) -> None:
        """Re-reads the part. Pending entries only lose bodies that are gone; Apply re-plans the rest."""
        self._refresh_body_state()
        present = {b.id for b in self.bodies}
        gone = [i for e in self.pending for i in e.body_ids if i not in present]
        self.pending = without_bodies(self.pending, set(gone))
        self._changed(Section.PENDING, Section.ASSIGNMENTS)

    # ---- Library and material browsing ----

    def select_library(self, library_id: MaterialLibraryId | None) -> None:
        reference = next((r for r in self.libraries if r.id == library_id), None)
        if reference is None:
            return
        self.current_reference = reference
        self.library = self._materials.load_library(reference)
        # The Sheet Metal Preferences only mean anything for materials that can go on sheet metal bodies.
        self.is_sheet_metal_library = self._materials.is_sheet_metal_library(reference.id)
        self.library_rows = (
            self._support.rows_for_library(m.name for m in self.library.materials)
            if self.is_sheet_metal_library
            else ()
        )
        # The first sheet metal library starts from the part's own preferences row; after that the user's filters
        # stand.
        if self.is_sheet_metal_library and not self._filter_seeded:
            preference = self.part_preference
            in_use = preference if preference is not None and preference.is_material_table_entry else None
            self.filter = self._support.default_filter(in_use, self.library_rows)
            self._filter_seeded = True
        self._refresh_material_tree()
        # Resolution against the new library can change which bodies have a resolved material.
        self._changed(Section.FILTERS, Section.ASSIGNMENTS)

    def set_filter(self, row_filter: SheetMetalRowFilter) -> None:
        """Pending entries keep the row they were staged with; only what can be picked next changes."""
        self.filter = row_filter
        self._refresh_material_tree()

    def clear_filter(self) -> None:
        self.set_filter(NO_FILTER)

    def material_tree(self) -> tuple[tuple[MaterialCategoryNode, ...], Mapping[str, tuple[SheetMetalMaterialRow, ...]]]:
        """The categories to show and, for a sheet metal library, the rows to list under each physical material (by
        case-folded name). With no filter every physical material is listed, so one with no row can still go on a plain
        solid; with a filter, only the materials that still have a row are."""
        library = self.library
        if library is None:
            return (), {}
        if not self.is_sheet_metal_library:
            return self._materials.category_tree(library), {}
        rows_by_material: dict[str, list[SheetMetalMaterialRow]] = {}
        for row in self.filtered_rows:
            rows_by_material.setdefault(row.physical_material_name.casefold(), []).append(row)
        materials = (
            library.materials
            if self.filter.is_empty
            else tuple(m for m in library.materials if m.name.casefold() in rows_by_material)
        )
        categories = self._materials.category_tree(dataclasses.replace(library, materials=materials))
        return categories, {k: tuple(v) for k, v in rows_by_material.items()}

    def pick(self, pick: MaterialPick | None) -> None:
        self.selected_pick = pick

    def material_named(self, name: str | None) -> Material | None:
        library = self.library
        if library is None or name is None:
            return None
        return next((m for m in library.materials if same_name(m.name, name)), None)

    def picked_sheet_metal_material(self) -> MaterialPick | None:
        """What Apply/OK act on when nothing is pending: the row selected in the material tree, else the only row the
        filters leave. None outside a sheet metal library, or when no single row is picked."""
        if not self.is_sheet_metal_library or self.library is None:
            return None
        if self.selected_pick is not None and self.selected_pick.row is not None:
            return self.selected_pick
        if len(self.filtered_rows) != 1:
            return None
        row = self.filtered_rows[0]
        material = self.material_named(row.physical_material_name)
        return MaterialPick(material, row) if material is not None else None

    def _refresh_material_tree(self) -> None:
        if self.library is None:
            return
        if not self.is_sheet_metal_library:
            self.filtered_rows = ()
        else:
            # A value the other filters no longer allow falls back to "(Any)".
            self.filter = normalized(self.filter, self.library_rows)
            # The row rule follows the Standard, so the rows it offers are the rows the tree shows.
            self._sheet_metal.standard_selection.selected = self.filter.standard
            self.filtered_rows = self.filter.apply(self.library_rows)
        # A rebuilt tree invalidates the previously picked material.
        self.selected_pick = None
        self._changed(Section.MATERIALS, Section.FILTERS)

    # ---- Quick selection ----

    @property
    def part_has_solid(self) -> bool:
        return any(self._support.is_solid(b) for b in self.bodies)

    def all_solids(self) -> tuple[BodyId, ...]:
        return tuple(b.id for b in self.bodies if self._support.is_solid(b))

    def unassigned_solids(self) -> tuple[BodyId, ...] | None:
        """None, after saying so, when every solid already has a material."""
        unassigned = {a.body_id for a in self.assignments.values() if a.material_name is None}
        ids = tuple(b.id for b in self.bodies if self._support.is_solid(b) and b.id in unassigned)
        if not ids:
            self._dialogs.show_error(self.text.every_solid_has_material)
            return None
        return ids

    def with_solids_added(
        self, bodies: Iterable[BodyInfo], selected_ids: Sequence[BodyId]
    ) -> tuple[BodyId, ...] | None:
        """The selection with the solid bodies among `bodies` added; None, after saying so, when there are none."""
        solids = [b.id for b in bodies if self._support.is_solid(b)]
        if not solids:
            self._dialogs.show_error(self.text.no_solid_body_in_rows)
            return None
        return tuple(dict.fromkeys([*selected_ids, *solids]))

    # ---- Staging an assignment ----

    def stage(self, pick: MaterialPick, selected_ids: Sequence[BodyId]) -> bool:
        """Plans the selected bodies against `pick`, asks the confirmations its rules need, and adds what will be
        assigned to the pending list. A body that already has the material is not staged, and an earlier pending
        change to it is dropped: assigning what it has means leaving it as it is. Blocked and declined bodies are
        reported, not staged, and keep any earlier pending claim. Only the staged bodies leave their earlier entry, so
        a body is never claimed twice. False when nothing was staged."""
        targets = self._selected_targets(selected_ids)
        if targets is None:
            return False
        text = self._materials_text
        claims = claims_by_body(self.pending)
        already = [b for b in targets if self._already_has(b, pick)]
        not_staged = [
            text.body_line(
                b.name,
                self.text.already_has(pick.material.name)
                + (self.text.earlier_pending_change_removed_suffix if b.id in claims else ""),
            )
            for b in already
        ]
        if already:
            self.pending = without_bodies(self.pending, {b.id for b in already})
        remaining = [b for b in targets if b not in already]
        staged: PendingAssignment | None = None
        replaced: list[str] = []
        warnings: list[str] = []

        if remaining:
            entry = self._checked_entry(pick, remaining)
            if entry is None:
                self._changed(Section.PENDING, Section.ASSIGNMENTS)
                return False
            confirmed = self._ask_confirmations(entry)
            not_staged += [
                text.body_line(r.body.name, text.blocked(r.message))
                for r in entry.rows
                if r.status is PendingBodyStatus.BLOCKED
            ]
            not_staged += [
                text.body_line(r.body.name, self.text.skipped_not_confirmed)
                for r in entry.rows
                if r.status is PendingBodyStatus.NEEDS_CONFIRMATION and r.body.id not in confirmed
            ]
            rows = tuple(
                r
                for r in entry.rows
                if r.status is PendingBodyStatus.OK
                or (r.status is PendingBodyStatus.NEEDS_CONFIRMATION and r.body.id in confirmed)
            )
            if rows:
                staged = dataclasses.replace(entry, rows=rows, confirmed=frozenset(confirmed))
                # A pending removal being replaced is worth saying: the user may not expect the body to keep a material.
                replaced = [
                    text.body_line(r.body.name, self.text.pending_removal_replaced)
                    for r in rows
                    if isinstance(claims.get(r.body.id), PendingRemoval)
                ]
                self.pending = [*without_bodies(self.pending, set(staged.body_ids)), staged]
                # Warnings never stop an assignment, but they are the only thing the user would otherwise never see.
                warnings = [
                    text.body_line(r.body.name, r.message)
                    for r in rows
                    if r.status is PendingBodyStatus.OK and r.message and r.message.strip()
                ]

        self._report_staging(pick.display_name, staged, not_staged, replaced, warnings, only_already=not remaining)
        self._changed(Section.PENDING, Section.ASSIGNMENTS)
        return staged is not None

    def _already_has(self, body: BodyInfo, pick: MaterialPick) -> bool:
        """True when assigning `pick` would change nothing: the body has the material and, for a sheet metal body with
        a row picked, the part's preferences already are that row."""
        if not same_name(self._material_of(body.id), pick.material.name):
            return False
        row = pick.row
        if row is None or body.kind is not BodyKind.SHEET_METAL:
            return True
        current = self.part_preference.row if self.part_preference is not None else None
        return current is not None and same_name(current.name, row.name)

    def _checked_entry(self, pick: MaterialPick, targets: Sequence[BodyInfo]) -> PendingAssignment | None:
        """Plans `targets`, and refuses a sheet metal body with no row picked, or a second sheet metal material, before
        anything is staged. None, after saying why, when the entry is refused."""
        entry = self._plan(pick.material, pick.row, targets)
        # The preferences are set to the row the user picks, never one guessed from the physical material. Bodies a rule
        # already blocks are left to that rule's own message.
        if pick.row is None and any(
            r.body.kind is BodyKind.SHEET_METAL and r.status is not PendingBodyStatus.BLOCKED for r in entry.rows
        ):
            self._dialogs.show_error(self.text.sheet_metal_needs_row(pick.material.name))
            return None
        conflict = self._find_conflict(pick.material, pick.row, [r.body for r in entry.rows])
        if conflict is not None:
            self._dialogs.show_error(conflict)
            return None
        return entry

    def _ask_confirmations(self, entry: PendingAssignment) -> set[BodyId]:
        """One question for the entry's bodies whose rules want confirmation (a reassignment, a coating mismatch, a row
        at another thickness than the body); all or nothing. Declined bodies are reported and not staged."""
        needing = [r for r in entry.rows if r.status is PendingBodyStatus.NEEDS_CONFIRMATION]
        if not needing:
            return set()
        text = self._materials_text
        question = text.confirm_bodies(
            len(needing), entry.material.name, (text.body_line(r.body.name, r.message or "") for r in needing)
        )
        return {r.body.id for r in needing} if self._dialogs.ask(question) else set()

    def _report_staging(
        self,
        display_name: str,
        staged: PendingAssignment | None,
        not_staged: Sequence[str],
        replaced: Sequence[str],
        warnings: Sequence[str],
        *,
        only_already: bool,
    ) -> None:
        """One message for what the pending tree does not show: bodies left out and why, removals replaced, warnings.
        A clean add needs none."""
        text = self.text
        sections = [
            text.section(header, lines)
            for header, lines in (
                (text.not_added_header, not_staged),
                (text.replaced_header, replaced),
                (text.warnings_header, warnings),
            )
            if lines
        ]
        if not sections:
            return
        details = text.join_sections(sections)
        if staged is not None:
            self._dialogs.show_info(text.title, text.added_to_pending(display_name, len(staged.rows), details))
        elif only_already:
            self._dialogs.show_info(text.title, text.nothing_added_to_pending(details))  # nothing went wrong
        else:
            self._dialogs.show_error(text.not_added_to_pending(display_name, details))

    # ---- Staging a removal ----

    def stage_removal(self, body_ids: Sequence[BodyId]) -> None:
        """Adds the bodies to the pending removal. A body with no material is skipped; a body pending an assignment has
        it replaced by the removal, and the user is told."""
        if not body_ids:
            self._dialogs.show_error(self.text.select_bodies_to_remove)
            return
        requested = set(body_ids)
        bodies = [b for b in self.bodies if b.id in requested]
        claims = claims_by_body(self.pending)
        no_material = [b for b in bodies if self._material_of(b.id) is None]
        to_remove = [b for b in bodies if b not in no_material]
        text = self._materials_text

        not_staged = [text.body_line(b.name, text.has_no_material) for b in no_material]
        replaced: list[str] = []
        for b in to_remove:
            claim = claims.get(b.id)
            if isinstance(claim, PendingAssignment):
                name = self._support.label(claim.material.name, claim.row)
                replaced.append(text.body_line(b.name, self.text.pending_assignment_replaced(name)))

        if to_remove:
            ids = {b.id for b in to_remove}
            existing = removal_of(self.pending)
            kept = [r for r in existing.rows if r.body.id not in ids] if existing is not None else []
            removal = PendingRemoval((*kept, *(PendingBodyRow(b, PendingBodyStatus.OK) for b in to_remove)))
            others = [e for e in self.pending if not isinstance(e, PendingRemoval)]
            self.pending = [removal, *without_bodies(others, ids)]

        sections = [
            self.text.section(header, lines)
            for header, lines in ((self.text.not_added_header, not_staged), (self.text.replaced_header, replaced))
            if lines
        ]
        if sections:
            details = self.text.join_sections(sections)
            self._dialogs.show_info(
                self.text.title,
                self.text.removal_added_to_pending(len(to_remove), details)
                if to_remove
                else self.text.nothing_to_remove(details),
            )
        self._changed(Section.PENDING, Section.ASSIGNMENTS)

    # ---- Removing from pending (the part is not touched) ----

    def remove_from_pending(self, entries: Collection[PendingEntry], body_ids: Collection[BodyId]) -> None:
        """A whole entry for each of `entries`; just the body for each of `body_ids`."""
        kept = [e for e in self.pending if not any(e is x for x in entries)]
        self.pending = without_bodies(kept, set(body_ids))
        self._changed(Section.PENDING, Section.ASSIGNMENTS)

    def clear_pending(self) -> None:
        self.pending = []
        self._changed(Section.PENDING, Section.ASSIGNMENTS)

    # ---- Sheet Metal Preferences without bodies ----

    def apply_preference_only(self, row: SheetMetalMaterialRow) -> bool:
        """Sets the part's Sheet Metal Preferences to `row` and nothing else. Final, like Apply."""
        result = self._sheet_metal.set_preferences(row)
        self._dialogs.show_result(result, result.value)
        self.refresh()
        return result.ok

    def _apply_picked(self, pick: MaterialPick, selected_ids: Sequence[BodyId]) -> bool:
        """With bodies selected, assigns the picked sheet metal material as "Add to pending" then Apply would. With none
        it sets only the preferences, after a warning, but only on a part with no solid body: once there are bodies,
        the preferences go with their material, so they are never set on their own."""
        if selected_ids:
            return self.stage(pick, selected_ids) and self._commit()
        row = pick.row
        assert row is not None, "a picked sheet metal material always has its row"
        if self.part_has_solid:
            self._dialogs.show_error(self.text.no_solid_selected_for_row(row.name))
            return False
        question = self._sheet_metal_text.set_preferences_only(row.name, row.describe())
        return self._dialogs.ask(question) and self.apply_preference_only(row)

    # ---- Committing ----

    def _commit(self) -> bool:
        """Applies every pending change: the removal first, then each assignment in order, each re-planned against the
        part as it now stands. The confirmations each entry was given are reused; a body that newly needs one is asked.
        A body that is not changed stays pending with the reason. True when nothing is left pending."""
        self._refresh_body_state()
        left: list[PendingEntry] = []
        report: list[str] = []
        removal = removal_of(self.pending)
        if removal is not None:
            self._commit_removal(removal, left, report)
        for entry in [e for e in self.pending if isinstance(e, PendingAssignment)]:
            self._commit_assignment(entry, left, report)
        self.pending = left

        if report:
            details = self.text.join_sections(report)
            if left:
                self._dialogs.show_error(self.text.still_pending(details))
            else:
                self._dialogs.show_info(self.text.title, self.text.applied_with_notes(details))
        self.refresh()
        return not left

    def _commit_removal(self, removal: PendingRemoval, left: list[PendingEntry], report: list[str]) -> None:
        present, lines = self._still_present(removal)
        failed: list[PendingBodyRow] = []
        if present:
            result = self._materials.clear([b.id for b in present])
            self._refresh_body_state()
            failed = self._not_applied(removal, result.value, lines)
        if failed:
            left.append(dataclasses.replace(removal, rows=tuple(failed)))
        if lines:
            report.append(self.text.entry_report(self.text.remove_material_entry, lines))

    def _commit_assignment(self, old: PendingAssignment, left: list[PendingEntry], report: list[str]) -> None:
        present, lines = self._still_present(old)
        if present:
            entry = self._plan(old.material, old.row, present)
            confirmed = set(old.confirmed)
            failed: list[PendingBodyRow] = []
            conflict = self._find_conflict(old.material, old.row, present)
            if conflict is not None:
                failed = [r.not_applied(self.text.conflicts_with_sheet_metal) for r in entry.rows]
                lines.append(conflict)
            else:
                result = self._apply(entry, confirmed)
                self._refresh_body_state()  # the next entry is planned against what this one did
                failed = self._not_applied(entry, result.value, lines)
            if failed:
                left.append(dataclasses.replace(entry, rows=tuple(failed), confirmed=frozenset(confirmed)))
        if lines:
            report.append(self.text.entry_report(self._support.label(old.material.name, old.row), lines))

    def _apply(self, entry: PendingAssignment, confirmed: set[BodyId]) -> OperationResult[AssignmentReport]:
        """Applies the entry; a body that newly needs confirmation is asked once, and a yes is added to `confirmed`."""
        variant = entry.row.name if entry.row is not None else None
        ids = list(entry.body_ids)
        result = self._materials.apply(entry.material, ids, variant=variant, confirmed=frozenset(confirmed))
        if result.needs_confirmation:
            answer = self._dialogs.ask(result.question or "")
            if answer:
                planned = self._materials.plan(entry.material, ids, variant=variant)
                confirmed.update(v.body.id for v in planned.needing_confirmation)
            result = self._materials.apply(
                entry.material, ids, variant=variant, confirmed=frozenset(confirmed), confirm_remaining=answer
            )
        return result

    def _not_applied(
        self, entry: PendingEntry, report: AssignmentReport | None, lines: list[str]
    ) -> list[PendingBodyRow]:
        """The entry's rows the apply or clear left behind, each with its reason, and a report line per body that has
        something to say (the reason, or a warning on one that took)."""
        text = self._materials_text
        outcomes = {o.body_id: o for o in report.outcomes} if report is not None else {}
        failed: list[PendingBodyRow] = []
        for row in entry.rows:
            outcome = outcomes.get(row.body.id)
            if outcome is None:
                continue
            if outcome.status in (OutcomeStatus.APPLIED, OutcomeStatus.NO_MATERIAL):
                if outcome.status is OutcomeStatus.APPLIED and outcome.message:
                    lines.append(text.body_line(row.body.name, outcome.message))
                continue
            lines.append(text.body_line(row.body.name, outcome.message or ""))
            if outcome.status is not OutcomeStatus.NOT_IN_PART:
                failed.append(row.not_applied(outcome.message))
        return failed

    def _still_present(self, entry: PendingEntry) -> tuple[list[BodyInfo], list[str]]:
        """The entry's bodies still in the part, and a report line for each one gone."""
        by_id = {b.id: b for b in self.bodies}
        present = [by_id[r.body.id] for r in entry.rows if r.body.id in by_id]
        text = self._materials_text
        gone = [text.body_line(r.body.name, text.no_longer_in_part) for r in entry.rows if r.body.id not in by_id]
        return present, gone

    # ---- Planning ----

    def _selected_targets(self, selected_ids: Sequence[BodyId]) -> list[BodyInfo] | None:
        """The selected bodies, or None after saying why there are none."""
        if not selected_ids:
            self._dialogs.show_error(self.text.select_bodies_first)
            return None
        selected = set(selected_ids)
        targets = [b for b in self.bodies if b.id in selected]
        if not targets:
            # The selection resolved to nothing this scan knows about: the part changed under the dialog.
            self._dialogs.show_error(self.text.selection_not_in_part)
            return None
        return targets

    def _plan(
        self, material: Material, row: SheetMetalMaterialRow | None, targets: Sequence[BodyInfo]
    ) -> PendingAssignment:
        planned = self._materials.plan(material, [b.id for b in targets], variant=row.name if row is not None else None)
        return PendingAssignment(material, row, tuple(PendingBodyRow.of(v) for v in planned.verdicts))

    def _find_conflict(
        self, material: Material, row: SheetMetalMaterialRow | None, targets: Sequence[BodyInfo]
    ) -> str | None:
        """A body pending an assignment counts as that entry's material and row, and the pending removal as having
        none, since that is what each will have."""

        def part_row() -> SheetMetalMaterialRow | None:
            return self.part_preference.row if self.part_preference is not None else None

        return self._support.find_conflict(
            material.name, row, targets, self.bodies, self.assignments, for_sheet_metal(self.pending), part_row
        )

    def _material_of(self, body_id: BodyId) -> str | None:
        assignment = self.assignments.get(body_id)
        return assignment.material_name if assignment is not None else None

    # ---- The part ----

    def _refresh_body_state(self) -> None:
        self.bodies = tuple(self._materials.bodies())
        self.assignments = self._materials.current_assignments()
        # Only sheet metal parts have preferences worth reading; asking any other part only logs a read failure.
        has_sheet_metal = any(b.kind is BodyKind.SHEET_METAL for b in self.bodies)
        self.part_preference = (
            self._sheet_metal.read_part_preference() if self._is_sheet_metal_application or has_sheet_metal else None
        )
        preference = self.part_preference
        self.preference_checks = (
            {
                b.id: self._support.check_body(
                    self._material_of(b.id), self._sheet_metal.body_thickness_of(b.id), preference
                )
                for b in self.bodies
                if b.kind is BodyKind.SHEET_METAL
            }
            if preference is not None
            else {}
        )
        self._changed(Section.ASSIGNMENTS)

    # ---- On open ----

    def check_on_open(self) -> tuple[BodyId, ...] | None:
        """Call after `show`. On the first show only, when the part's Sheet Metal Preferences name a material: says
        which sheet metal bodies are not in sync with them. With a single sheet metal body whose material is what
        disagrees, the preferences row is staged for it, so Apply syncs them; when it cannot be staged, the body is
        returned to be put in the selection instead. Several sheet metal bodies are left to the multi-body check."""
        if self._initial_sync_checked:
            return None
        self._initial_sync_checked = True
        preference = self.part_preference
        if (
            not self.is_sheet_metal_library
            or preference is None
            or not preference.is_material_table_entry
            or not (preference.material_name or "").strip()
        ):
            return None
        sheet_metal = [b for b in self.bodies if b.kind is BodyKind.SHEET_METAL]
        not_in_sync = [
            BodyCheck(b, self.preference_checks[b.id])
            for b in sheet_metal
            if b.id in self.preference_checks
            and self.preference_checks[b.id].status is not SheetMetalPreferenceStatus.IN_SYNC
        ]
        if not not_in_sync:
            return None

        action = SyncAction.NONE
        select: tuple[BodyId, ...] | None = None
        suggestion = self._support.suggested_sync(sheet_metal, not_in_sync, preference)
        if suggestion is not None:
            body, row = suggestion
            if self._stage_preference_sync(body, row):
                action = SyncAction.STAGED
            else:
                select, action = (body.id,), SyncAction.SELECTED
        self._dialogs.show_info(
            self.text.sheet_metal_preferences_title, self._support.open_message(preference, not_in_sync, action)
        )
        return select

    def _stage_preference_sync(self, body: BodyInfo, row: SheetMetalMaterialRow) -> bool:
        """Stages `row`, and the material it is made of, for `body` without asking anything. Replacing the body's
        material is what syncing means, so a reassignment confirmation counts as given; any other confirmation is left
        for Apply to ask. False, staging nothing, when the library does not list the material or a rule blocks it."""
        material = self.material_named(row.physical_material_name)
        if material is None:
            return False
        planned = self._materials.plan(material, [body.id], variant=row.name)
        if planned.blocked:
            return False
        # Confirmation is per body, not per rule: pre-confirmed only when reassignment is all it needs confirming.
        only_reassignment = all(
            o.reason_code == MaterialsCodes.REASSIGN
            for e in planned.plan.body_evaluations
            if e.body_id == body.id and e.requires_confirmation
            for o in e.confirmation_outcomes
        )
        confirmed = frozenset({body.id}) if only_reassignment and planned.needing_confirmation else frozenset[BodyId]()
        rows = tuple(PendingBodyRow.of(v) for v in planned.verdicts)
        self.pending.append(PendingAssignment(material, row, rows, confirmed))
        self._changed(Section.PENDING, Section.ASSIGNMENTS)
        return True


def normalized(row_filter: SheetMetalRowFilter, rows: Sequence[SheetMetalMaterialRow]) -> SheetMetalRowFilter:
    """Each value the other filters no longer offer becomes "any"; a kept value takes the option's own spelling (and,
    for thickness, the option within tolerance), as a dropdown refilled with the options would read back."""

    def keep(value: Any, options: Sequence[Any], same: Callable[[Any, Any], bool]) -> Any:
        return next((o for o in options if same(o, value)), None) if value is not None else None

    return SheetMetalRowFilter(
        keep(row_filter.standard, row_filter.standard_options(rows), same_name),
        keep(row_filter.physical_material_name, row_filter.physical_material_options(rows), same_name),
        keep(row_filter.thickness, row_filter.thickness_options(rows), thickness_matches),
        keep(row_filter.bend_radius, row_filter.bend_radius_options(rows), same_name),
    )
