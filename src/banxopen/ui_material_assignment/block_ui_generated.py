#==============================================================================
#  WARNING!!  This file is overwritten by the Block UI Styler while generating
#  the automation code. Any modifications to this file will be lost after
#  generating the code again.
#
#       Filename:  block_ui_generated.py   (Styler output: BlockUI.py, renamed)
#
#  TRANSCRIBED, NOT YET GENERATED: written by hand from the C# Styler output
#  (BlockUI.cs, Designcenter 2606) in the shape of NX 2412's Python template
#  (UGOPEN/SampleNXOpenApplications/Python/BlockStyler). Regenerate it from
#  application/BlockUI.dlx with the Styler's Python language and overwrite this
#  file; dialog.py needs no change if the block IDs and callbacks are the same.
#==============================================================================
import NXOpen
import NXOpen.BlockStyler


class BlockUI:
    def __init__(self):
        try:
            self.theSession = NXOpen.Session.GetSession()
            self.theUI = NXOpen.UI.GetUI()
            self.theDlxFileName = "BlockUI.dlx"
            self.theDialog = self.theUI.CreateDialog(self.theDlxFileName)
            self.theDialog.AddApplyHandler(self.apply_cb)
            self.theDialog.AddOkHandler(self.ok_cb)
            self.theDialog.AddUpdateHandler(self.update_cb)
            self.theDialog.AddInitializeHandler(self.initialize_cb)
            self.theDialog.AddEnableOKButtonHandler(self.enableOKButton_cb)
            self.theDialog.AddDialogShownHandler(self.dialogShown_cb)
            self.Sel_SoildBodies = None # Block type: Selection
            self.gp_quickselect = None # Block type: Group
            self.selectAllButton = None # Block type: Button
            self.selectUnassignedButton = None # Block type: Button
            self.group1 = None # Block type: Group
            self.tabControl = None # Block type: Tabs Page
            self.tabPage_NewMat = None # Block type: Group
            self.enum_MatLibrary = None # Block type: Enumeration
            self.group_SMPref = None # Block type: Group
            self.enum_SmStandard = None # Block type: Enumeration
            self.enum_SmPhyMatName = None # Block type: Enumeration
            self.enum_smTHK = None # Block type: Enumeration
            self.enum_SmBendRad = None # Block type: Enumeration
            self.btn_SmClearSelection = None # Block type: Button
            self.gp_Material = None # Block type: Group
            self.MaterialTree = None # Block type: Tree Control
            self.lbl_MaterialDisplay = None # Block type: Label
            self.tabPage_Current = None # Block type: Group
            self.gp_ExistingMaterial = None # Block type: Group
            self.CurrentAssignmentTree = None # Block type: Tree Control
            self.lbl_MaterialDisplay1 = None # Block type: Label
            self.tabPagePending = None # Block type: Group
            self.lbl_MaterialDisplay2 = None # Block type: Label
            self.PendingAssignments = None # Block type: Tree Control
        except Exception as ex:
            raise ex

    def Launch(self):
        dialogResponse = None
        try:
            dialogResponse = self.theDialog.Launch()
        except Exception as ex:
            self.theUI.NXMessageBox.Show("Block Styler", NXOpen.NXMessageBox.DialogType.Error, str(ex))
        return dialogResponse

    def Dispose(self):
        if self.theDialog != None:
            self.theDialog.Dispose()
            self.theDialog = None

    def initialize_cb(self):
        try:
            self.Sel_SoildBodies = self.theDialog.TopBlock.FindBlock("Sel_SoildBodies")
            self.gp_quickselect = self.theDialog.TopBlock.FindBlock("gp_quickselect")
            self.selectAllButton = self.theDialog.TopBlock.FindBlock("selectAllButton")
            self.selectUnassignedButton = self.theDialog.TopBlock.FindBlock("selectUnassignedButton")
            self.group1 = self.theDialog.TopBlock.FindBlock("group1")
            self.tabControl = self.theDialog.TopBlock.FindBlock("tabControl")
            self.tabPage_NewMat = self.theDialog.TopBlock.FindBlock("tabPage_NewMat")
            self.enum_MatLibrary = self.theDialog.TopBlock.FindBlock("enum_MatLibrary")
            self.group_SMPref = self.theDialog.TopBlock.FindBlock("group_SMPref")
            self.enum_SmStandard = self.theDialog.TopBlock.FindBlock("enum_SmStandard")
            self.enum_SmPhyMatName = self.theDialog.TopBlock.FindBlock("enum_SmPhyMatName")
            self.enum_smTHK = self.theDialog.TopBlock.FindBlock("enum_smTHK")
            self.enum_SmBendRad = self.theDialog.TopBlock.FindBlock("enum_SmBendRad")
            self.btn_SmClearSelection = self.theDialog.TopBlock.FindBlock("btn_SmClearSelection")
            self.gp_Material = self.theDialog.TopBlock.FindBlock("gp_Material")
            self.MaterialTree = self.theDialog.TopBlock.FindBlock("MaterialTree")
            self.lbl_MaterialDisplay = self.theDialog.TopBlock.FindBlock("lbl_MaterialDisplay")
            self.tabPage_Current = self.theDialog.TopBlock.FindBlock("tabPage_Current")
            self.gp_ExistingMaterial = self.theDialog.TopBlock.FindBlock("gp_ExistingMaterial")
            self.CurrentAssignmentTree = self.theDialog.TopBlock.FindBlock("CurrentAssignmentTree")
            self.lbl_MaterialDisplay1 = self.theDialog.TopBlock.FindBlock("lbl_MaterialDisplay1")
            self.tabPagePending = self.theDialog.TopBlock.FindBlock("tabPagePending")
            self.lbl_MaterialDisplay2 = self.theDialog.TopBlock.FindBlock("lbl_MaterialDisplay2")
            self.PendingAssignments = self.theDialog.TopBlock.FindBlock("PendingAssignments")
        except Exception as ex:
            self.theUI.NXMessageBox.Show("Block Styler", NXOpen.NXMessageBox.DialogType.Error, str(ex))

    def dialogShown_cb(self):
        try:
            pass
        except Exception as ex:
            self.theUI.NXMessageBox.Show("Block Styler", NXOpen.NXMessageBox.DialogType.Error, str(ex))

    def apply_cb(self):
        errorCode = 0
        try:
            pass
        except Exception as ex:
            errorCode = 1
            self.theUI.NXMessageBox.Show("Block Styler", NXOpen.NXMessageBox.DialogType.Error, str(ex))
        return errorCode

    def update_cb(self, block):
        try:
            if block == self.Sel_SoildBodies:
                pass
            elif block == self.selectAllButton:
                pass
            elif block == self.selectUnassignedButton:
                pass
            elif block == self.tabControl:
                pass
            elif block == self.enum_MatLibrary:
                pass
            elif block == self.enum_SmStandard:
                pass
            elif block == self.enum_SmPhyMatName:
                pass
            elif block == self.enum_smTHK:
                pass
            elif block == self.enum_SmBendRad:
                pass
            elif block == self.btn_SmClearSelection:
                pass
            elif block == self.lbl_MaterialDisplay:
                pass
            elif block == self.lbl_MaterialDisplay1:
                pass
            elif block == self.lbl_MaterialDisplay2:
                pass
        except Exception as ex:
            self.theUI.NXMessageBox.Show("Block Styler", NXOpen.NXMessageBox.DialogType.Error, str(ex))
        return 0

    def ok_cb(self):
        errorCode = 0
        try:
            errorCode = self.apply_cb()
        except Exception as ex:
            errorCode = 1
            self.theUI.NXMessageBox.Show("Block Styler", NXOpen.NXMessageBox.DialogType.Error, str(ex))
        return errorCode

    def enableOKButton_cb(self):
        try:
            pass
        except Exception as ex:
            self.theUI.NXMessageBox.Show("Block Styler", NXOpen.NXMessageBox.DialogType.Error, str(ex))
        return True

    def GetBlockProperties(self, blockID):
        try:
            return self.theDialog.GetBlockProperties(blockID)
        except Exception as ex:
            self.theUI.NXMessageBox.Show("Block Styler", NXOpen.NXMessageBox.DialogType.Error, str(ex))
        return None


def main():
    theBlockUI = None
    try:
        theBlockUI = BlockUI()
        theBlockUI.Launch()
    except Exception as ex:
        NXOpen.UI.GetUI().NXMessageBox.Show("Block Styler", NXOpen.NXMessageBox.DialogType.Error, str(ex))
    finally:
        if theBlockUI != None:
            theBlockUI.Dispose()


if __name__ == "__main__":
    main()
