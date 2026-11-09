"""Mode: interactive. Reads the view, calls one session gesture, and redraws what the gesture changed. No decisions
here: those are the session's (the pending list) and the libraries' (everything else)."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from enum import Enum
from typing import Protocol

from banxopen.foundation import BodyId, BodyInfo
from banxopen.foundation.ui import MenuItem, TreeRow
from banxopen.materials import Material
from banxopen.ui_material_assignment.pending import PendingAssignment
from banxopen.ui_material_assignment.rows import (
    AssignmentMenu,
    AssignmentRowRef,
    Column,
    FilterChoices,
    MaterialMenu,
    PendingMenu,
    PendingRowRef,
    assignment_columns,
    assignment_menu,
    assignment_rows,
    entry_name,
    filter_choices,
    image_of,
    material_columns,
    material_menu,
    material_rows,
    pending_columns,
    pending_menu,
    pending_rows,
    tooltip,
)
from banxopen.ui_material_assignment.session import AssignmentSession, Dialogs, MaterialPick, Section

_log = logging.getLogger(__name__)


class Block(Enum):
    """The blocks whose changes reach `update_cb`. Tree events come through the tree handlers instead."""

    LIBRARY = "library"
    FILTER = "filter"
    CLEAR_FILTER = "clear_filter"
    SELECT_ALL = "select_all"
    SELECT_UNASSIGNED = "select_unassigned"
    TABS = "tabs"


class View(Protocol):
    """What the presenter needs of the dialog's blocks. `MaterialAssignmentView` is the NX one."""

    def set_up_columns(
        self, material: Sequence[Column], assignment: Sequence[Column], pending: Sequence[Column]
    ) -> None: ...
    def clear_highlight(self) -> None: ...
    def show_libraries(self, names: Sequence[str], selected: int | None) -> None: ...
    def selected_library_index(self) -> int | None: ...
    def show_sheet_metal_preferences(self, visible: bool) -> None: ...
    def show_filters(self, choices: FilterChoices) -> None: ...
    def selected_filter_indices(self) -> tuple[int | None, int | None, int | None, int | None]: ...
    def show_material_tree(self, rows: Sequence[TreeRow[MaterialPick]]) -> None: ...
    def show_assignment_tree(self, rows: Sequence[TreeRow[AssignmentRowRef]]) -> None: ...
    def show_pending_tree(self, rows: Sequence[TreeRow[PendingRowRef]]) -> None: ...
    def set_material_label(self, text: str | None, image: str | None) -> None: ...
    def set_assignment_label(self, text: str | None, image: str | None) -> None: ...
    def set_pending_label(self, text: str | None, image: str | None) -> None: ...
    def selected_body_ids(self) -> list[BodyId]: ...
    def set_selected_bodies(self, body_ids: Sequence[BodyId]) -> None: ...


class PropertyWindow(Protocol):
    def show(self, material: Material) -> None: ...


class MaterialAssignmentPresenter:
    def __init__(
        self,
        session: AssignmentSession,
        view: View,
        dialogs: Dialogs,
        property_window: PropertyWindow | None = None,
    ) -> None:
        self._session = session
        self._view = view
        self._dialogs = dialogs
        self._property_window = property_window
        self._choices: FilterChoices | None = None

    # ---- Dialog callbacks ----

    def on_shown(self) -> int:
        """May fire again on a tab switch: the session keeps the library and filters in use."""
        self._set_up_columns()
        self._view.clear_highlight()
        self._session.show()
        self._render()
        # After the trees are filled, so the message that may come with it is shown over a full dialog.
        select = self._session.check_on_open()
        self._render()
        if select:
            self._view.set_selected_bodies(select)
        return 0

    def on_update(self, block: Block) -> int:
        session, view = self._session, self._view
        match block:
            case Block.LIBRARY:
                index = view.selected_library_index()
                if index is not None and 0 <= index < len(session.libraries):
                    session.select_library(session.libraries[index].id)
            case Block.FILTER:
                if self._choices is not None:
                    session.set_filter(self._choices.read(*view.selected_filter_indices()))
            case Block.CLEAR_FILTER:
                session.clear_filter()
            case Block.SELECT_ALL:
                view.set_selected_bodies(session.all_solids())
            case Block.SELECT_UNASSIGNED:
                ids = session.unassigned_solids()
                if ids is not None:
                    view.set_selected_bodies(ids)
            case Block.TABS:
                # Alongside on_shown: whether a tab switch re-fires dialogShown is unconfirmed. Column setup is
                # idempotent per page, so both firing is harmless.
                self._set_up_columns()
                view.clear_highlight()
        self._render()
        return 0

    def on_apply(self) -> int:
        """Nonzero keeps the dialog as it is."""
        done = self._session.apply(self._view.selected_body_ids())
        self._render()
        return 0 if done else 1

    def on_ok(self) -> int:
        """Nonzero keeps the dialog open."""
        done = self._session.ok(self._view.selected_body_ids())
        self._render()
        if not done:
            return 1
        self._view.clear_highlight()
        return 0

    def on_cancel(self) -> int:
        """Nonzero keeps the dialog open."""
        if not self._session.cancel():
            return 1
        self._view.clear_highlight()
        return 0

    # ---- Material tree ----

    def on_material_selected(self, pick: MaterialPick | None) -> None:
        self._session.pick(pick)
        self._set_material_label(pick)

    def on_material_hovered(self, pick: MaterialPick | None) -> None:
        """Hover only retitles the label: moving the pointer across the tree must not repoint what Assign acts on."""
        self._set_material_label(pick or self._session.selected_pick)

    def material_tooltip(self, pick: MaterialPick) -> str:
        return tooltip(pick, self._session.text)

    def on_material_default_action(self, pick: MaterialPick) -> None:
        self._show_properties(pick.material)

    def material_menu(self, clicked: MaterialPick | None) -> Sequence[MenuItem]:
        return material_menu(self._session, clicked, bool(self._view.selected_body_ids()))

    def on_material_command(self, item_id: int, targets: Sequence[MaterialPick]) -> None:
        session = self._session
        pick = targets[0] if targets else session.selected_pick
        if item_id == MaterialMenu.REFRESH:
            session.refresh()
        elif pick is None:
            return
        elif item_id == MaterialMenu.PROPERTIES:
            self._show_properties(pick.material)
        elif item_id == MaterialMenu.ASSIGN:
            session.stage(pick, self._view.selected_body_ids())
        elif item_id == MaterialMenu.APPLY_SHEET_METAL_PREFERENCE and pick.row is not None:
            session.apply_preference_only(pick.row)
        self._render()

    # ---- Current assignment tree ----

    def on_assignment_selected(self, row: AssignmentRowRef | None) -> None:
        self._view.set_assignment_label(row.material_label if row else None, image_of(self._session, row))

    def on_assignment_default_action(self, row: AssignmentRowRef) -> None:
        self._add_to_selection(row.bodies)

    def assignment_menu(self, clicked: AssignmentRowRef | None) -> Sequence[MenuItem]:
        return assignment_menu(self._session, clicked)

    def on_assignment_command(self, item_id: int, targets: Sequence[AssignmentRowRef]) -> None:
        bodies = [b for t in targets for b in t.bodies]
        if item_id == AssignmentMenu.REFRESH:
            self._session.refresh()
        elif item_id == AssignmentMenu.SELECT_BODIES:
            self._view.set_selected_bodies(tuple(dict.fromkeys(b.id for b in bodies)))
        elif item_id == AssignmentMenu.ADD_TO_BODY_SELECTION:
            self._add_to_selection(bodies)
        elif item_id == AssignmentMenu.REMOVE_MATERIAL:
            self._session.stage_removal(tuple(dict.fromkeys(b.id for b in bodies)))
        self._render()

    # ---- Pending tree ----

    def on_pending_selected(self, row: PendingRowRef | None) -> None:
        if row is None:
            self._view.set_pending_label(None, None)
            return
        entry = row.entry
        image = entry.material.image_path if isinstance(entry, PendingAssignment) else None
        self._view.set_pending_label(entry_name(self._session, row.entry), image)

    def pending_menu(self, clicked: PendingRowRef | None) -> Sequence[MenuItem]:
        return pending_menu(self._session, clicked)

    def on_pending_command(self, item_id: int, targets: Sequence[PendingRowRef]) -> None:
        if item_id == PendingMenu.CLEAR_ALL:
            self._session.clear_pending()
        elif item_id == PendingMenu.REMOVE:
            # A root row removes the whole entry; a body row just that body from it.
            entries = [t.entry for t in targets if t.row is None]
            body_ids = {t.row.body.id for t in targets if t.row is not None}
            self._session.remove_from_pending(entries, body_ids)
        self._render()

    # ---- Helpers ----

    def _set_up_columns(self) -> None:
        text = self._session.text
        self._view.set_up_columns(
            material_columns(text),
            assignment_columns(text, self._session.show_grade_column),
            pending_columns(text),
        )

    def _set_material_label(self, pick: MaterialPick | None) -> None:
        if pick is None:
            self._view.set_material_label(None, None)
        else:
            self._view.set_material_label(pick.display_name, pick.material.image_path)

    def _add_to_selection(self, bodies: Sequence[BodyInfo]) -> None:
        ids = self._session.with_solids_added(bodies, self._view.selected_body_ids())
        if ids is not None:
            self._view.set_selected_bodies(ids)

    def _show_properties(self, material: Material) -> None:
        if self._property_window is None:
            self._dialogs.show_error(self._session.text.property_window_unavailable)
            return
        _log.debug("Opening the property window for '%s'.", material.name)
        self._property_window.show(material)

    def _render(self) -> None:
        """Redraws only what changed: a rebuilt tree loses its selection."""
        session, view = self._session, self._view
        changes = session.take_changes()
        if Section.LIBRARIES in changes:
            view.show_libraries([r.display_name for r in session.libraries], session.selected_library_index)
        if Section.FILTERS in changes:
            view.show_sheet_metal_preferences(session.is_sheet_metal_library)
            if session.is_sheet_metal_library:
                self._choices = filter_choices(session)
                view.show_filters(self._choices)
        if Section.MATERIALS in changes:
            view.show_material_tree(material_rows(session))
            view.set_material_label(None, None)
        if Section.ASSIGNMENTS in changes:
            view.show_assignment_tree(assignment_rows(session))
        if Section.PENDING in changes:
            view.show_pending_tree(pending_rows(session))
