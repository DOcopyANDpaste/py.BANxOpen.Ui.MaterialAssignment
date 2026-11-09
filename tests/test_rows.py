"""What the trees, dropdowns and menus show."""

from banxopen.foundation import BodyKind
from banxopen.materials import DisplayMaterial, MaterialId
from banxopen.sheetmetal import SheetMetalRowFilter
from banxopen.ui_material_assignment.rows import (
    AssignmentColumn,
    AssignmentMenu,
    MaterialColumn,
    MaterialMenu,
    PendingColumn,
    PendingMenu,
    PropertyColumn,
    assignment_columns,
    assignment_groups,
    assignment_menu,
    assignment_rows,
    filter_choices,
    material_menu,
    material_rows,
    pending_menu,
    pending_rows,
    property_rows,
    tooltip,
)
from banxopen.ui_material_assignment.session import MaterialPick
from test_session import AL2024, AL6061, R2024, R6061, STEEL, opened, sheet_metal_world

from builders import PLAIN, SHEET_METAL, assigned, body, ids, library, material, preference, world


def test_the_material_tree_lists_categories_then_materials_with_description_and_density():
    steel = material("Steel", density="7850")
    s = opened(world([body("b1")], library(PLAIN, steel)))

    [category] = material_rows(s)

    assert category.text == "Alloys" and category.value is None
    [node] = category.children
    assert node.value == MaterialPick(steel)
    assert node.columns[MaterialColumn.DENSITY] == "7850 kg/m^3"


def test_a_sheet_metal_library_lists_its_rows_under_each_material():
    s = opened(sheet_metal_world(body("sm", BodyKind.SHEET_METAL)))

    [category] = material_rows(s)
    by_name = {c.text: c for c in category.children}

    assert [r.text for r in by_name["6061-T6"].children] == [R6061.name]
    assert by_name["6061-T6"].children[0].value == MaterialPick(AL6061, R6061)
    assert by_name["6061-T6"].children[0].columns[MaterialColumn.DETAIL] == R6061.describe()


def test_the_tooltip_names_the_row_and_what_it_is_made_of():
    s = opened(sheet_metal_world())

    lines = tooltip(MaterialPick(AL2024, R2024), s.text).split("\n")

    assert lines == [R2024.name, "Sheet metal material made of 2024-O", R2024.describe(), "Alloys"]


def test_assignment_groups_put_the_unassigned_last_and_sort_bodies_by_name():
    w = world(
        [body("b2"), body("B1"), body("c")],
        library(PLAIN, STEEL),
        assignments=[assigned("b2", "Steel"), assigned("B1", "steel")],
    )
    s = opened(w)

    groups = assignment_groups(s)

    assert [g.material_label for g in groups] == ["Steel", s.text.unassigned]
    assert [b.name for b in groups[0].bodies] == ["B1", "b2"]
    assert groups[0].assignment_count == 2
    assert groups[1].is_unassigned


def test_the_assignment_tree_flags_pending_changes_beside_the_real_material():
    w = world([body("b1"), body("b2")], library(PLAIN, STEEL), assignments=[assigned("b2", "Steel")])
    s = opened(w)
    s.stage(MaterialPick(STEEL), ids("b1"))
    s.stage_removal(ids("b2"))

    rows = {r.text: r for r in assignment_rows(s)}

    unassigned = rows[s.text.unassigned]
    assert unassigned.columns[AssignmentColumn.PENDING] == "1 pending"
    assert unassigned.children[0].columns[AssignmentColumn.PENDING] == "→ Steel"
    assert rows["Steel"].children[0].columns[AssignmentColumn.PENDING] == "→ (remove material)"
    assert rows["Steel"].children[0].columns[AssignmentColumn.COUNT] == "Solid"


def test_a_confirmed_body_is_flagged_as_such():
    w = world([body("b1")], library(PLAIN, STEEL, material("Alu")), assignments=[assigned("b1", "Alu")])
    s = opened(w)
    s.stage(MaterialPick(STEEL), ids("b1"))

    [group] = assignment_rows(s)

    assert group.children[0].columns[AssignmentColumn.PENDING] == "→ Steel (confirmed)"


def test_the_display_material_column_shows_the_coating():
    coated = assigned("b1", "Steel")
    coated = type(coated)(coated.body_id, "Steel", None, DisplayMaterial(MaterialId("d"), "Zinc", (1, 2, 3)))
    s = opened(world([body("b1")], library(PLAIN, STEEL), assignments=[coated]))

    [group] = assignment_rows(s)

    assert group.children[0].columns[AssignmentColumn.DISPLAY_MATERIAL] == "Zinc"


def test_the_grade_column_appears_in_the_sheet_metal_application_only():
    w = sheet_metal_world(
        body("sm", BodyKind.SHEET_METAL),
        assignments=[assigned("sm", "2024-O")],
        part_preference=preference(R2024),
        sheet_metal_app=True,
    )
    s = opened(w)

    [group] = assignment_rows(s)

    assert group.columns[AssignmentColumn.GRADE] == R2024.name
    assert group.children[0].columns[AssignmentColumn.GRADE] == R2024.name
    assert len(assignment_columns(s.text, True)) == 5
    assert len(assignment_columns(s.text, False)) == 4


def test_the_pending_tree_shows_each_entry_and_its_bodies_status():
    w = world([body("b1"), body("b2")], library(PLAIN, STEEL), assignments=[assigned("b2", "Steel")])
    s = opened(w)
    s.stage(MaterialPick(STEEL), ids("b1"))
    s.stage_removal(ids("b2"))

    removal, steel = pending_rows(s)

    assert removal.text == "Remove material"
    assert removal.children[0].columns[PendingColumn.STATUS] == "Pending — currently Steel"
    assert steel.text == "Steel" and steel.columns[PendingColumn.KIND] == "1"
    assert steel.children[0].columns[PendingColumn.STATUS] == "Pending"


def test_a_body_apply_left_behind_shows_why():
    w = world([body("b1")], library(PLAIN, STEEL), fail_on={"b1": "refused"})
    s = opened(w)
    s.stage(MaterialPick(STEEL), ids("b1"))
    s.apply([])

    [entry] = pending_rows(s)

    assert entry.children[0].columns[PendingColumn.STATUS] == "Not applied — refused"
    [group] = assignment_rows(s)
    assert group.children[0].columns[AssignmentColumn.PENDING] == "→ Steel (not applied)"


def test_a_sheet_metal_entry_is_named_with_its_row():
    w = sheet_metal_world(body("sm", BodyKind.SHEET_METAL))
    s = opened(w)
    s.stage(MaterialPick(AL2024, R2024), ids("sm"))

    [entry] = pending_rows(s)

    assert entry.text == f"2024-O [{R2024.name}]"


def test_filter_choices_start_with_any_and_select_the_current_value():
    s = opened(sheet_metal_world(body("sm", BodyKind.SHEET_METAL)))
    s.set_filter(SheetMetalRowFilter(physical_material_name="6061-T6"))

    choices = filter_choices(s)

    assert choices.physical_material.labels == ("(Any)", "2024-O", "6061-T6")
    assert choices.physical_material.selected == 2
    assert choices.thickness.labels == ("(Any)", "0.032")
    assert choices.read(0, 2, 1, None) == SheetMetalRowFilter(None, "6061-T6", 0.032, None)


def test_the_material_menu_offers_preferences_only_on_a_part_with_no_solid():
    empty = opened(sheet_metal_world())
    with_body = opened(sheet_metal_world(body("sm", BodyKind.SHEET_METAL)))

    assert MaterialMenu.APPLY_SHEET_METAL_PREFERENCE in {
        i.id for i in material_menu(empty, MaterialPick(AL2024, R2024), False)
    }
    assert MaterialMenu.APPLY_SHEET_METAL_PREFERENCE not in {
        i.id for i in material_menu(with_body, MaterialPick(AL2024, R2024), True)
    }


def test_add_to_pending_is_disabled_without_a_selection():
    s = opened(world([body("b1")], library(PLAIN, STEEL)))

    [assign, *_] = material_menu(s, MaterialPick(STEEL), False)

    assert assign.id == MaterialMenu.ASSIGN and not assign.enabled
    assert [i.id for i in material_menu(s, None, False)] == [MaterialMenu.REFRESH]


def test_remove_material_is_disabled_for_rows_with_no_material():
    s = opened(world([body("b1")], library(PLAIN, STEEL)))
    [group] = assignment_groups(s)

    items = {i.id: i for i in assignment_menu(s, group)}

    assert not items[AssignmentMenu.REMOVE_MATERIAL].enabled
    assert items[AssignmentMenu.ADD_TO_BODY_SELECTION].enabled


def test_clear_all_pending_is_enabled_only_with_something_pending():
    s = opened(world([body("b1")], library(PLAIN, STEEL)))

    [clear] = pending_menu(s, None)

    assert clear.id == PendingMenu.CLEAR_ALL and not clear.enabled


def test_a_property_list_value_becomes_one_child_per_entry():
    m = material("Steel", density="1, 2, 3")

    [category] = property_rows(m, opened(world([], library(SHEET_METAL))).text)

    [prop] = category.children
    assert prop.text == "Density"
    assert prop.columns[PropertyColumn.VALUE] == "3 values"
    assert [c.columns[PropertyColumn.VALUE] for c in prop.children] == ["1", "2", "3"]
