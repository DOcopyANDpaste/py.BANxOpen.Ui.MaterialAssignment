#==============================================================================
#  WARNING!!  This file is overwritten by the Block UI Styler while generating
#  the automation code. Any modifications to this file will be lost after
#  generating the code again.
#
#       Filename:  material_display_generated.py
#                  (Styler output: MaterialDisplay_UIBlock.py, renamed)
#
#  TRANSCRIBED, NOT YET GENERATED: written by hand from the C# Styler output
#  (MaterialDisplay_UIBlock.cs) in the shape of NX 2412's Python template.
#  Regenerate it from application/MaterialDisplay_UIBlock.dlx with the Styler's
#  Python language and overwrite this file.
#==============================================================================
import NXOpen
import NXOpen.BlockStyler


class MaterialDisplay_UIBlock:
    def __init__(self):
        try:
            self.theSession = NXOpen.Session.GetSession()
            self.theUI = NXOpen.UI.GetUI()
            self.theDlxFileName = "MaterialDisplay_UIBlock.dlx"
            self.theUserDefinedUIBlock = self.theUI.CreateDialog(self.theDlxFileName)
            self.theUserDefinedUIBlock.AddUpdateHandler(self.update_cb)
            self.theUserDefinedUIBlock.AddInitializeHandler(self.initialize_cb)
            self.theUserDefinedUIBlock.AddDialogShownHandler(self.dialogShown_cb)
            self.lbl_Image = None # Block type: Label
            self.MaterialPropTree = None # Block type: Tree Control
        except Exception as ex:
            raise ex

    def Launch(self):
        dialogResponse = None
        try:
            dialogResponse = self.theUserDefinedUIBlock.Launch()
        except Exception as ex:
            self.theUI.NXMessageBox.Show("Block Styler", NXOpen.NXMessageBox.DialogType.Error, str(ex))
        return dialogResponse

    def Dispose(self):
        if self.theUserDefinedUIBlock != None:
            self.theUserDefinedUIBlock.Dispose()
            self.theUserDefinedUIBlock = None

    def initialize_cb(self):
        try:
            self.lbl_Image = self.theUserDefinedUIBlock.TopBlock.FindBlock("lbl_Image")
            self.MaterialPropTree = self.theUserDefinedUIBlock.TopBlock.FindBlock("MaterialPropTree")
        except Exception as ex:
            self.theUI.NXMessageBox.Show("Block Styler", NXOpen.NXMessageBox.DialogType.Error, str(ex))

    def dialogShown_cb(self):
        try:
            pass
        except Exception as ex:
            self.theUI.NXMessageBox.Show("Block Styler", NXOpen.NXMessageBox.DialogType.Error, str(ex))

    def update_cb(self, block):
        try:
            if block == self.lbl_Image:
                pass
            elif block == self.MaterialPropTree:
                pass
        except Exception as ex:
            self.theUI.NXMessageBox.Show("Block Styler", NXOpen.NXMessageBox.DialogType.Error, str(ex))
        return 0
