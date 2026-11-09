"""The material property popup, opened from the material tree (double-click, or right-click > Properties).

MaterialDisplay_UIBlock.dlx is a user-defined UI block with its own OK/Cancel, launched as a dialog of its own, fresh
for each material and disposed on close. The C# tool shipped a WinForms window as well; NX's Python has no WinForms,
so the Block UI popup is the one ported.

It is a second, unparented dialog launched from a tree callback of the main dialog's running `Launch()`: NX has no way
to declare an owner between the two. If the main dialog's `Launch()` is ever seen returning during or after this
popup's Cancel, register the block into the main dialog instead of launching it.
"""

# NX 2412's Python stubs declare instance methods without `self`, type enum members as int and give collections
# no __iter__; these rules would only report those stub defects here. Everything else is still checked.
# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportReturnType=false
# pyright: reportCallIssue=false, reportGeneralTypeIssues=false
# The Styler-generated base class is untyped: pyright infers its dialog attribute as None.
# pyright: reportOptionalMemberAccess=false

from __future__ import annotations

import logging

import NXOpen
import NXOpen.BlockStyler

from banxopen.foundation.nx import nx_error_detail
from banxopen.foundation.ui import NxMessenger, TreeBinding
from banxopen.materials import Material, MaterialPropertyValue
from banxopen.ui_material_assignment.material_display_generated import MaterialDisplay_UIBlock
from banxopen.ui_material_assignment.rows import property_columns, property_rows
from banxopen.ui_material_assignment.text import UiText

_log = logging.getLogger(__name__)

IMAGE_LABEL = "lbl_Image"
PROPERTY_TREE = "MaterialPropTree"


class _Popup(MaterialDisplay_UIBlock):
    def __init__(self, material: Material, text: UiText) -> None:
        self._material = material
        self._text = text
        self._shown = False
        super().__init__()

    def dialogShown_cb(self) -> None:  # noqa: N802  (Styler name)
        """The block's contents exist only once the dialog is built, so columns and rows wait for this. It can fire
        more than once, and inserting a column twice throws."""
        try:
            if self._shown:
                return
            self._shown = True
            self._fill()
        except Exception as ex:  # noqa: BLE001  (boundary: an NX callback)
            _log.exception("The material property window could not be filled")
            NxMessenger(self._text.title).show_error(self._text.property_window_failed(str(ex)))

    def _fill(self) -> None:
        top = self.theUserDefinedUIBlock.TopBlock
        material = self._material
        image = top.FindBlock(IMAGE_LABEL)
        if image is not None:
            image.Label = material.name
            try:
                image.Bitmap = material.image_path or ""
            except NXOpen.NXException as ex:
                _log.warning(
                    "Material property bitmap '%s' could not be set: %s", material.image_path, nx_error_detail(ex)
                )
        tree = top.FindBlock(PROPERTY_TREE)
        if tree is None:
            _log.warning("Material property block '%s' is missing.", PROPERTY_TREE)
            return
        for column_id, title, width in property_columns(self._text):
            tree.InsertColumn(column_id, title, width)
            tree.SetColumnResizePolicy(column_id, NXOpen.BlockStyler.Tree.ColumnResizePolicy.ConstantWidth)
        TreeBinding[MaterialPropertyValue](tree).show(property_rows(material, self._text))


class MaterialPropertyWindow:
    def __init__(self, text: UiText | None = None) -> None:
        self._text = text or UiText.DEFAULT

    def show(self, material: Material) -> None:
        popup: _Popup | None = None
        try:
            popup = _Popup(material, self._text)
            popup.Launch()
        except Exception as ex:  # noqa: BLE001  (an NX failure must not escape into the calling tree callback)
            _log.warning("Material property window could not be opened: %s", ex)
            NxMessenger(self._text.title).show_error(
                self._text.property_window_failed(self._text.property_window_dlx_missing)
            )
        finally:
            if popup is not None:
                popup.Dispose()
