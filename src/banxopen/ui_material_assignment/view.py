"""Every block ID of BlockUI.dlx and every block read and write. When the Styler renames a block, only this file
changes. Implements the presenter's `View`, and turns tree events into presenter calls with the value each node was
rendered from: the presenter never sees a Node."""

# NX 2412's Python stubs declare instance methods without `self`, type enum members as int and give collections
# no __iter__; these rules would only report those stub defects here. Everything else is still checked.
# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportReturnType=false
# pyright: reportCallIssue=false, reportGeneralTypeIssues=false, reportOptionalMemberAccess=false

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

import NXOpen
import NXOpen.BlockStyler

from banxopen.foundation import BodyId
from banxopen.foundation.nx import BodyResolver, NxDialogText, nx_error_detail
from banxopen.foundation.ui import NxMessenger, TreeBinding, TreeRow, TreeUnavailableError, show_menu
from banxopen.ui_material_assignment.presenter import Block, MaterialAssignmentPresenter
from banxopen.ui_material_assignment.rows import AssignmentRowRef, Column, FilterChoice, FilterChoices, PendingRowRef
from banxopen.ui_material_assignment.session import MaterialPick

T = TypeVar("T")
_log = logging.getLogger(__name__)

# ---- Block IDs, verbatim from BlockUI.dlx ----
SELECTED_BODIES = "Sel_SoildBodies"
SELECT_ALL_BUTTON = "selectAllButton"
SELECT_UNASSIGNED_BUTTON = "selectUnassignedButton"
LIBRARY_ENUM = "enum_MatLibrary"
SM_PREFERENCES_GROUP = "group_SMPref"
STANDARD_ENUM = "enum_SmStandard"
SM_MATERIAL_ENUM = "enum_SmPhyMatName"
SM_THICKNESS_ENUM = "enum_smTHK"
SM_BEND_RADIUS_ENUM = "enum_SmBendRad"
SM_CLEAR_BUTTON = "btn_SmClearSelection"
TAB_CONTROL = "tabControl"
MATERIAL_TREE = "MaterialTree"
ASSIGNMENT_TREE = "CurrentAssignmentTree"
PENDING_TREE = "PendingAssignments"
MATERIAL_LABEL = "lbl_MaterialDisplay"
ASSIGNMENT_LABEL = "lbl_MaterialDisplay1"
PENDING_LABEL = "lbl_MaterialDisplay2"

_UPDATES = {
    LIBRARY_ENUM: Block.LIBRARY,
    STANDARD_ENUM: Block.FILTER,
    SM_MATERIAL_ENUM: Block.FILTER,
    SM_THICKNESS_ENUM: Block.FILTER,
    SM_BEND_RADIUS_ENUM: Block.FILTER,
    SM_CLEAR_BUTTON: Block.CLEAR_FILTER,
    SELECT_ALL_BUTTON: Block.SELECT_ALL,
    SELECT_UNASSIGNED_BUTTON: Block.SELECT_UNASSIGNED,
    TAB_CONTROL: Block.TABS,
}

# The tab pages, in BlockUI.dlx order. A page's native controls exist only while it is the current page.
_MATERIAL_PAGE, _ASSIGNMENT_PAGE, _PENDING_PAGE = 0, 1, 2


@dataclass(slots=True)
class _Page(Generic[T]):
    """One tab page's tree. Whether the tree is ready is asked of NX every time, never remembered: a tree's control
    can be gone, or rebuilt without its columns, after the page was first set up (an off-screen page, or NX
    recreating the controls after Apply). A redraw that cannot run now is kept and replayed when the page is next set
    up, and the last one is kept too, so a tree whose control was rebuilt is refilled with its latest rows."""

    label: str
    index: int
    tree: NXOpen.BlockStyler.Tree | None
    binding: TreeBinding[T] | None
    columns: Sequence[Column] = ()
    ever_set_up: bool = False
    waiting: Sequence[TreeRow[T]] | None = None
    last: Sequence[TreeRow[T]] | None = None

    def has_live_columns(self) -> bool:
        if self.tree is None:
            return False
        try:
            return self.tree.NumberOfColumns >= len(self.columns)
        except NXOpen.NXException as ex:
            _log.debug("%s tree not available (%s)", self.label, nx_error_detail(ex))
            return False


class MaterialAssignmentView:
    def __init__(self, dialog: NXOpen.BlockStyler.BlockDialog, resolver: BodyResolver, placeholder: str) -> None:
        """Construct from initialize_cb, which is where the blocks exist. `placeholder` is what a label shows with
        nothing selected; the .dlx's design-time text would otherwise look like data."""
        self._top = dialog.TopBlock
        self._resolver = resolver
        self._placeholder = placeholder
        self._highlighted: dict[BodyId, NXOpen.Body] = {}
        self._libraries_count = 0
        self._filter_counts: dict[str, int] = {}

        self._selected_bodies = self._find(SELECTED_BODIES)
        self._library_enum = self._find(LIBRARY_ENUM)
        self._sm_group = self._find(SM_PREFERENCES_GROUP)
        self._filters = {
            k: self._find(k) for k in (STANDARD_ENUM, SM_MATERIAL_ENUM, SM_THICKNESS_ENUM, SM_BEND_RADIUS_ENUM)
        }
        self._tabs = self._find(TAB_CONTROL)
        self._labels = {k: self._find(k) for k in (MATERIAL_LABEL, ASSIGNMENT_LABEL, PENDING_LABEL)}
        material_tree, assignment_tree, pending_tree = (
            self._find(MATERIAL_TREE),
            self._find(ASSIGNMENT_TREE),
            self._find(PENDING_TREE),
        )
        self._materials: _Page[MaterialPick] = _Page(
            "material", _MATERIAL_PAGE, material_tree, TreeBinding(material_tree) if material_tree else None
        )
        self._assignments: _Page[AssignmentRowRef] = _Page(
            "current assignment",
            _ASSIGNMENT_PAGE,
            assignment_tree,
            TreeBinding(assignment_tree) if assignment_tree else None,
        )
        self._pending: _Page[PendingRowRef] = _Page(
            "pending", _PENDING_PAGE, pending_tree, TreeBinding(pending_tree) if pending_tree else None
        )

    @staticmethod
    def update_of(block: NXOpen.BlockStyler.UIBlock) -> Block | None:
        return _UPDATES.get(block.Name)

    # ---- Tree handlers ----

    def connect(self, presenter: MaterialAssignmentPresenter) -> None:
        """Registers the tree handlers. Tree events do not route through update_cb."""
        p = presenter
        materials, assignments, pending = self._materials.binding, self._assignments.binding, self._pending.binding
        if materials is not None:
            tree = self._materials.tree
            tree.SetOnSelectHandler(
                _guarded(
                    "material tree select",
                    lambda _t, node, _c, selected: (
                        None
                        if materials.is_rebuilding
                        else p.on_material_selected(materials.resolve(node) if selected else None)
                    ),
                )
            )
            tree.SetOnPreSelectHandler(
                _guarded(
                    "material tree hover",
                    lambda _t, node, _c, _s: (
                        None if materials.is_rebuilding else p.on_material_hovered(materials.resolve(node))
                    ),
                )
            )
            tree.SetToolTipTextHandler(
                _guarded("material tree tooltip", lambda _t, node, _c: _tooltip(p, materials.resolve(node)), "")
            )
            tree.SetOnDefaultActionHandler(
                _guarded(
                    "material tree double-click",
                    lambda _t, node, _c: _if_value(materials.resolve(node), p.on_material_default_action),
                )
            )
            tree.SetOnMenuHandler(
                _guarded(
                    "material tree menu", lambda t, node, _c: show_menu(t, p.material_menu(materials.resolve(node)))
                )
            )
            tree.SetOnMenuSelectionHandler(
                _guarded(
                    "material tree command",
                    lambda _t, node, item: p.on_material_command(item, materials.resolve_selected_or(node)),
                )
            )
        if assignments is not None:
            tree = self._assignments.tree

            def on_assignment_select(_t: Any, node: Any, _c: int, selected: bool) -> None:
                if assignments.is_rebuilding:
                    return
                p.on_assignment_selected(assignments.resolve(node) if selected else None)
                self._highlight(b.id for r in assignments.resolve_selected() for b in r.bodies)

            tree.SetOnSelectHandler(_guarded("current assignment tree select", on_assignment_select))
            tree.SetOnDefaultActionHandler(
                _guarded(
                    "current assignment double-click",
                    lambda _t, node, _c: _if_value(assignments.resolve(node), p.on_assignment_default_action),
                )
            )
            tree.SetOnMenuHandler(
                _guarded(
                    "current assignment menu",
                    lambda t, node, _c: show_menu(t, p.assignment_menu(assignments.resolve(node))),
                )
            )
            tree.SetOnMenuSelectionHandler(
                _guarded(
                    "current assignment command",
                    lambda _t, node, item: p.on_assignment_command(item, assignments.resolve_selected_or(node)),
                )
            )
        if pending is not None:
            tree = self._pending.tree

            def on_pending_select(_t: Any, node: Any, _c: int, selected: bool) -> None:
                if pending.is_rebuilding:
                    return
                p.on_pending_selected(pending.resolve(node) if selected else None)
                self._highlight(b.id for r in pending.resolve_selected() for b in r.bodies)

            tree.SetOnSelectHandler(_guarded("pending tree select", on_pending_select))
            tree.SetOnMenuHandler(
                _guarded("pending tree menu", lambda t, node, _c: show_menu(t, p.pending_menu(pending.resolve(node))))
            )
            tree.SetOnMenuSelectionHandler(
                _guarded(
                    "pending tree command",
                    lambda _t, node, item: p.on_pending_command(item, pending.resolve_selected_or(node)),
                )
            )

    # ---- Columns and deferred redraws ----

    def set_up_columns(
        self, material: Sequence[Column], assignment: Sequence[Column], pending: Sequence[Column]
    ) -> None:
        self._materials.columns, self._assignments.columns, self._pending.columns = material, assignment, pending
        page = self._active_page()
        for state in (self._materials, self._assignments, self._pending):
            if state.index == page:
                self._ensure_columns(state)

    def _ensure_columns(self, state: _Page[Any]) -> None:
        if not state.has_live_columns():
            if state.ever_set_up:
                _log.debug("%s tree lost its columns (control recreated); rebuilding", state.label)
                state.waiting = state.waiting if state.waiting is not None else state.last
            if state.tree is not None and state is self._materials:
                state.tree.SetPreSelectionTimeOut(250.0)
            self._insert_columns(state)
            state.ever_set_up = True
        # The page is current (only the active page gets here): flush what was kept while it was off-screen.
        if state.waiting is not None:
            rows, state.waiting = state.waiting, None
            self._try_show(state, rows)

    @staticmethod
    def _insert_columns(state: _Page[Any]) -> None:
        tree = state.tree
        if tree is None:
            return
        for column_id, title, width in state.columns:
            # Per column, so a control that kept some of its columns still gets the rest.
            try:
                tree.InsertColumn(column_id, title, width)
                tree.SetColumnResizePolicy(column_id, NXOpen.BlockStyler.Tree.ColumnResizePolicy.ConstantWidth)
            except NXOpen.NXException as ex:
                _log.debug("Column %d ('%s') of the %s tree: %s", column_id, title, state.label, nx_error_detail(ex))

    def _show_or_defer(self, state: _Page[T], rows: Sequence[TreeRow[T]]) -> None:
        """A tree's control exists only while its tab page is current, and redrawing one that is not there throws."""
        state.last = rows
        if state.binding is None:
            return
        if self._active_page() == state.index and state.has_live_columns():
            self._try_show(state, rows)
        else:
            state.waiting = rows

    @staticmethod
    def _try_show(state: _Page[T], rows: Sequence[TreeRow[T]]) -> None:
        if state.binding is None:
            return
        try:
            state.binding.show(rows)
        except TreeUnavailableError as ex:
            _log.debug("%s tree refused the rebuild, deferred: %s", state.label, ex)
            state.waiting = rows

    def _active_page(self) -> int | None:
        return self._tabs.ActivePage if self._tabs is not None else None

    # ---- Trees ----

    def show_material_tree(self, rows: Sequence[TreeRow[MaterialPick]]) -> None:
        self._show_or_defer(self._materials, rows)

    def show_assignment_tree(self, rows: Sequence[TreeRow[AssignmentRowRef]]) -> None:
        self._show_or_defer(self._assignments, rows)

    def show_pending_tree(self, rows: Sequence[TreeRow[PendingRowRef]]) -> None:
        self._show_or_defer(self._pending, rows)

    # ---- Library and filter dropdowns ----

    def show_libraries(self, names: Sequence[str], selected: int | None) -> None:
        self._libraries_count = len(names)
        if self._library_enum is not None:
            _set_enum(self._library_enum, names, max(selected or 0, 0) if names else None)

    def selected_library_index(self) -> int | None:
        return _selected_index(self._library_enum, self._libraries_count)

    def show_sheet_metal_preferences(self, visible: bool) -> None:
        if self._sm_group is not None:
            self._sm_group.Show = visible

    def show_filters(self, choices: FilterChoices) -> None:
        for block_id, choice in self._choices(choices):
            self._filter_counts[block_id] = len(choice.labels)
            block = self._filters[block_id]
            if block is not None:
                _set_enum(block, choice.labels, choice.selected)

    def selected_filter_indices(self) -> tuple[int | None, int | None, int | None, int | None]:
        def index(block_id: str) -> int | None:
            return _selected_index(self._filters[block_id], self._filter_counts.get(block_id, 0))

        return index(STANDARD_ENUM), index(SM_MATERIAL_ENUM), index(SM_THICKNESS_ENUM), index(SM_BEND_RADIUS_ENUM)

    @staticmethod
    def _choices(choices: FilterChoices) -> tuple[tuple[str, FilterChoice[Any]], ...]:
        return (
            (STANDARD_ENUM, choices.standard),
            (SM_MATERIAL_ENUM, choices.physical_material),
            (SM_THICKNESS_ENUM, choices.thickness),
            (SM_BEND_RADIUS_ENUM, choices.bend_radius),
        )

    # ---- Labels, one per tab page ----

    def set_material_label(self, text: str | None, image: str | None) -> None:
        self._set_label(MATERIAL_LABEL, text, image)

    def set_assignment_label(self, text: str | None, image: str | None) -> None:
        self._set_label(ASSIGNMENT_LABEL, text, image)

    def set_pending_label(self, text: str | None, image: str | None) -> None:
        self._set_label(PENDING_LABEL, text, image)

    def _set_label(self, block_id: str, text: str | None, image: str | None) -> None:
        label = self._labels[block_id]
        if label is None:
            return
        properties = label.GetProperties()
        try:
            properties.SetString("Label", text if text and text.strip() else self._placeholder)
        finally:
            properties.Dispose()
        # A full path to the BMP. A thumbnail NX refuses must not cost the user the label text.
        try:
            label.Bitmap = image if image and image.strip() else ""
        except NXOpen.NXException as ex:
            _log.warning("Label '%s' bitmap '%s' could not be set: %s", block_id, image, nx_error_detail(ex))

    # ---- Body selection and highlight ----

    def selected_body_ids(self) -> list[BodyId]:
        if self._selected_bodies is None:
            return []
        # Scoped to bodies in the .dlx, but filtered rather than trusted: a non-body must drop out, not throw.
        return [
            BodyResolver.body_id(o) for o in self._selected_bodies.GetSelectedObjects() if isinstance(o, NXOpen.Body)
        ]

    def set_selected_bodies(self, body_ids: Sequence[BodyId]) -> None:
        if self._selected_bodies is None:
            return
        # The resolver is only valid for the scan that filled it, and this can run at any point of the dialog's life.
        self._resolver.refresh()
        bodies = [b for b in (self._resolver.resolve(i) for i in body_ids) if b is not None]
        self._selected_bodies.SetSelectedObjects(bodies)

    def clear_highlight(self) -> None:
        """On a tab switch and on close, so a highlight never outlives the tree selection it was shown for."""
        self._highlight(())

    def _highlight(self, body_ids: Any) -> None:
        """Highlights exactly `body_ids`: transient feedback for browsing a tree, not the assignment target."""
        ids = set(body_ids)
        for stale in [i for i in self._highlighted if i not in ids]:
            self._highlighted.pop(stale).Unhighlight()
        for body_id in ids - self._highlighted.keys():
            body = self._resolver.resolve(body_id)
            if body is not None:
                body.Highlight()
                self._highlighted[body_id] = body

    # ---- Lookup ----

    def _find(self, block_id: str) -> Any:
        """None, with a warning, when a block is missing: that disables the feature that needs it rather than stopping
        a dialog that otherwise works."""
        try:
            block = self._top.FindBlock(block_id)
        except Exception as ex:  # noqa: BLE001  (any failure means the block is unavailable)
            _log.warning(
                "Dialog block '%s' could not be resolved (%s); the features that use it are disabled.", block_id, ex
            )
            return None
        if block is None:
            _log.warning("Dialog block '%s' is missing; the features that use it are disabled.", block_id)
        return block


def _set_enum(block: Any, members: Sequence[str], selected: int | None) -> None:
    properties = block.GetProperties()
    try:
        properties.SetEnumMembers("Value", list(members))
        if members and selected is not None:
            properties.SetEnum("Value", selected)
    finally:
        properties.Dispose()


def _selected_index(block: Any, count: int) -> int | None:
    if block is None or count == 0:
        return None
    properties = block.GetProperties()
    try:
        index = properties.GetEnum("Value")
    finally:
        properties.Dispose()
    return index if 0 <= index < count else None


def _tooltip(presenter: MaterialAssignmentPresenter, pick: MaterialPick | None) -> str:
    return presenter.material_tooltip(pick) if pick is not None else ""


def _if_value(value: T | None, action: Callable[[T], None]) -> None:
    if value is not None:
        action(value)


def _guarded(what: str, handler: Callable[..., Any], fallback: Any = None) -> Callable[..., Any]:
    """A tree handler whose errors are logged and shown rather than thrown: an exception escaping an NX callback leaves
    a dialog that quietly stopped responding."""

    def run(*args: Any) -> Any:
        try:
            return handler(*args)
        except Exception as ex:  # noqa: BLE001  (boundary: the last line of defence for an NX callback)
            _log.exception("An error occurred handling '%s'", what)
            NxMessenger().show_error(NxDialogText.DEFAULT.handler_failed(what, str(ex)))
            return fallback

    return run
