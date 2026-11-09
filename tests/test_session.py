"""The dialog's pending-list behaviour (README.md's decision tree), against the real material rules on a fake part."""

import dataclasses

from banxopen.foundation import BodyId, BodyKind, OperationResult
from banxopen.materials import MaterialPropertyValue
from banxopen.sheetmetal import NO_FILTER, SheetMetalRowFilter
from banxopen.ui_material_assignment.pending import PendingAssignment, PendingBodyStatus, PendingRemoval
from banxopen.ui_material_assignment.session import MaterialPick, Section

from builders import (
    PLAIN,
    SHEET_METAL,
    assigned,
    body,
    ids,
    library,
    material,
    preference,
    row,
    world,
)

STEEL = material("Steel")
ALU = material("Aluminium")
AL2024 = material("2024-O", SHEET_METAL)
AL6061 = material("6061-T6", SHEET_METAL)
R2024 = row("2024-O_0.032", "2024-O")
R2024_THICK = row("2024-O_0.063", "2024-O", thickness=0.063)
R6061 = row("6061-T6_0.032", "6061-T6")


def opened(w):
    w.session.show()
    w.session.check_on_open()
    w.session.take_changes()
    return w.session


def plain_world(*bodies, **kwargs):
    return world(list(bodies), library(PLAIN, STEEL, ALU), **kwargs)


def sheet_metal_world(*bodies, **kwargs):
    kwargs.setdefault("rows", (R2024, R2024_THICK, R6061))
    return world(list(bodies), library(SHEET_METAL, AL2024, AL6061), **kwargs)


# ---- Opening ----


def test_show_loads_the_first_library_and_reads_the_part():
    w = plain_world(body("b1"))
    w.session.show()

    assert w.session.library is not None and w.session.library.id.value == PLAIN
    assert w.session.selected_library_index == 0
    assert [b.name for b in w.session.bodies] == ["b1"]
    assert {Section.LIBRARIES, Section.MATERIALS, Section.ASSIGNMENTS} <= w.session.take_changes()


def test_showing_again_keeps_the_library_in_use():
    w = world([body("b1")], library(PLAIN, STEEL), library("Other", ALU))
    s = opened(w)
    s.select_library(s.libraries[1].id)

    s.show()

    assert s.selected_library_index == 1


def test_a_sheet_metal_library_lists_only_the_standards_rows_made_of_its_materials():
    w = sheet_metal_world(body("sm", BodyKind.SHEET_METAL), rows=(R2024, R6061, row("X", "Unlisted")))
    s = opened(w)

    assert s.is_sheet_metal_library
    assert [r.name for r in s.library_rows] == [R2024.name, R6061.name]


def allowed_for(m, value: str):
    return dataclasses.replace(m, properties=(MaterialPropertyValue("a", "AllowedFor", None, value, None),))


def test_a_mixed_library_offers_its_sheet_metal_materials_as_a_sheet_metal_library():
    sheet_only = allowed_for(material("2024-O"), "SheetMetal")
    both = allowed_for(material("6061-T6"), "Solid, SheetMetal")
    w = world(
        [body("sm", BodyKind.SHEET_METAL)], library(PLAIN, STEEL, sheet_only, both), rows=(R2024, R6061, R2024_THICK)
    )
    s = opened(w)

    assert [r.display_name for r in s.libraries] == [PLAIN, f"{PLAIN}_SheetMetal"]
    assert not s.is_sheet_metal_library  # the library itself stays an ordinary one
    assert s.library is not None and [m.name for m in s.library.materials] == ["Steel", "6061-T6"]

    s.select_library(s.libraries[1].id)

    assert s.is_sheet_metal_library
    assert s.library is not None and [m.name for m in s.library.materials] == ["2024-O", "6061-T6"]
    assert [r.name for r in s.library_rows] == [R2024.name, R6061.name, R2024_THICK.name]


def test_the_first_sheet_metal_library_filters_on_the_parts_preferences_row():
    w = sheet_metal_world(body("sm", BodyKind.SHEET_METAL), part_preference=preference(R6061))
    s = opened(w)

    assert s.filter.physical_material_name == "6061-T6"
    assert [r.name for r in s.filtered_rows] == [R6061.name]


# ---- Filters ----


def test_a_filter_value_the_others_no_longer_offer_falls_back_to_any():
    s = opened(sheet_metal_world(body("sm", BodyKind.SHEET_METAL)))

    s.set_filter(SheetMetalRowFilter(thickness=0.5))

    assert s.filter.thickness is None  # no row is 0.5 thick
    assert len(s.filtered_rows) == 3


def test_two_filters_that_rule_each_other_out_both_fall_back_to_any():
    s = opened(sheet_metal_world(body("sm", BodyKind.SHEET_METAL)))

    s.set_filter(SheetMetalRowFilter(physical_material_name="6061-T6", thickness=0.063))

    assert s.filter == NO_FILTER


def test_the_filter_drives_the_row_rule_standard():
    w = sheet_metal_world(body("sm", BodyKind.SHEET_METAL))
    s = opened(w)

    s.set_filter(SheetMetalRowFilter(standard="baps"))

    assert s.filter.standard == "BAPS"
    assert w.sheet_metal.standard_selection.selected == "BAPS"


def test_with_a_filter_only_materials_that_still_have_a_row_are_listed():
    s = opened(sheet_metal_world(body("sm", BodyKind.SHEET_METAL)))
    s.set_filter(SheetMetalRowFilter(physical_material_name="6061-T6"))

    categories, rows = s.material_tree()

    assert [m.name for c in categories for m in c.materials] == ["6061-T6"]
    assert [r.name for r in rows["6061-t6"]] == [R6061.name]


def test_the_only_row_the_filters_leave_is_what_apply_acts_on():
    s = opened(sheet_metal_world(body("sm", BodyKind.SHEET_METAL)))
    s.set_filter(SheetMetalRowFilter(physical_material_name="6061-T6"))

    pick = s.picked_sheet_metal_material()

    assert pick is not None and pick.row == R6061 and pick.material == AL6061


def test_clearing_the_filter_shows_everything_again():
    s = opened(sheet_metal_world(body("sm", BodyKind.SHEET_METAL)))
    s.set_filter(SheetMetalRowFilter(physical_material_name="6061-T6"))

    s.clear_filter()

    assert s.filter == NO_FILTER
    assert len(s.filtered_rows) == 3


# ---- Add to pending ----


def test_add_to_pending_with_no_selection_says_so():
    w = plain_world(body("b1"))
    s = opened(w)

    assert not s.stage(MaterialPick(STEEL), [])
    assert w.dialogs.errors == [s.text.select_bodies_first]


def test_add_to_pending_with_a_selection_no_longer_in_the_part_says_so():
    w = plain_world(body("b1"))
    s = opened(w)

    assert not s.stage(MaterialPick(STEEL), ids("gone"))
    assert w.dialogs.errors == [s.text.selection_not_in_part]


def test_a_warning_rides_along_in_the_staging_message():
    w = world([body("b1")], library(PLAIN, STEEL), with_display_rules=True)
    s = opened(w)

    assert s.stage(MaterialPick(STEEL), ids("b1"))

    _, message = w.dialogs.infos[-1]
    assert message.startswith("Steel added to pending for 1 body(ies).")
    assert "Warnings:\n  [b1] Material 'Steel' has no CoatingStudioMaterialName defined" in message


def test_add_to_pending_stages_without_touching_the_part():
    w = plain_world(body("b1"), body("b2"))
    s = opened(w)

    assert s.stage(MaterialPick(STEEL), ids("b1", "b2"))

    [entry] = s.pending
    assert isinstance(entry, PendingAssignment) and entry.body_ids == tuple(ids("b1", "b2"))
    assert w.part.applied == []
    assert w.dialogs.infos == [] and w.dialogs.errors == []  # a clean add needs no message


def test_a_body_that_already_has_the_material_is_not_staged_and_its_pending_change_is_dropped():
    w = plain_world(body("b1"), assignments=[assigned("b1", "Steel")])
    s = opened(w)
    s.stage_removal(ids("b1"))

    assert not s.stage(MaterialPick(STEEL), ids("b1"))

    assert s.pending == []
    [(_, message)] = w.dialogs.infos[-1:]
    assert message.startswith("Nothing to add to pending.")
    assert "[b1] already has Steel; its earlier pending change was removed" in message


def test_a_reassignment_is_staged_once_confirmed():
    w = plain_world(body("b1"), assignments=[assigned("b1", "Aluminium")], answers=[True])
    s = opened(w)

    assert s.stage(MaterialPick(STEEL), ids("b1"))

    [entry] = s.pending
    assert isinstance(entry, PendingAssignment)
    assert entry.confirmed == {BodyId("b1")}
    assert w.dialogs.asked[0].startswith("1 body(ies) need confirmation for Steel:")


def test_a_declined_reassignment_is_reported_and_not_staged():
    w = plain_world(body("b1"), assignments=[assigned("b1", "Aluminium")], answers=[False])
    s = opened(w)

    assert not s.stage(MaterialPick(STEEL), ids("b1"))

    assert s.pending == []
    assert w.dialogs.errors[-1].startswith("Steel was not added to pending.")
    assert "[b1] skipped: not confirmed" in w.dialogs.errors[-1]


def test_a_blocked_body_is_reported_and_keeps_its_earlier_pending_claim():
    w = plain_world(body("b1"), body("sm", BodyKind.SHEET_METAL))
    s = opened(w)
    s.stage(MaterialPick(ALU), ids("b1"))

    assert s.stage(MaterialPick(STEEL), ids("b1", "sm"))  # Steel is no sheet metal material: sm is blocked

    staged = s.pending[-1]
    assert isinstance(staged, PendingAssignment) and staged.body_ids == tuple(ids("b1"))
    _, message = w.dialogs.infos[-1]
    assert message.startswith("Steel added to pending for 1 body(ies).")
    assert "[sm] blocked:" in message


def test_the_latest_action_replaces_an_earlier_claim():
    w = plain_world(body("b1"), body("b2"))
    s = opened(w)
    s.stage(MaterialPick(ALU), ids("b1", "b2"))

    s.stage(MaterialPick(STEEL), ids("b1"))

    first, second = s.pending
    assert isinstance(first, PendingAssignment) and first.material == ALU and first.body_ids == tuple(ids("b2"))
    assert isinstance(second, PendingAssignment) and second.material == STEEL


def test_a_plain_material_on_a_sheet_metal_body_needs_a_row():
    w = sheet_metal_world(body("sm", BodyKind.SHEET_METAL))
    s = opened(w)

    assert not s.stage(MaterialPick(AL2024), ids("sm"))

    assert w.dialogs.errors == [s.text.sheet_metal_needs_row("2024-O")]
    assert s.pending == []


def test_a_second_sheet_metal_material_in_the_part_is_a_conflict():
    w = sheet_metal_world(
        body("sm1", BodyKind.SHEET_METAL),
        body("sm2", BodyKind.SHEET_METAL),
        assignments=[assigned("sm2", "6061-T6")],
        part_preference=preference(R6061, count=2),
    )
    s = opened(w)

    assert not s.stage(MaterialPick(AL2024, R2024), ids("sm1"))

    assert "cannot be assigned to sheet metal bodies in this part" in w.dialogs.errors[-1]
    assert "[sm2] 6061-T6 [6061-T6_0.032]" in w.dialogs.errors[-1]


def test_a_staged_assignment_that_replaces_a_removal_says_so():
    w = plain_world(body("b1"), assignments=[assigned("b1", "Aluminium")])
    s = opened(w)
    s.stage_removal(ids("b1"))

    s.stage(MaterialPick(STEEL), ids("b1"))

    [entry] = s.pending
    assert isinstance(entry, PendingAssignment)
    _, message = w.dialogs.infos[-1]
    assert "Replaced:\n  [b1] its pending removal was replaced" in message


# ---- Remove material ----


def test_remove_material_skips_a_body_with_none():
    w = plain_world(body("b1"), body("b2"), assignments=[assigned("b1", "Steel")])
    s = opened(w)

    s.stage_removal(ids("b1", "b2"))

    [removal] = s.pending
    assert isinstance(removal, PendingRemoval) and removal.body_ids == tuple(ids("b1"))
    _, message = w.dialogs.infos[-1]
    assert message.startswith("Material removal added to pending for 1 body(ies).")
    assert "[b2] has no material" in message


def test_remove_material_replaces_a_pending_assignment():
    w = plain_world(body("b1"), assignments=[assigned("b1", "Aluminium")])
    s = opened(w)
    s.stage(MaterialPick(STEEL), ids("b1"))

    s.stage_removal(ids("b1"))

    [removal] = s.pending
    assert isinstance(removal, PendingRemoval)
    assert "[b1] its pending assignment to Steel was replaced" in w.dialogs.infos[-1][1]


def test_the_removal_entry_stays_first_and_single():
    w = plain_world(body("b1"), body("b2"), body("b3"), assignments=[assigned("b1", "Steel"), assigned("b2", "Steel")])
    s = opened(w)
    s.stage(MaterialPick(ALU), ids("b3"))
    s.stage_removal(ids("b1"))

    s.stage_removal(ids("b2"))

    removal, assignment = s.pending
    assert isinstance(removal, PendingRemoval) and removal.body_ids == tuple(ids("b1", "b2"))
    assert isinstance(assignment, PendingAssignment)


def test_remove_material_with_nothing_selected_says_so():
    w = plain_world(body("b1"))
    s = opened(w)

    s.stage_removal([])

    assert w.dialogs.errors == [s.text.select_bodies_to_remove]


# ---- Removing from pending ----


def test_remove_from_pending_drops_a_whole_entry_or_one_body():
    w = plain_world(body("b1"), body("b2"), body("b3"))
    s = opened(w)
    s.stage(MaterialPick(STEEL), ids("b1", "b2"))
    s.stage(MaterialPick(ALU), ids("b3"))
    steel, alu = s.pending
    assert isinstance(steel, PendingAssignment)

    s.remove_from_pending([alu], {BodyId("b1")})

    [left] = s.pending
    assert left.body_ids == tuple(ids("b2"))
    assert isinstance(left, PendingAssignment) and left.material == steel.material


def test_clear_pending_never_touches_the_part():
    w = plain_world(body("b1"))
    s = opened(w)
    s.stage(MaterialPick(STEEL), ids("b1"))

    s.clear_pending()

    assert s.pending == [] and w.part.applied == []


# ---- Apply ----


def test_apply_with_nothing_pending_says_so():
    w = plain_world(body("b1"))
    s = opened(w)

    assert not s.apply([])
    assert w.dialogs.errors == [s.text.nothing_pending(False)]


def test_apply_applies_the_removal_then_each_assignment():
    w = plain_world(body("b1"), body("b2"), assignments=[assigned("b2", "Steel")])
    s = opened(w)
    s.stage(MaterialPick(STEEL), ids("b1"))
    s.stage_removal(ids("b2"))

    assert s.apply([])

    assert s.pending == []
    assert w.part.cleared == [ids("b2")]
    assert s.assignments[BodyId("b1")].material_name == "Steel"
    assert s.assignments[BodyId("b2")].material_name is None
    assert w.dialogs.errors == [] and w.dialogs.infos == []


def test_a_body_nx_refuses_stays_pending_with_the_reason():
    w = plain_world(body("b1"), body("b2"), fail_on={"b2": "NX 123: no"})
    s = opened(w)
    s.stage(MaterialPick(STEEL), ids("b1", "b2"))

    s.apply([])

    [left] = s.pending
    [row_left] = left.rows
    assert row_left.body.id == BodyId("b2") and row_left.status is PendingBodyStatus.NOT_APPLIED
    assert row_left.message == "NX 123: no"
    assert w.dialogs.errors[-1].startswith("Some pending changes were not applied and are still pending:")
    assert "Steel:\n  [b2] NX 123: no" in w.dialogs.errors[-1]


def test_ok_keeps_the_dialog_open_while_something_is_still_pending():
    w = plain_world(body("b1"), fail_on={"b1": "refused"})
    s = opened(w)
    s.stage(MaterialPick(STEEL), ids("b1"))

    assert not s.ok([])


def test_ok_with_nothing_pending_closes():
    s = opened(plain_world(body("b1")))

    assert s.ok([])


def test_a_body_gone_from_the_part_is_reported_and_dropped():
    w = plain_world(body("b1"), body("b2"))
    s = opened(w)
    s.stage(MaterialPick(STEEL), ids("b1", "b2"))
    w.part.bodies.pop()

    assert s.apply([])

    assert s.pending == []
    _, message = w.dialogs.infos[-1]
    assert message.startswith("The pending changes were applied, with these notes:")
    assert "[b2] no longer in the work part" in message


def test_apply_asks_for_a_confirmation_that_arose_after_staging():
    w = plain_world(body("b1"), answers=[True])
    s = opened(w)
    s.stage(MaterialPick(STEEL), ids("b1"))
    w.part.assignments[BodyId("b1")] = assigned("b1", "Aluminium")  # changed under the dialog

    s.apply([])

    assert w.dialogs.asked[-1].startswith("1 body(ies) need confirmation for Steel:")
    assert s.assignments[BodyId("b1")].material_name == "Steel"


def test_a_confirmation_given_when_staging_is_not_asked_again():
    w = plain_world(body("b1"), assignments=[assigned("b1", "Aluminium")], answers=[True])
    s = opened(w)
    s.stage(MaterialPick(STEEL), ids("b1"))

    s.apply([])

    assert len(w.dialogs.asked) == 1
    assert s.assignments[BodyId("b1")].material_name == "Steel"


def test_a_confirmation_declined_at_apply_keeps_the_body_pending():
    w = plain_world(body("b1"), answers=[False])
    s = opened(w)
    s.stage(MaterialPick(STEEL), ids("b1"))
    w.part.assignments[BodyId("b1")] = assigned("b1", "Aluminium")

    s.apply([])

    [left] = s.pending
    assert left.rows[0].message == "not confirmed"


def test_cancel_with_pending_changes_asks_first():
    w = plain_world(body("b1"), answers=[False, True])
    s = opened(w)
    s.stage(MaterialPick(STEEL), ids("b1"))

    assert not s.cancel()
    assert s.pending
    assert s.cancel()
    assert s.pending == []
    assert w.dialogs.asked[0] == s.text.discard_pending(1)


def test_refresh_drops_pending_bodies_that_are_gone():
    w = plain_world(body("b1"), body("b2"))
    s = opened(w)
    s.stage(MaterialPick(STEEL), ids("b1", "b2"))
    w.part.bodies.pop()

    s.refresh()

    assert s.pending[0].body_ids == tuple(ids("b1"))


# ---- A picked sheet metal material with nothing pending ----


def test_a_picked_row_with_bodies_selected_is_staged_and_applied():
    w = sheet_metal_world(body("sm", BodyKind.SHEET_METAL))
    s = opened(w)
    s.pick(MaterialPick(AL2024, R2024))

    assert s.apply(ids("sm"))

    assert s.assignments[BodyId("sm")].material_name == "2024-O"
    assert s.pending == []


def test_a_picked_row_on_a_part_with_no_solid_sets_only_the_preferences_after_asking():
    w = sheet_metal_world(answers=[True])
    s = opened(w)
    s.pick(MaterialPick(AL2024, R2024))

    assert s.apply([])

    assert w.sheet_metal.set_rows == [R2024]
    assert w.dialogs.asked[0].startswith("This part has no solid body, so only its Sheet Metal Preferences")
    assert w.dialogs.results[-1][1] == "Preferences set."


def test_a_picked_row_with_solids_but_none_selected_is_refused():
    w = sheet_metal_world(body("sm", BodyKind.SHEET_METAL))
    s = opened(w)
    s.pick(MaterialPick(AL2024, R2024))

    assert not s.apply([])
    assert w.dialogs.errors == [s.text.no_solid_selected_for_row(R2024.name)]


def test_ok_with_a_picked_row_but_no_selection_on_a_part_with_bodies_just_closes():
    w = sheet_metal_world(body("sm", BodyKind.SHEET_METAL))
    s = opened(w)
    s.pick(MaterialPick(AL2024, R2024))

    assert s.ok([])
    assert w.dialogs.errors == []


def test_a_refused_preferences_change_is_shown():
    w = sheet_metal_world(answers=[True])
    w.sheet_metal.set_result = OperationResult.fail("X", "NX refused")
    s = opened(w)

    assert not s.apply_preference_only(R2024)
    assert not w.dialogs.results[-1][0].ok


# ---- On open: Sheet Metal Preferences sync ----


def test_on_open_a_single_out_of_sync_sheet_metal_body_is_staged_with_the_preferences_row():
    w = sheet_metal_world(
        body("sm", BodyKind.SHEET_METAL),
        assignments=[assigned("sm", "6061-T6")],
        part_preference=preference(R2024),
    )
    w.session.show()

    assert w.session.check_on_open() is None

    [entry] = w.session.pending
    assert isinstance(entry, PendingAssignment) and entry.row == R2024 and entry.material == AL2024
    assert entry.confirmed == {BodyId("sm")}  # replacing the material is what syncing means
    title, message = w.dialogs.infos[-1]
    assert title == w.session.text.sheet_metal_preferences_title
    assert "was added to pending for the body. Apply to sync them." in message


def test_on_open_a_body_whose_row_material_is_not_in_the_library_is_selected_instead():
    unlisted = row("7075_0.032", "7075")
    w = sheet_metal_world(
        body("sm", BodyKind.SHEET_METAL),
        assignments=[assigned("sm", "6061-T6")],
        rows=(R2024, R6061, unlisted),
        part_preference=preference(unlisted),
    )
    w.session.show()

    assert w.session.check_on_open() == (BodyId("sm"),)
    assert w.session.pending == []
    assert "The body was added to the selection." in w.dialogs.infos[-1][1]


def test_on_open_runs_once():
    w = sheet_metal_world(
        body("sm", BodyKind.SHEET_METAL),
        assignments=[assigned("sm", "6061-T6")],
        part_preference=preference(R2024),
    )
    s = opened(w)
    s.clear_pending()
    s.show()

    assert s.check_on_open() is None
    assert s.pending == []


def test_on_open_bodies_in_sync_say_nothing():
    w = sheet_metal_world(
        body("sm", BodyKind.SHEET_METAL),
        assignments=[assigned("sm", "2024-O")],
        part_preference=preference(R2024),
    )
    opened(w)

    assert w.dialogs.infos == []


# ---- Quick selection ----


def test_select_unassigned_lists_solids_with_no_material():
    w = plain_world(body("b1"), body("b2"), body("s", BodyKind.SHEET), assignments=[assigned("b1", "Steel")])
    s = opened(w)

    assert s.unassigned_solids() == (BodyId("b2"),)
    assert s.all_solids() == tuple(ids("b1", "b2"))


def test_select_unassigned_when_every_solid_has_a_material_says_so():
    w = plain_world(body("b1"), assignments=[assigned("b1", "Steel")])
    s = opened(w)

    assert s.unassigned_solids() is None
    assert w.dialogs.errors == [s.text.every_solid_has_material]


def test_adding_rows_to_the_selection_keeps_what_was_selected():
    w = plain_world(body("b1"), body("b2"), body("s", BodyKind.SHEET))
    s = opened(w)

    assert s.with_solids_added([body("b2"), body("s", BodyKind.SHEET)], ids("b1")) == tuple(ids("b1", "b2"))
    assert s.with_solids_added([body("s", BodyKind.SHEET)], ids("b1")) is None
    assert w.dialogs.errors == [s.text.no_solid_body_in_rows]
