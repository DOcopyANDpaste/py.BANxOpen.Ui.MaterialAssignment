"""What the dialog's trees, filter dropdowns and context menus show, built from the session as plain values. The view
writes these to the blocks as they are."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Generic, TypeVar

from banxopen.foundation import BodyId, BodyInfo
from banxopen.foundation.ui import SEPARATOR, MenuItem, TreeRow
from banxopen.materials import Material, MaterialCategoryNode, MaterialId, MaterialPropertyValue
from banxopen.sheetmetal import SheetMetalMaterialRow, SheetMetalRowFilter, format_thickness
from banxopen.ui_material_assignment.pending import (
    PendingAssignment,
    PendingBodyRow,
    PendingBodyStatus,
    PendingEntry,
    PendingRemoval,
)
from banxopen.ui_material_assignment.session import AssignmentSession, MaterialPick, same_name
from banxopen.ui_material_assignment.text import UiText

T = TypeVar("T")
Column = tuple[int, str, int]
"""(id, title, width)."""


# ---- Columns ----


class MaterialColumn:
    NAME: Final = 0
    DETAIL: Final = 1
    DENSITY: Final = 2


class AssignmentColumn:
    NAME: Final = 0
    COUNT: Final = 1
    DISPLAY_MATERIAL: Final = 2
    PENDING: Final = 3
    """What a body is about to be changed to."""
    GRADE: Final = 4
    """In the NX Sheet Metal application only."""


class PendingColumn:
    NAME: Final = 0
    KIND: Final = 1
    STATUS: Final = 2


def material_columns(text: UiText) -> tuple[Column, ...]:
    return (
        (MaterialColumn.NAME, text.column_material, 220),
        (MaterialColumn.DETAIL, text.column_description, 160),
        (MaterialColumn.DENSITY, text.column_density, 90),
    )


def assignment_columns(text: UiText, show_grade: bool) -> tuple[Column, ...]:
    columns: tuple[Column, ...] = (
        (AssignmentColumn.NAME, text.column_material_or_body, 220),
        (AssignmentColumn.COUNT, text.column_bodies_or_kind, 110),
        (AssignmentColumn.DISPLAY_MATERIAL, text.column_display_material, 140),
        (AssignmentColumn.PENDING, text.column_pending, 200),
    )
    return (*columns, (AssignmentColumn.GRADE, text.column_sheet_metal_grade, 150)) if show_grade else columns


def pending_columns(text: UiText) -> tuple[Column, ...]:
    return (
        (PendingColumn.NAME, text.column_material_or_body, 220),
        (PendingColumn.KIND, text.column_kind, 90),
        (PendingColumn.STATUS, text.column_status, 260),
    )


# ---- What a row stands for ----


@dataclass(frozen=True, slots=True)
class AssignmentRowRef:
    """A current-assignment row: a material in use (`body` None, `bodies` all of its bodies) or one body under it, so a
    command can act on either alike."""

    material_label: str
    resolved_material_id: MaterialId | None
    bodies: tuple[BodyInfo, ...]
    body: BodyInfo | None
    is_unassigned: bool
    assignment_count: int = 1
    """How many bodies the part says carry the material (bodies only seen by one of the two reads included)."""


@dataclass(frozen=True, slots=True)
class PendingRowRef:
    """A pending row: a whole entry (`row` None), or one body in it."""

    entry: PendingEntry
    row: PendingBodyRow | None

    @property
    def bodies(self) -> tuple[BodyInfo, ...]:
        return tuple(r.body for r in self.entry.rows) if self.row is None else (self.row.body,)


def entry_name(session: AssignmentSession, entry: PendingEntry) -> str:
    if isinstance(entry, PendingRemoval):
        return session.text.remove_material_entry
    return session.support.label(entry.material.name, entry.row)


# ---- Material tree ----


def material_rows(session: AssignmentSession) -> tuple[TreeRow[MaterialPick], ...]:
    """Categories (not pickable), their materials, and under each material of a sheet metal library the standards file
    rows the filters leave: the Sheet Metal Preferences materials the user actually picks."""
    categories, rows_by_material = session.material_tree()
    return tuple(_category(c, rows_by_material) for c in categories)


def _category(
    node: MaterialCategoryNode, by_material: Mapping[str, tuple[SheetMetalMaterialRow, ...]]
) -> TreeRow[MaterialPick]:
    children = [_category(c, by_material) for c in node.children]
    for material in node.materials:
        density = density_text(material)
        rows = by_material.get(material.name.casefold(), ())
        children.append(
            TreeRow(
                material.name,
                MaterialPick(material),
                {MaterialColumn.DETAIL: material.description or "", MaterialColumn.DENSITY: density},
                tuple(
                    TreeRow(
                        row.name,
                        MaterialPick(material, row),
                        {MaterialColumn.DETAIL: row.describe(), MaterialColumn.DENSITY: density},
                    )
                    for row in rows
                ),
            )
        )
    return TreeRow(node.display_name, None, children=tuple(children))


def density_text(material: Material) -> str:
    density = next((p for p in material.properties if "density" in (p.name or "").casefold()), None)
    if density is None:
        return ""
    unit = density.unit or ""
    return density.as_string() if not unit.strip() else f"{density.as_string()} {unit}"


def tooltip(pick: MaterialPick, text: UiText) -> str:
    material = pick.material
    lines = [pick.display_name]
    if pick.row is not None:
        lines += [text.sheet_metal_material_made_of(material.name), pick.row.describe()]
    category = material.category
    lines.append(
        text.category_separator.join(category.path_segments) if category.path_segments else category.display_name
    )
    if material.description and material.description.strip():
        lines.append(material.description)
    return "\n".join(lines)


# ---- Material property window ----


class PropertyColumn:
    NAME: Final = 0
    VALUE: Final = 1
    UNIT: Final = 2


def property_columns(text: UiText) -> tuple[Column, ...]:
    return (
        (PropertyColumn.NAME, text.column_property, 220),
        (PropertyColumn.VALUE, text.column_value, 200),
        (PropertyColumn.UNIT, text.column_unit, 90),
    )


def property_rows(material: Material, text: UiText) -> tuple[TreeRow[MaterialPropertyValue], ...]:
    """The material's class, and its properties under it. MatML properties come in three practical shapes and nothing
    declares which: a single value is one row; a comma-separated list (typically a temperature-dependent table) is a
    row with one child per entry, which is why this is a tree and not a table."""
    rows: list[TreeRow[MaterialPropertyValue]] = []
    for prop in material.properties:
        values = prop.as_array()
        unit = prop.unit or ""
        name = prop.name if not (prop.symbol or "").strip() else f"{prop.name} ({prop.symbol})"
        is_table = len(values) > 1
        rows.append(
            TreeRow(
                name,
                prop,
                {
                    PropertyColumn.VALUE: text.property_values(len(values)) if is_table else prop.as_string(),
                    PropertyColumn.UNIT: unit,
                },
                tuple(TreeRow("", prop, {PropertyColumn.VALUE: v, PropertyColumn.UNIT: unit}) for v in values)
                if is_table
                else (),
            )
        )
    return (TreeRow(material.category.display_name, None, children=tuple(rows)),)


# ---- Current assignment tree ----


def assignment_groups(session: AssignmentSession) -> tuple[AssignmentRowRef, ...]:
    """One group per material name in use (case-insensitive, first spelling met), bodies by name; the unassigned
    group last, the rest by name."""
    text = session.text
    by_id = {b.id: b for b in session.bodies}
    groups: dict[str, tuple[str, list[MaterialId | None], list[BodyId]]] = {}
    for assignment in session.assignments.values():
        label = assignment.material_name if assignment.material_name is not None else text.unassigned
        _, resolved, ids = groups.setdefault(label.casefold(), (label, [], []))
        resolved.append(assignment.resolved_material_id)
        ids.append(assignment.body_id)
    result: list[AssignmentRowRef] = []
    for label, resolved, ids in groups.values():
        resolved_id = next((r for r in resolved if r is not None), None)
        bodies = sorted((by_id[i] for i in ids if i in by_id), key=lambda b: b.name.casefold())
        unassigned = resolved_id is None and label == text.unassigned
        result.append(AssignmentRowRef(label, resolved_id, tuple(bodies), None, unassigned, len(ids)))
    return tuple(sorted(result, key=lambda r: (r.is_unassigned, r.material_label.casefold())))


def assignment_rows(session: AssignmentSession) -> tuple[TreeRow[AssignmentRowRef], ...]:
    """The part's real materials, with what the pending list is about to change beside each body."""
    text = session.text
    support = session.support
    preference = session.part_preference
    pending = _pending_by_body(session.pending)
    rows: list[TreeRow[AssignmentRowRef]] = []
    for group in assignment_groups(session):
        count = sum(1 for b in group.bodies if b.id in pending)
        columns = {AssignmentColumn.COUNT: str(group.assignment_count)}
        if count:
            columns[AssignmentColumn.PENDING] = text.group_pending_count(count)
        if session.show_grade_column:
            columns[AssignmentColumn.GRADE] = support.grade_for_material(group.material_label, preference)
        children: list[TreeRow[AssignmentRowRef]] = []
        for body in group.bodies:
            body_columns = {
                AssignmentColumn.COUNT: body.kind.value,
                AssignmentColumn.DISPLAY_MATERIAL: _display_material(session, body.id),
            }
            claim = pending.get(body.id)
            if claim is not None:
                body_columns[AssignmentColumn.PENDING] = pending_flag(session, *claim)
            if session.show_grade_column:
                body_columns[AssignmentColumn.GRADE] = support.grade_for_body(
                    session.preference_checks.get(body.id), preference
                )
            ref = AssignmentRowRef(group.material_label, group.resolved_material_id, (body,), body, group.is_unassigned)
            children.append(TreeRow(body.name, ref, body_columns))
        rows.append(TreeRow(group.material_label, group, columns, tuple(children)))
    return tuple(rows)


def _display_material(session: AssignmentSession, body_id: BodyId) -> str:
    assignment = session.assignments.get(body_id)
    display = assignment.current_display_material if assignment is not None else None
    return display.name if display is not None else ""


def _pending_by_body(entries: Sequence[PendingEntry]) -> dict[BodyId, tuple[PendingEntry, PendingBodyRow]]:
    return {row.body.id: (entry, row) for entry in entries for row in entry.rows}


def pending_flag(session: AssignmentSession, entry: PendingEntry, row: PendingBodyRow) -> str:
    text = session.text
    flag = text.flag_remove if isinstance(entry, PendingRemoval) else text.flag_assign(entry_name(session, entry))
    if row.status is PendingBodyStatus.NOT_APPLIED:
        return flag + text.flag_not_applied_suffix
    if isinstance(entry, PendingAssignment) and entry.is_confirmed(row):
        return flag + text.flag_confirmed_suffix
    return flag


def image_of(session: AssignmentSession, row: AssignmentRowRef | None) -> str | None:
    """The thumbnail of the material a current-assignment row names, from the loaded library."""
    if row is None or row.is_unassigned:
        return None
    material = session.material_named(row.material_label)
    return material.image_path if material is not None else None


# ---- Pending tree ----


def pending_rows(session: AssignmentSession) -> tuple[TreeRow[PendingRowRef], ...]:
    return tuple(
        TreeRow(
            entry_name(session, entry),
            PendingRowRef(entry, None),
            {PendingColumn.KIND: str(len(entry.rows))},
            tuple(
                TreeRow(
                    row.body.name,
                    PendingRowRef(entry, row),
                    {
                        PendingColumn.KIND: row.body.kind.value,
                        PendingColumn.STATUS: pending_status(session, entry, row),
                    },
                )
                for row in entry.rows
            ),
        )
        for entry in session.pending
    )


def pending_status(session: AssignmentSession, entry: PendingEntry, row: PendingBodyRow) -> str:
    """Blocked and declined bodies are reported when staged and never listed, so a body is either waiting (with a
    rule's warning, or the reassignment the user confirmed) or was left behind by Apply, with why. A pending removal
    names the material it will take off."""
    text = session.text
    if row.status is PendingBodyStatus.NOT_APPLIED:
        return text.status_not_applied(row.message)
    if isinstance(entry, PendingRemoval):
        assignment = session.assignments.get(row.body.id)
        return text.status_pending_removal(assignment.material_name if assignment is not None else None)
    status = text.status_pending_confirmed if entry.is_confirmed(row) else text.status_pending
    return text.status_with_note(status, row.message) if row.message and row.message.strip() else status


# ---- Sheet Metal Preferences filter dropdowns ----


@dataclass(frozen=True, slots=True)
class FilterChoice(Generic[T]):
    """One dropdown: "(Any)" then the options. A pick is mapped back through `values`, never parsed from the label,
    which is what lets a thickness be shown rounded and still compare exactly."""

    labels: tuple[str, ...]
    values: tuple[T, ...]
    selected: int
    """0 is "(Any)"."""

    def value_at(self, index: int | None) -> T | None:
        return self.values[index - 1] if index is not None and 0 < index <= len(self.values) else None


@dataclass(frozen=True, slots=True)
class FilterChoices:
    standard: FilterChoice[str]
    physical_material: FilterChoice[str]
    thickness: FilterChoice[float]
    bend_radius: FilterChoice[str]

    def read(
        self, standard: int | None, physical_material: int | None, thickness: int | None, bend_radius: int | None
    ) -> SheetMetalRowFilter:
        """The filter the dropdowns' selected indices stand for."""
        return SheetMetalRowFilter(
            self.standard.value_at(standard),
            self.physical_material.value_at(physical_material),
            self.thickness.value_at(thickness),
            self.bend_radius.value_at(bend_radius),
        )


def filter_choices(session: AssignmentSession) -> FilterChoices:
    """Each dropdown with the options the other filters leave, and the current value selected."""
    f, rows, any_label = session.filter, session.library_rows, session.text.any_filter

    def text_choice(options: tuple[str, ...], current: str | None) -> FilterChoice[str]:
        selected = next((i + 1 for i, o in enumerate(options) if same_name(o, current)), 0)
        return FilterChoice((any_label, *options), options, selected)

    thicknesses = f.thickness_options(rows)
    selected_thickness = next(
        (i + 1 for i, t in enumerate(thicknesses) if f.thickness is not None and t == f.thickness), 0
    )
    return FilterChoices(
        text_choice(f.standard_options(rows), f.standard),
        text_choice(f.physical_material_options(rows), f.physical_material_name),
        FilterChoice((any_label, *(format_thickness(t) for t in thicknesses)), thicknesses, selected_thickness),
        text_choice(f.bend_radius_options(rows), f.bend_radius),
    )


# ---- Context menus ----


class MaterialMenu:
    """Ids in distinct ranges per tree, so a stray id is never mistaken for another tree's command."""

    ASSIGN: Final = 101
    PROPERTIES: Final = 103
    REFRESH: Final = 104
    APPLY_SHEET_METAL_PREFERENCE: Final = 105


class AssignmentMenu:
    SELECT_BODIES: Final = 201
    REMOVE_MATERIAL: Final = 202
    REFRESH: Final = 203
    ADD_TO_BODY_SELECTION: Final = 204


class PendingMenu:
    REMOVE: Final = 301
    CLEAR_ALL: Final = 302


def material_menu(session: AssignmentSession, clicked: MaterialPick | None, has_bodies: bool) -> tuple[MenuItem, ...]:
    text = session.text
    if clicked is None:
        return (MenuItem(MaterialMenu.REFRESH, text.menu_refresh),)
    # Assignment needs a target, and the selection block is the only source of one.
    items = [MenuItem(MaterialMenu.ASSIGN, text.menu_add_to_pending, has_bodies)]
    # Sets the part's preferences straight away. Only a row can be applied, and only on a part with no solid body:
    # once there are bodies, the preferences go with their material.
    if session.is_sheet_metal_library and not session.part_has_solid:
        items.append(
            MenuItem(
                MaterialMenu.APPLY_SHEET_METAL_PREFERENCE,
                text.menu_apply_sheet_metal_preference,
                clicked.row is not None,
            )
        )
    items += [
        SEPARATOR,
        MenuItem(MaterialMenu.PROPERTIES, text.menu_properties),
        MenuItem(MaterialMenu.REFRESH, text.menu_refresh),
    ]
    return tuple(items)


def assignment_menu(session: AssignmentSession, clicked: AssignmentRowRef | None) -> tuple[MenuItem, ...]:
    text = session.text
    if clicked is None:
        return (MenuItem(AssignmentMenu.REFRESH, text.menu_refresh),)
    has_solid = any(session.support.is_solid(b) for b in clicked.bodies)
    has_material = any(
        (a := session.assignments.get(b.id)) is not None and a.material_name is not None for b in clicked.bodies
    )
    return (
        MenuItem(AssignmentMenu.SELECT_BODIES, text.menu_select_bodies),
        MenuItem(AssignmentMenu.ADD_TO_BODY_SELECTION, text.menu_add_to_body_selection, has_solid),
        MenuItem(AssignmentMenu.REMOVE_MATERIAL, text.menu_remove_material, has_material),
        SEPARATOR,
        MenuItem(AssignmentMenu.REFRESH, text.menu_refresh),
    )


def pending_menu(session: AssignmentSession, clicked: PendingRowRef | None) -> tuple[MenuItem, ...]:
    text = session.text
    clear_all = MenuItem(PendingMenu.CLEAR_ALL, text.menu_clear_all_pending, bool(session.pending))
    if clicked is None:
        return (clear_all,)
    # Nothing is applied from here: Apply/OK apply the whole pending list at once.
    return (MenuItem(PendingMenu.REMOVE, text.menu_remove_from_pending), SEPARATOR, clear_all)
