"""The presenter only reads the view, calls one gesture and redraws what changed."""

from banxopen.foundation import BodyKind
from banxopen.materials import Material
from banxopen.ui_material_assignment.presenter import Block, MaterialAssignmentPresenter
from banxopen.ui_material_assignment.rows import AssignmentMenu, MaterialMenu, PendingMenu, PendingRowRef
from banxopen.ui_material_assignment.session import MaterialPick
from test_session import AL2024, R2024, STEEL, sheet_metal_world

from builders import PLAIN, assigned, body, ids, library, world


class FakeView:
    def __init__(self, selected=()):
        self.selected = list(selected)
        self.calls: list[str] = []
        self.trees: dict[str, list] = {}
        self.labels: dict[str, tuple] = {}
        self.filter_indices: tuple[int | None, int | None, int | None, int | None] = (None, None, None, None)
        self.library_index = 0

    def set_up_columns(self, material, assignment, pending):
        self.calls.append("columns")

    def clear_highlight(self):
        self.calls.append("clear_highlight")

    def show_libraries(self, names, selected):
        self.trees["libraries"] = list(names)

    def selected_library_index(self):
        return self.library_index

    def show_sheet_metal_preferences(self, visible):
        self.calls.append(f"sm_group={visible}")

    def show_filters(self, choices):
        self.trees["filters"] = [choices]

    def selected_filter_indices(self):
        return self.filter_indices

    def show_material_tree(self, rows):
        self.trees["materials"] = list(rows)

    def show_assignment_tree(self, rows):
        self.trees["assignments"] = list(rows)

    def show_pending_tree(self, rows):
        self.trees["pending"] = list(rows)

    def set_material_label(self, text, image):
        self.labels["material"] = (text, image)

    def set_assignment_label(self, text, image):
        self.labels["assignment"] = (text, image)

    def set_pending_label(self, text, image):
        self.labels["pending"] = (text, image)

    def selected_body_ids(self):
        return list(self.selected)

    def set_selected_bodies(self, body_ids):
        self.selected = list(body_ids)


class FakePropertyWindow:
    def __init__(self):
        self.shown: list[Material] = []

    def show(self, material):
        self.shown.append(material)


def presenter(w, view=None, window=None):
    view = view or FakeView()
    return MaterialAssignmentPresenter(w.session, view, w.dialogs, window), view


def test_on_shown_fills_every_section_once():
    w = world([body("b1")], library(PLAIN, STEEL))
    p, view = presenter(w)

    assert p.on_shown() == 0

    assert view.trees["libraries"] == [PLAIN]
    assert view.trees["materials"] and view.trees["assignments"]
    assert view.calls[:2] == ["columns", "clear_highlight"]


def test_on_shown_puts_the_out_of_sync_body_in_the_selection():
    from builders import preference, row

    unlisted = row("7075_0.032", "7075")
    w = sheet_metal_world(
        body("sm", BodyKind.SHEET_METAL),
        assignments=[assigned("sm", "6061-T6")],
        rows=(R2024, unlisted),
        part_preference=preference(unlisted),
    )
    p, view = presenter(w)

    p.on_shown()

    assert view.selected == ids("sm")


def test_staging_redraws_the_pending_and_assignment_trees_but_not_the_material_tree():
    w = world([body("b1")], library(PLAIN, STEEL))
    p, view = presenter(w, FakeView(ids("b1")))
    p.on_shown()
    materials = view.trees["materials"]

    p.on_material_command(MaterialMenu.ASSIGN, [MaterialPick(STEEL)])

    assert view.trees["materials"] is materials  # a rebuilt tree would lose the user's selection
    assert view.trees["pending"][0].text == "Steel"


def test_apply_returns_nonzero_when_nothing_was_done():
    w = world([body("b1")], library(PLAIN, STEEL))
    p, _ = presenter(w)
    p.on_shown()

    assert p.on_apply() == 1
    assert w.dialogs.errors


def test_ok_clears_the_highlight_when_it_closes():
    w = world([body("b1")], library(PLAIN, STEEL))
    p, view = presenter(w)
    p.on_shown()

    assert p.on_ok() == 0
    assert view.calls[-1] == "clear_highlight"


def test_cancel_declined_keeps_the_dialog_open():
    w = world([body("b1")], library(PLAIN, STEEL), answers=[False])
    p, _ = presenter(w, FakeView(ids("b1")))
    p.on_shown()
    p.on_material_command(MaterialMenu.ASSIGN, [MaterialPick(STEEL)])

    assert p.on_cancel() == 1


def test_select_buttons_write_the_selection():
    w = world([body("b1"), body("b2")], library(PLAIN, STEEL), assignments=[assigned("b1", "Steel")])
    p, view = presenter(w)
    p.on_shown()

    p.on_update(Block.SELECT_UNASSIGNED)
    assert view.selected == ids("b2")
    p.on_update(Block.SELECT_ALL)
    assert view.selected == ids("b1", "b2")


def test_a_filter_change_reads_the_dropdowns_back_through_the_choices():
    w = sheet_metal_world(body("sm", BodyKind.SHEET_METAL))
    p, view = presenter(w)
    p.on_shown()
    choices = view.trees["filters"][0]
    view.filter_indices = (0, choices.physical_material.labels.index("2024-O"), 0, 0)

    p.on_update(Block.FILTER)

    assert w.session.filter.physical_material_name == "2024-O"
    assert "sm_group=True" in view.calls


def test_hover_retitles_the_label_without_repointing_the_pick():
    w = world([body("b1")], library(PLAIN, STEEL))
    p, view = presenter(w)
    p.on_shown()
    p.on_material_selected(MaterialPick(STEEL))

    p.on_material_hovered(None)

    assert view.labels["material"][0] == "Steel"
    assert w.session.selected_pick == MaterialPick(STEEL)


def test_properties_open_the_property_window_or_say_it_is_unavailable():
    w = world([body("b1")], library(PLAIN, STEEL))
    window = FakePropertyWindow()
    p, _ = presenter(w, window=window)
    p.on_shown()

    p.on_material_default_action(MaterialPick(STEEL))
    assert window.shown == [STEEL]

    q, _ = presenter(w)
    q.on_material_command(MaterialMenu.PROPERTIES, [MaterialPick(STEEL)])
    assert w.dialogs.errors == [w.session.text.property_window_unavailable]


def test_remove_material_from_the_assignment_tree_stages_the_rows_bodies():
    w = world([body("b1")], library(PLAIN, STEEL), assignments=[assigned("b1", "Steel")])
    p, view = presenter(w)
    p.on_shown()
    [group] = view.trees["assignments"]

    p.on_assignment_command(AssignmentMenu.REMOVE_MATERIAL, [group.value])

    assert view.trees["pending"][0].text == "Remove material"


def test_removing_a_root_pending_row_drops_its_entry():
    w = world([body("b1")], library(PLAIN, STEEL))
    p, view = presenter(w, FakeView(ids("b1")))
    p.on_shown()
    p.on_material_command(MaterialMenu.ASSIGN, [MaterialPick(STEEL)])
    [entry] = view.trees["pending"]

    p.on_pending_command(PendingMenu.REMOVE, [entry.value])

    assert view.trees["pending"] == []


def test_a_pending_row_label_shows_the_entry_name():
    w = sheet_metal_world(body("sm", BodyKind.SHEET_METAL))
    p, view = presenter(w, FakeView(ids("sm")))
    p.on_shown()
    p.on_material_command(MaterialMenu.ASSIGN, [MaterialPick(AL2024, R2024)])
    entry = w.session.pending[0]

    p.on_pending_selected(PendingRowRef(entry, None))

    assert view.labels["pending"][0] == f"2024-O [{R2024.name}]"
