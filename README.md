# BANxOpen.Ui.MaterialAssignment (Python)

The NX Block UI dialog that assigns physical materials to bodies. It is the Python port of the C#
`BANxOpen.Ui.MaterialAssignment` (NX 2412, CPython 3.11). Every rule, check and message comes from the libraries:
[Materials](https://github.com/DOcopyANDpaste/py.BANxOpen.Materials) (`MaterialAssignmentService`) and
[SheetMetal](https://github.com/DOcopyANDpaste/py.BANxOpen.SheetMetal) (`SheetMetalAssignmentSupport`, `SheetMetalServices`).

## Layout

| File | Role | NX |
|---|---|---|
| `session.py` | The pending list: what is staged, replaced, applied and reported (the decision tree below) | no |
| `rows.py` | What the trees, filter dropdowns and context menus show, as `TreeRow` and `MenuItem` values | no |
| `presenter.py` | Reads the view, calls one session gesture, redraws what it changed | no |
| `text.py` | The dialog's own wording (`UiText`) | no |
| `view.py` | Every block ID and block read and write; tree handlers; deferred redraws of off-screen tab pages | yes |
| `property_window.py` | The material property popup (`MaterialDisplay_UIBlock.dlx`) | yes |
| `dialog.py` | Subclass of the generated dialog: each callback is one delegation | yes |
| `entry.py`, `application/MaterialAssignment.py` | Wiring, and the three-line file NX runs | yes |
| `*_generated.py` | The Styler's output. Never edited | yes |

The four NX-free modules are tested without NX (`tests/`), and import-linter keeps NXOpen out of them.

## Assignment logic

The basic rules:

- **Nothing touches the part until Apply / OK.** "Add to pending" and "Remove material" only list the change in the
  **Pending** tab. Until Apply, the **Current Assignment** tab keeps showing what each body really has, and flags the
  pending change in its *Pending* column.
- **One pending change per body.** If you act on the same body again, the latest action replaces the earlier one.
  This applies to assignments and removals alike.
- **Apply is final.** Cancel never reverts what was applied; it only discards what is still pending.

### A. "Add to pending" (material tree, right-click)

```
Add to pending (picked material [+ sheet metal row])
├─ No body selected? ─────────────────────────────► Error "Select at least one body". Pending unchanged.
├─ Selection not in the part any more? ──────────► Error "Refresh and try again". Pending unchanged.
├─ Body ALREADY HAS this material (same physical material; for a sheet metal body with a row picked,
│  the part's Sheet Metal Preferences are also that row)?
│   ├─ Not planned, not staged, no confirmation asked
│   ├─ Reported: "[Body] already has <material>"
│   └─ If the body had a pending change (another assignment, or a removal), it is dropped
│      (assigning what it already has means "leave it as it is")
├─ Every selected body already has it? ─────────► Info "Nothing to add to pending". Nothing staged.
├─ Plan the remaining bodies against the part's REAL current materials
├─ Plain material picked, but a non-blocked sheet metal body is selected?
│                                                 ► Error "pick a sheet metal row". Pending unchanged.
├─ Sheet metal conflict (another sheet metal body, real or pending, has a different material/row;
│  a body pending removal counts as having no material)?
│                                                 ► Error (conflict details). Pending unchanged.
├─ For each body in the plan:
│   ├─ Blocked by a rule ────────────────────────► reported "blocked: <reason>"; NOT staged;
│   │                                               its earlier pending change, if any, is KEPT
│   ├─ Needs confirmation (reassignment, coating, thickness) → one prompt for the entry
│   │   ├─ Yes ──────────────────────────────────► staged; the confirmation is remembered
│   │   └─ No ───────────────────────────────────► reported "skipped: not confirmed"; NOT staged;
│   │                                               its earlier pending change, if any, is KEPT
│   └─ Ok (with or without a warning) ───────────► staged
├─ Nothing staged? ──────────────────────────────► Error "<material> was not added to pending" + reasons.
└─ Something staged:
    ├─ Only the staged bodies are taken out of earlier pending entries (entries left empty are dropped)
    │   A pending removal replaced this way is reported: "[Body] its pending removal was replaced"
    ├─ The new entry (staged bodies only) is added to Pending
    ├─ One info box for anything left out (already has it / blocked / declined), replaced, or warned about
    ├─ Pending tab, Status column:  "Pending"  |  "Pending: <warning>"  |  "Pending — confirmed: <reason>"
    └─ Current Assignment tab: materials unchanged; Pending column flags the change
         body row  → "→ <new material [row]>"   (+ " (confirmed)" when a confirmation was given)
         group row → "<n> pending"
```

### B. "Remove material" (Current Assignment tab, right-click)

```
Remove material (the clicked rows' bodies)
├─ Body has no material ─────────────────────────► skipped: "[Body] has no material"
├─ Body pending an assignment to Y ─────────────► the assignment is REPLACED by the removal
│                                                   (reported: "[Body] its pending assignment to Y was replaced")
└─ Added to the single "Remove material" entry in Pending (no confirmation; Apply is the confirmation)
     Pending tab:  "Remove material" ▸ Body   Status "Pending — currently <material>"
     Current tab:  Pending column "→ (remove material)"; group row "<n> pending"
```

### C. Apply / OK

```
Apply / OK
├─ Pending not empty → apply the pending list:
│   ├─ Re-read the part
│   ├─ The removal first (each body is in only one entry, so the order is only for predictability):
│   │   ├─ Bodies no longer in the part ──────────► reported and dropped
│   │   ├─ Cleared ────────────────────────────────► leave Pending
│   │   ├─ Partial failure ───────────────────────► bodies that still have a material stay pending
│   │   └─ Failed ─────────────────────────────────► all stay pending ("Not applied — <NX message>")
│   ├─ Then each assignment, in order:
│   │   ├─ Bodies no longer in the part ──────────► reported and dropped
│   │   ├─ Re-plan against the part as it is now
│   │   ├─ Sheet metal conflict now? ─────────────► whole entry stays pending ("Not applied — conflicts …")
│   │   ├─ Bodies that newly need confirmation → prompt (earlier answers are reused)
│   │   ├─ Bodies blocked or declined now ────────► stay pending ("Not applied — blocked: … / not confirmed")
│   │   ├─ Apply the rest to the part
│   │   │   ├─ Ok ─────────────────────────────────► they leave Pending
│   │   │   ├─ Partial failure ───────────────────► bodies that now carry the material leave Pending;
│   │   │   │                                       the rest stay ("Not applied — <NX message>")
│   │   │   └─ Failed ─────────────────────────────► all stay pending ("Not applied — <NX message>")
│   │   └─ Re-read the part (the next entry is planned against what this one did)
│   ├─ One message: error if anything is still pending, info if everything applied but there were notes
│   └─ Both trees refresh: Current shows the new materials, Pending shows only what is left
│       ├─ Apply: the dialog stays open
│       └─ OK: anything still pending? → the dialog stays open, so you can see what did not apply
│                                     else → closes
├─ Pending empty, sheet metal row picked, bodies selected → Add to pending + apply, as above
├─ Pending empty, sheet metal row picked, no solid body in the part → sets only the Sheet Metal Preferences
└─ Pending empty, nothing picked → Apply: error "Nothing is pending"; OK: closes
```

### D. Other actions

```
Remove from pending / Clear all pending ► removed from the list only; the part is not touched
Cancel / close ► anything still pending is discarded, after "N pending change(s) … will be discarded. Close
                 anyway?" when there is any. Applied changes are final and are never reverted.
Refresh        ► re-reads the part and drops pending bodies that no longer exist (Apply re-plans the rest)
```

### E. On open (sheet metal part)

Runs once, on the first show, when the part's Sheet Metal Preferences name a material (Parameter Entry is Material
Table) and a sheet metal library is loaded.

```
On open
├─ Every sheet metal body in sync with the preferences ─► nothing
├─ ONE sheet metal body, and its material differs from the preferences row's (or it has none)
│   ├─ Plan it against the preferences row, with every rule, as "Add to pending" would
│   ├─ Row's material not in the library, or a rule blocks it
│   │                                     ► the body is put in the selection + hint "pick <row> and Apply"
│   └─ Otherwise ► staged in Pending: "<material> [<row>]" for the body
│                   ├─ replacing the body's material counts as confirmed (that is what syncing means)
│                   └─ any other confirmation (row thickness ≠ body thickness) is asked at Apply
├─ Several sheet metal bodies ─► info message only (the multi-body check decides)
└─ Info box: what is out of sync, and what was done about it
   Removing the staged entry from Pending is final for this session of the dialog: it is not staged again.
```

## Trees

Every tree (Material, Current Assignment, Pending) opens with its top-level rows expanded (level 1), and it is
expanded again after each rebuild.

## Changing messages

Text lives with whatever produces it. The dialog shows a library's message as-is and never rewords it.

| To change... | Edit |
|---|---|
| A rule outcome, a per-body apply reason ("blocked: ...", "not confirmed", "no longer in the work part", NX's refusal), the confirmation question | `MaterialsText` (BANxOpen.Materials) |
| The sheet metal conflict, the Sheet Metal Preferences messages, the open-time sync hint, "set only the preferences?", the SheetMetal Grade column, `material [row]` names | `SheetMetalText` (BANxOpen.SheetMetal) |
| Message box titles, "could not start", the unexpected-error message | `NxDialogText` (BANxOpen.Foundation) |
| Menus, columns, Pending statuses, staging and apply summaries, this dialog's errors and prompts | [`text.py`](src/banxopen/ui_material_assignment/text.py) (`UiText`) |

Keep the `{...}` values. A describer's members can be overridden in a subclass passed to `MaterialEngine.create`,
`SheetMetalServices.create` or `AssignmentSession`.

## Running in NX

1. Put the five repos' `src` folders on `UGII_PYTHONPATH` and this repo's `application` folder on the dialog search
   path (`UGII_USER_DIR\application`, or `custom_dirs.dat`), as the library's runtime-and-deployment notes describe.
2. Alt+F8, `application\MaterialAssignment.py`. With `BANXOPEN_DEV=1` the packages are reloaded on every run.

The two `*_generated.py` files were transcribed from the C# Styler output, not generated. Regenerate each from its
`.dlx` with the Styler's Python language, rename it, and overwrite it; nothing else should need to change.

### Smoke checklist

1. The dialog opens from Alt+F8. The three tabs show their columns, and SheetMetal Grade in the Sheet Metal application.
2. Select bodies, right-click a material > Add to pending. The Pending tab and the Current tab's Pending column show it;
   the part is unchanged.
3. Apply. The materials change, and **one** Ctrl+Z takes the whole Apply back.
4. A reassignment asks. Yes and No both behave as in the decision tree.
5. A sheet metal library: the filters narrow the rows, a plain material on a sheet metal body is refused, and a second
   sheet metal material is a conflict.
6. A part with one out-of-sync sheet metal body shows the open message and stages the sync.
7. Properties opens the popup, and closing it returns to the dialog.
8. Cancel with something pending asks first. After closing, the syslog (Help > Log File) has no errors.

## Development

```powershell
uv venv --python 3.11
uv pip install -e ".[dev]"                 # installs the three libraries editable
New-Item -ItemType Junction -Path .\typings -Target "$env:UGII_BASE_DIR\UGOPEN\pythonStubs"

.venv\Scripts\ruff check . ; .venv\Scripts\pyright ; .venv\Scripts\lint-imports ; .venv\Scripts\python -m pytest --cov
```
