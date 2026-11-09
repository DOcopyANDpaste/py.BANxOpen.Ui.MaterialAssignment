"""The Styler dialog, rewired by overriding its callbacks: the generated file is never edited. Each override is one
delegation to the presenter."""

# The Styler-generated base class is untyped Python: pyright infers its attributes as None and its callbacks as
# returning None. These rules would only report that inference here.
# pyright: reportOptionalMemberAccess=false, reportIncompatibleMethodOverride=false, reportArgumentType=false

from __future__ import annotations

from banxopen.foundation.nx import BodyResolver
from banxopen.foundation.ui import NxMessenger, ui_callback
from banxopen.ui_material_assignment.block_ui_generated import BlockUI
from banxopen.ui_material_assignment.presenter import MaterialAssignmentPresenter
from banxopen.ui_material_assignment.property_window import MaterialPropertyWindow
from banxopen.ui_material_assignment.session import AssignmentServices, AssignmentSession
from banxopen.ui_material_assignment.text import UiText
from banxopen.ui_material_assignment.view import MaterialAssignmentView

TITLE = UiText.DEFAULT.title


class MaterialAssignmentDialog(BlockUI):
    """Mode: interactive."""

    def __init__(
        self, services: AssignmentServices, resolver: BodyResolver, messenger: NxMessenger, text: UiText | None = None
    ) -> None:
        self._services = services
        self._resolver = resolver
        self._messenger = messenger
        self._text = text or UiText.DEFAULT
        self._view: MaterialAssignmentView | None = None
        self._presenter: MaterialAssignmentPresenter | None = None
        super().__init__()  # generated: creates the dialog and registers its callbacks
        # The Styler generates no cancel callback. Cancel and the title bar's close both come here.
        self.theDialog.AddCancelHandler(self.cancel_cb)

    @ui_callback(TITLE)
    def initialize_cb(self) -> int:
        super().initialize_cb()  # generated: finds the blocks
        self._view = MaterialAssignmentView(self.theDialog, self._resolver, self._text.no_material_selected)
        session = AssignmentSession(self._services, self._messenger, self._text)
        self._presenter = MaterialAssignmentPresenter(
            session, self._view, self._messenger, MaterialPropertyWindow(self._text)
        )
        self._view.connect(self._presenter)
        return 0

    @ui_callback(TITLE)
    def dialogShown_cb(self) -> int:  # noqa: N802  (Styler name)
        return self._p.on_shown()

    @ui_callback(TITLE)
    def update_cb(self, block: object) -> int:
        update = MaterialAssignmentView.update_of(block)  # type: ignore[arg-type]  # a UIBlock
        return self._p.on_update(update) if update is not None else 0

    @ui_callback(TITLE)
    def apply_cb(self) -> int:
        return self._p.on_apply()

    @ui_callback(TITLE)
    def ok_cb(self) -> int:
        return self._p.on_ok()

    @ui_callback(TITLE)
    def cancel_cb(self) -> int:
        return self._p.on_cancel()

    @property
    def _p(self) -> MaterialAssignmentPresenter:
        assert self._presenter is not None, "initialize_cb runs before any other callback"
        return self._presenter
