"""The preferred material: one per part, staged in the pending list, written to the part attribute after Apply."""

from __future__ import annotations

from banxopen.foundation import BodyKind
from banxopen.foundation.ui import CHECKED, UNCHECKED
from banxopen.ui_material_assignment.pending import PendingAssignment, PendingPreferred
from banxopen.ui_material_assignment.rows import (
    AssignmentMenu,
    MaterialMenu,
    PendingColumn,
    PendingMenu,
    PendingRowRef,
    assignment_menu,
    assignment_rows,
    material_menu,
    pending_menu,
    pending_rows,
)
from banxopen.ui_material_assignment.session import AssignmentSettings, MaterialPick
from test_presenter import presenter
from test_session import AL2024, ALU, R2024, STEEL, opened, plain_world, sheet_metal_world

from builders import assigned, body, ids

UNOBTAINIUM = "Unobtainium"
"""A material no body has and no pending change assigns."""


def item(items, item_id):
    return next(i for i in items if i.id == item_id)


def root(rows, text):
    return next(r for r in rows if r.text == text)


# ---- The save gate ----


def test_apply_is_refused_while_no_preferred_material_is_defined():
    w = plain_world(body("b1"))
    s = opened(w)
    s.stage(MaterialPick(STEEL), ids("b1"))

    assert not s.apply([])

    assert w.dialogs.errors == [s.text.preferred_required(False)]
    assert w.part.applied == []
    assert len(s.pending) == 1


def test_ok_is_refused_while_no_preferred_material_is_defined():
    w = plain_world(body("b1"))
    s = opened(w)
    s.stage(MaterialPick(STEEL), ids("b1"))

    assert not s.ok([])
    assert w.part.applied == []


def test_ok_with_no_changes_closes_without_a_preferred_material():
    w = plain_world(body("b1"))
    s = opened(w)

    assert s.ok([])
    assert w.part.preferred_writes == []


def test_the_part_preferred_material_satisfies_the_gate_and_is_not_rewritten():
    w = plain_world(body("b1"), preferred="Steel")
    s = opened(w)
    s.stage(MaterialPick(ALU), ids("b1"))

    assert s.apply([])

    assert w.part.preferred_writes == []


# ---- Staging a preferred material ----


def test_any_material_may_be_preferred_without_a_warning_by_default():
    w = plain_world(body("b1"))
    s = opened(w)

    s.set_preferred(UNOBTAINIUM)

    assert s.pending_preferred == UNOBTAINIUM
    assert w.dialogs.infos == [] and w.dialogs.errors == []


def test_the_not_in_part_warning_informs_but_still_stages_when_switched_on():
    w = plain_world(body("b1"), settings=AssignmentSettings(warn_preferred_not_in_part=True))
    s = opened(w)

    s.set_preferred(UNOBTAINIUM)

    assert s.pending_preferred == UNOBTAINIUM
    assert w.dialogs.infos == [(s.text.title, s.text.preferred_not_on_any_body(UNOBTAINIUM))]


def test_the_warning_is_not_shown_for_a_material_a_pending_change_assigns():
    w = plain_world(body("b1"), settings=AssignmentSettings(warn_preferred_not_in_part=True))
    s = opened(w)
    s.stage(MaterialPick(ALU), ids("b1"))

    s.set_preferred("Aluminium")

    assert w.dialogs.infos == []


def test_choosing_the_part_value_drops_the_pending_change():
    w = plain_world(body("b1"), preferred="Steel")
    s = opened(w)
    s.set_preferred("Aluminium")

    s.set_preferred("steel")

    assert s.pending_preferred is None
    assert not s.has_changes


def test_a_new_preferred_material_replaces_the_earlier_change():
    s = opened(plain_world(body("b1")))
    s.set_preferred("Steel")

    s.set_preferred("Aluminium")

    assert s.pending_preferred == "Aluminium"
    assert s.pending_count == 1


def test_toggle_removes_a_pending_preferred_change():
    s = opened(plain_world(body("b1"), preferred="Steel"))
    s.set_preferred("Aluminium")

    s.toggle_preferred("Aluminium")

    assert s.pending_preferred is None
    assert s.effective_preferred == "Steel"


def test_the_part_own_value_cannot_be_unset():
    s = opened(plain_world(body("b1"), preferred="Steel"))

    assert not s.can_unset_preferred("Steel")
    s.toggle_preferred("Steel")
    assert s.effective_preferred == "Steel" and not s.has_changes


def test_clear_all_pending_and_cancel_drop_the_preferred_change():
    s = opened(plain_world(body("b1")))
    s.set_preferred("Steel")
    s.clear_pending()
    assert s.pending_preferred is None

    s.set_preferred("Steel")
    assert s.cancel()
    assert s.pending_preferred is None


def test_cancel_counts_the_preferred_change_as_a_pending_change():
    w = plain_world(body("b1"), answers=[False])
    s = opened(w)
    s.set_preferred("Steel")

    assert not s.cancel()

    assert w.dialogs.asked == [s.text.discard_pending(1)]


def test_removing_the_preferred_entry_drops_the_change():
    s = opened(plain_world(body("b1")))
    s.set_preferred("Steel")

    s.remove_from_pending([PendingPreferred("Steel")], ())

    assert s.pending_preferred is None


def test_removing_the_checked_assignment_entry_keeps_the_change_as_its_own_entry():
    s = opened(plain_world(body("b1")))
    s.stage(MaterialPick(STEEL), ids("b1"))
    s.set_preferred("Steel")
    assert s.preferred_on_entry

    s.remove_from_pending(list(s.pending), ())

    assert s.pending_preferred == "Steel"
    assert not s.preferred_on_entry and s.pending_count == 1


# ---- Writing it ----


def test_apply_writes_the_preferred_material_after_the_assignments():
    w = plain_world(body("b1"))
    s = opened(w)
    s.stage(MaterialPick(STEEL), ids("b1"))
    s.set_preferred("Steel")

    assert s.apply([])

    assert w.part.preferred_writes == ["Steel"]
    assert s.part_preferred == "Steel"
    assert s.pending_preferred is None and s.pending == []


def test_apply_with_only_a_preferred_change_writes_it():
    w = plain_world(body("b1"), assignments=[assigned("b1", "Steel")])
    s = opened(w)
    s.set_preferred("Steel")

    assert s.apply([])

    assert w.part.preferred_writes == ["Steel"]
    assert w.dialogs.errors == []


def test_a_material_on_no_body_is_written_and_noted_when_the_warning_is_on():
    w = plain_world(body("b1"), settings=AssignmentSettings(warn_preferred_not_in_part=True))
    s = opened(w)
    s.set_preferred(UNOBTAINIUM)

    assert s.ok([])

    assert w.part.preferred_writes == [UNOBTAINIUM]
    assert s.text.preferred_not_on_any_body_after_apply(UNOBTAINIUM) in w.dialogs.infos[-1][1]


def test_a_failed_write_keeps_the_change_pending_and_the_dialog_open():
    w = plain_world(body("b1"))
    w.part.fail_preferred_write = "NX said no"
    s = opened(w)
    s.set_preferred("Steel")

    assert not s.ok([])

    assert s.pending_preferred == "Steel"
    assert "NX said no" in w.dialogs.errors[-1]


# ---- Sheet metal part: follows the sheet metal body ----


def test_on_a_sheet_metal_part_the_preferred_material_follows_the_pending_body_material():
    w = sheet_metal_world(body("sm", BodyKind.SHEET_METAL))
    s = opened(w)
    s.stage(MaterialPick(AL2024, R2024), ids("sm"))

    assert s.pending_preferred == "2024-O"
    assert s.preferred_on_entry

    assert s.apply([])
    assert w.part.preferred_writes == ["2024-O"]


def test_on_a_sheet_metal_part_set_as_preferred_is_ignored():
    w = sheet_metal_world(body("sm", BodyKind.SHEET_METAL), assignments=[assigned("sm", "2024-O")], preferred="2024-O")
    s = opened(w)

    s.set_preferred("Steel")

    assert s.pending_preferred is None and not s.has_changes


def test_an_out_of_sync_sheet_metal_part_has_the_body_material_pending():
    w = sheet_metal_world(body("sm", BodyKind.SHEET_METAL), assignments=[assigned("sm", "2024-O")], preferred="Old")
    s = opened(w)

    assert s.pending_preferred == "2024-O"
    assert s.pending_count == 1

    assert s.ok([])
    assert w.part.preferred_writes == ["2024-O"]


def test_removing_the_sheet_metal_body_material_leaves_no_preferred_material_and_apply_refuses():
    w = sheet_metal_world(body("sm", BodyKind.SHEET_METAL), assignments=[assigned("sm", "2024-O")], preferred="2024-O")
    s = opened(w)
    s.stage_removal(ids("sm"))

    assert not s.apply([])

    assert w.dialogs.errors == [s.text.preferred_required(True)]


# ---- Rows ----


def test_the_current_tree_checks_the_part_value_first_and_ignores_pending_changes():
    s = opened(
        plain_world(
            body("b1"), body("b2"), body("b3"),
            assignments=[assigned("b1", "Aluminium"), assigned("b2", "Steel")],
            preferred="Steel",
        )
    )  # fmt: skip
    s.set_preferred("Aluminium")

    rows = assignment_rows(s)

    assert [r.text for r in rows] == ["Steel", "Aluminium", s.text.unassigned]
    assert [r.state for r in rows] == [CHECKED, UNCHECKED, None]
    assert rows[0].children[0].state is None


def test_a_preferred_change_with_no_assignment_entry_is_its_own_entry_listed_first():
    s = opened(plain_world(body("b1"), preferred="Steel"))
    s.stage(MaterialPick(STEEL), ids("b1"))
    s.set_preferred(UNOBTAINIUM)

    first, second = pending_rows(s)

    assert first.text == s.text.preferred_entry(UNOBTAINIUM) and first.state is CHECKED
    assert first.value is not None and isinstance(first.value.entry, PendingPreferred)
    assert first.columns[PendingColumn.KIND] == s.text.kind_preferred
    assert "Steel" in first.columns[PendingColumn.STATUS]
    assert second.state is UNCHECKED


def test_a_preferred_change_is_checked_on_its_assignment_entry_listed_first():
    s = opened(plain_world(body("b1"), body("b2"), preferred="Steel"))
    s.stage(MaterialPick(STEEL), ids("b1"))
    s.stage(MaterialPick(ALU), ids("b2"))
    s.set_preferred("Aluminium")

    rows = pending_rows(s)

    assert [r.text for r in rows] == ["Aluminium", "Steel"]
    assert [r.state for r in rows] == [CHECKED, UNCHECKED]
    assert [e.material.name for e in s.pending if isinstance(e, PendingAssignment)] == ["Steel", "Aluminium"]


def test_a_removal_entry_has_no_box():
    s = opened(plain_world(body("b1"), assignments=[assigned("b1", "Steel")]))
    s.stage_removal(ids("b1"))

    [entry] = pending_rows(s)

    assert entry.state is None


# ---- Menus ----


def test_set_as_preferred_is_offered_in_every_tree():
    s = opened(plain_world(body("b1"), body("b2"), assignments=[assigned("b1", "Aluminium")], preferred="Steel"))
    s.stage(MaterialPick(ALU), ids("b2"))
    group = root(assignment_rows(s), "Aluminium")
    [entry] = pending_rows(s)

    for menu_item in (
        item(material_menu(s, MaterialPick(ALU), False), MaterialMenu.SET_PREFERRED),
        item(assignment_menu(s, group.value), AssignmentMenu.SET_PREFERRED),
        item(pending_menu(s, entry.value), PendingMenu.SET_PREFERRED),
    ):
        assert menu_item.text == s.text.menu_set_preferred and menu_item.enabled


def test_the_staged_preferred_material_offers_remove_as_preferred():
    s = opened(plain_world(body("b1"), preferred="Steel"))
    s.set_preferred("Aluminium")

    menu_item = item(material_menu(s, MaterialPick(ALU), False), MaterialMenu.SET_PREFERRED)

    assert menu_item.text == s.text.menu_remove_preferred and menu_item.enabled


def test_the_part_value_shows_remove_as_preferred_disabled():
    s = opened(plain_world(body("b1"), assignments=[assigned("b1", "Steel")], preferred="Steel"))
    [group] = assignment_rows(s)

    menu_item = item(assignment_menu(s, group.value), AssignmentMenu.SET_PREFERRED)

    assert menu_item.text == s.text.menu_remove_preferred and not menu_item.enabled


def test_set_as_preferred_is_disabled_on_a_sheet_metal_part_and_on_unassigned_and_removal_rows():
    sm = opened(sheet_metal_world(body("sm", BodyKind.SHEET_METAL)))
    assert not item(material_menu(sm, MaterialPick(AL2024), False), MaterialMenu.SET_PREFERRED).enabled

    s = opened(plain_world(body("b1"), body("b2"), assignments=[assigned("b2", "Steel")]))
    unassigned = root(assignment_rows(s), s.text.unassigned)
    assert not item(assignment_menu(s, unassigned.value), AssignmentMenu.SET_PREFERRED).enabled
    s.stage_removal(ids("b2"))
    [removal] = pending_rows(s)
    assert not item(pending_menu(s, removal.value), PendingMenu.SET_PREFERRED).enabled


def test_the_preferred_entry_menu_removes_it():
    s = opened(plain_world(body("b1")))
    s.set_preferred("Steel")
    [entry] = pending_rows(s)

    items = pending_menu(s, entry.value)

    assert [i.id for i in items if not i.is_separator] == [PendingMenu.REMOVE, PendingMenu.CLEAR_ALL]


# ---- Presenter ----


def test_the_menu_command_stages_the_preferred_material_and_redraws():
    w = plain_world(body("b1"))
    p, view = presenter(w)
    p.on_shown()

    p.on_material_command(MaterialMenu.SET_PREFERRED, [MaterialPick(STEEL)])

    assert w.session.pending_preferred == "Steel"
    assert view.trees["pending"][0].text == w.session.text.preferred_entry("Steel")


def test_the_pending_remove_command_drops_the_preferred_entry():
    w = plain_world(body("b1"))
    p, view = presenter(w)
    p.on_shown()
    w.session.set_preferred("Steel")

    p.on_pending_command(PendingMenu.REMOVE, [PendingRowRef(PendingPreferred("Steel"), None)])

    assert w.session.pending_preferred is None
    assert view.trees["pending"] == []


def test_a_current_tree_box_click_stages_and_redraws_both_trees():
    w = plain_world(body("b1"), body("b2"), assignments=[assigned("b1", "Steel"), assigned("b2", "Aluminium")])
    p, view = presenter(w)
    p.on_shown()
    group = root(view.trees["assignments"], "Aluminium")
    view.trees.clear()

    p.on_assignment_state_changed(group.value)

    assert w.session.pending_preferred == "Aluminium"
    assert "assignments" in view.trees and "pending" in view.trees


def test_a_click_on_the_checked_pending_box_unchecks_it():
    w = plain_world(body("b1"))
    p, view = presenter(w)
    p.on_shown()
    w.session.stage(MaterialPick(STEEL), ids("b1"))
    w.session.set_preferred("Steel")
    [entry] = pending_rows(w.session)

    p.on_pending_state_changed(entry.value)

    assert w.session.pending_preferred is None
    assert view.trees["pending"][0].state is UNCHECKED


def test_a_click_on_the_preferred_entry_box_changes_nothing_but_redraws():
    w = plain_world(body("b1"))
    p, view = presenter(w)
    p.on_shown()
    w.session.set_preferred("Steel")
    [entry] = pending_rows(w.session)
    view.trees.clear()

    p.on_pending_state_changed(entry.value)

    assert w.session.pending_preferred == "Steel"
    assert view.trees["pending"][0].state is CHECKED
