"""The text that exists because of this dialog's design: menus, column titles, tree statuses, the staging and apply
messages, and the dialog's own errors and prompts. Keep the `{...}` values: they are what the text is filled with.

Not here, by design:
- what a rule, check or service says (rule outcomes, the per-body reasons of an apply, the sheet metal conflict, the
  Sheet Metal Preferences messages and the SheetMetal Grade column) is worded by `MaterialsText` and `SheetMetalText`
  and shown as-is, so every tool says it the same way;
- message box titles, "could not start", the unexpected-error message: `NxDialogText`;
- log lines, which are not user text.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

_PARA = "\n\n"


class UiText:
    """Override a member in a subclass and pass it to `AssignmentSession` to change a wording."""

    DEFAULT: ClassVar[UiText]

    # ---- Message box titles ----

    title = "Material Assignment"
    sheet_metal_preferences_title = "Sheet Metal Preferences"

    # ---- Context menus ----

    menu_add_to_pending = "Add to pending"
    menu_apply_sheet_metal_preference = "Apply sheet metal preference"
    menu_properties = "Properties..."
    menu_refresh = "Refresh"
    menu_select_bodies = "Select these bodies"
    menu_add_to_body_selection = "Add all to body selection"
    menu_remove_material = "Remove material"
    menu_remove_from_pending = "Remove from pending"
    menu_clear_all_pending = "Clear all pending"

    # ---- Tree columns ----

    column_material = "Material"
    column_description = "Description"
    column_density = "Density"
    column_material_or_body = "Material / Body"
    column_bodies_or_kind = "Bodies / Kind"
    column_display_material = "Display material"
    column_pending = "Pending"
    column_sheet_metal_grade = "SheetMetal Grade"
    column_kind = "Kind"
    column_status = "Status"
    column_property = "Property"
    column_value = "Value"
    column_unit = "Unit"

    # ---- Labels and placeholders ----

    no_material_selected = "(no material selected)"
    any_filter = "(Any)"
    """The "no filter" member of every Sheet Metal Preferences filter dropdown."""
    unassigned = "(No material assigned)"
    """The current-assignment tree's group for bodies with no physical material."""
    remove_material_entry = "Remove material"
    """The pending tree's entry for bodies whose material is to be removed."""
    category_separator = " > "

    def sheet_metal_material_made_of(self, material: str) -> str:
        return f"Sheet metal material made of {material}"

    def property_values(self, count: int) -> str:
        return f"{count} values"

    # ---- Pending tree Status column, and the Current tab's Pending column ----

    status_pending = "Pending"
    status_pending_confirmed = "Pending — confirmed"
    flag_remove = "→ (remove material)"
    flag_confirmed_suffix = " (confirmed)"
    flag_not_applied_suffix = " (not applied)"

    def status_with_note(self, status: str, note: str) -> str:
        return f"{status}: {note}"

    def status_pending_removal(self, current_material: str | None) -> str:
        return self.status_pending if current_material is None else f"Pending — currently {current_material}"

    def status_not_applied(self, reason: str | None) -> str:
        return f"Not applied — {reason if reason is not None else 'unknown reason'}"

    def flag_assign(self, entry_name: str) -> str:
        return f"→ {entry_name}"

    def group_pending_count(self, count: int) -> str:
        return f"{count} pending"

    # ---- Why a body was left out of pending (the per-body apply reasons are MaterialsText's) ----

    skipped_not_confirmed = "skipped: not confirmed"
    conflicts_with_sheet_metal = "conflicts with another sheet metal body's material"
    earlier_pending_change_removed_suffix = "; its earlier pending change was removed"
    pending_removal_replaced = "its pending removal was replaced"

    def already_has(self, material: str) -> str:
        return f"already has {material}"

    def pending_assignment_replaced(self, entry_name: str) -> str:
        return f"its pending assignment to {entry_name} was replaced"

    # ---- Errors ----

    def nothing_pending(self, sheet_metal_library: bool) -> str:
        text = (
            f'Nothing is pending. Select bodies, then right-click a material and choose "{self.menu_add_to_pending}".'
        )
        if sheet_metal_library:
            text += (
                f"{_PARA}For a sheet metal library you can also pick a sheet metal material (a row under a physical "
                "material) and Apply it."
            )
        return text

    select_bodies_first = "Select at least one body before assigning a material."
    selection_not_in_part = "The selected bodies are no longer in the work part. Refresh and try again."
    every_solid_has_material = "Every solid body in this part already has a material."
    no_solid_body_in_rows = "None of the selected rows have a solid body."
    select_bodies_to_remove = "Select at least one body to remove its material."
    property_window_unavailable = "The material property window is not available."
    property_window_dlx_missing = "Check that MaterialDisplay_UIBlock.dlx is on the dialog search path."

    def sheet_metal_needs_row(self, material: str) -> str:
        return (
            f"Sheet metal bodies need a sheet metal material, not just '{material}'.{_PARA}"
            f"Expand '{material}' in the material tree and pick one of its rows (Standard, thickness, bend radius) — "
            "that is what the part's Sheet Metal Preferences are set to. Use the Sheet Metal Preferences filters to "
            "narrow the rows."
        )

    def no_solid_selected_for_row(self, row: str) -> str:
        return (
            f"No solid body is selected. This part has bodies, so '{row}' has to be assigned to them: the Sheet Metal "
            f"Preferences are set together with the bodies' material, which keeps the two in sync.{_PARA}"
            "Select the bodies, then Apply again."
        )

    def not_added_to_pending(self, entry_name: str, details: str) -> str:
        return f"{entry_name} was not added to pending.{_PARA}{details}"

    def still_pending(self, report: str) -> str:
        return f"Some pending changes were not applied and are still pending:{_PARA}{report}"

    def property_window_failed(self, detail: str) -> str:
        return f"The material property window could not be opened.\n{detail}"

    # ---- Information ----

    not_added_header = "Not added to pending:"
    replaced_header = "Replaced:"
    warnings_header = "Warnings:"

    def added_to_pending(self, entry_name: str, body_count: int, details: str) -> str:
        return f"{entry_name} added to pending for {body_count} body(ies).{_PARA}{details}"

    def nothing_added_to_pending(self, details: str) -> str:
        return f"Nothing to add to pending.{_PARA}{details}"

    def removal_added_to_pending(self, body_count: int, details: str) -> str:
        return f"Material removal added to pending for {body_count} body(ies).{_PARA}{details}"

    def nothing_to_remove(self, details: str) -> str:
        return f"No material to remove.{_PARA}{details}"

    def applied_with_notes(self, report: str) -> str:
        return f"The pending changes were applied, with these notes:{_PARA}{report}"

    def section(self, header: str, lines: Iterable[str]) -> str:
        return header + "\n" + "\n".join(lines)

    def entry_report(self, entry_name: str, lines: Iterable[str]) -> str:
        return f"{entry_name}:\n" + "\n".join(lines)

    def join_sections(self, sections: Iterable[str]) -> str:
        return _PARA.join(sections)

    # ---- Yes/No questions ----

    def discard_pending(self, count: int) -> str:
        return f"{count} pending change(s) were never applied and will be discarded.{_PARA}Close anyway?"


UiText.DEFAULT = UiText()
