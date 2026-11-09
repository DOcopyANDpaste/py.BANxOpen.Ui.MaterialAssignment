"""Type-only: pyright checks that the real NX classes are what the session's and presenter's protocols say. dialog.py
cannot be relied on for this, since the untyped generated base class turns argument checks off there."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from banxopen.foundation.ui import NxMessenger
    from banxopen.sheetmetal.nx import SheetMetalServices
    from banxopen.ui_material_assignment.presenter import PropertyWindow, View
    from banxopen.ui_material_assignment.property_window import MaterialPropertyWindow
    from banxopen.ui_material_assignment.session import Dialogs, SheetMetalPort
    from banxopen.ui_material_assignment.view import MaterialAssignmentView

    def _sheet_metal(services: SheetMetalServices) -> SheetMetalPort:
        return services

    def _dialogs(messenger: NxMessenger) -> Dialogs:
        return messenger

    def _view(view: MaterialAssignmentView) -> View:
        return view

    def _property_window(window: MaterialPropertyWindow) -> PropertyWindow:
        return window
