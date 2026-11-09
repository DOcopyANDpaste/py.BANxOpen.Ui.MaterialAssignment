"""The tool's entry: build the session context and the libraries once per launch, then show the dialog. Wiring only."""

# NX 2412's Python stubs leave out Session.LibraryUnloadOption.
# pyright: reportAttributeAccessIssue=false

from __future__ import annotations

import NXOpen

from banxopen.foundation.nx import BodyResolver, NxDialogText, NxSessionContext, install_nx_logging
from banxopen.foundation.ui import NxMessenger, launch_dialog
from banxopen.materials.nx import MaterialEngine
from banxopen.sheetmetal.nx import SheetMetalServices
from banxopen.ui_material_assignment.dialog import TITLE, MaterialAssignmentDialog
from banxopen.ui_material_assignment.session import AssignmentServices


def main() -> None:
    install_nx_logging(NXOpen.Session.GetSession())
    messenger = NxMessenger(TITLE)
    started = NxSessionContext.try_initialize()
    if not started.ok or started.value is None:
        messenger.show_error(NxDialogText.DEFAULT.could_not_start(TITLE, started.message))
        return
    context = started.value

    # Sheet metal config that cannot be loaded stops the dialog rather than dropping the bead rules: a dialog that
    # silently stopped enforcing SPEC restrictions would assign forbidden materials to beaded parts.
    sheet_metal = SheetMetalServices.create(context)
    if not sheet_metal.ok or sheet_metal.value is None:
        messenger.show_error(sheet_metal.message or NxDialogText.DEFAULT.could_not_start(TITLE, None))
        return
    sm = sheet_metal.value

    # One resolver for the engine and the selection block: both map the same bodies.
    resolver = BodyResolver(context)
    engine = MaterialEngine.create(context, sm.material_modules, body_resolver=resolver, confirm_load=messenger.ask)
    if not engine.ok or engine.value is None:
        messenger.show_error(engine.message or NxDialogText.DEFAULT.could_not_start(TITLE, None))
        return

    services = AssignmentServices(
        materials=engine.value.service,
        sheet_metal=sm,
        support=sm.assignment_support(),
        is_sheet_metal_application=context.is_sheet_metal_application,
        materials_text=engine.value.text,
        sheet_metal_text=sm.text,
    )
    launch_dialog(lambda: MaterialAssignmentDialog(services, resolver, messenger), TITLE)


def GetUnloadOption(arg: str) -> int:  # noqa: N802  (the name NX looks for)
    return int(NXOpen.Session.LibraryUnloadOption.Immediately)
