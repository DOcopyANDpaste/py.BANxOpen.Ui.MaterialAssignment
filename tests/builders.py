"""The real material service and rules over an in-memory part, and fakes for everything NX."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from banxopen.foundation import BodyId, BodyInfo, BodyKind, OperationResult
from banxopen.materials import (
    BodyMaterialAssignment,
    CachingMaterialLibraryLoader,
    ExecutablePlan,
    Material,
    MaterialAssignmentService,
    MaterialCategory,
    MaterialId,
    MaterialLibrary,
    MaterialLibraryId,
    MaterialLibraryReference,
    MaterialPropertyValue,
    MaterialRuleSet,
    PartChangeOutcome,
    SheetMetalLibraries,
)
from banxopen.sheetmetal import (
    SheetMetalAssignmentSupport,
    SheetMetalMaterialRow,
    SheetMetalMaterialTable,
    SheetMetalPartPreference,
    SheetMetalStandardSelection,
)
from banxopen.ui_material_assignment.session import AssignmentServices, AssignmentSession

PLAIN = "Metals"
SHEET_METAL = "SheetMetal"
CATEGORY = MaterialCategory("alloys", "Alloys", ("Alloys",))


def material(name: str, library: str = PLAIN, density: str | None = None) -> Material:
    properties = (MaterialPropertyValue("d", "Density", None, density, "kg/m^3"),) if density else ()
    return Material(
        id=MaterialId(f"{library}:{name}"),
        library_id=MaterialLibraryId(library),
        name=name,
        category=CATEGORY,
        properties=properties,
    )


def library(library_id: str, *materials: Material) -> MaterialLibrary:
    return MaterialLibrary(MaterialLibraryId(library_id), library_id, tuple(materials))


def body(name: str, kind: BodyKind = BodyKind.SOLID) -> BodyInfo:
    return BodyInfo(BodyId(name), name, kind, 1.0, {})


def row(
    name: str, physical: str, thickness: float = 0.032, standard: str = "BAPS", grade: str = "G1", bend: str = "0.06"
) -> SheetMetalMaterialRow:
    return SheetMetalMaterialRow(name, standard, standard, physical, grade, thickness, bend)


def assigned(body_id: str, material_name: str | None) -> BodyMaterialAssignment:
    return BodyMaterialAssignment(BodyId(body_id), material_name, None)


@dataclass
class FakePart:
    """An in-memory work part whose materials change when a plan is applied. `fail_on` makes NX refuse those bodies."""

    bodies: list[BodyInfo]
    assignments: dict[BodyId, BodyMaterialAssignment] = field(default_factory=dict)
    names: dict[MaterialId, str] = field(default_factory=dict)
    fail_on: Mapping[BodyId, str] = field(default_factory=dict)
    applied: list[ExecutablePlan] = field(default_factory=list)
    cleared: list[list[BodyId]] = field(default_factory=list)

    def get_bodies(self) -> Sequence[BodyInfo]:
        return list(self.bodies)

    def get_current_assignments(self) -> Mapping[BodyId, BodyMaterialAssignment]:
        return {b.id: self.assignments.get(b.id, BodyMaterialAssignment(b.id, None, None)) for b in self.bodies}

    def set_resolution_libraries(self, libraries: Sequence[MaterialLibrary]) -> None:
        self.names.update({m.id: m.name for lib in libraries for m in lib.materials})

    def apply_plan(self, plan: ExecutablePlan) -> OperationResult[PartChangeOutcome]:
        self.applied.append(plan)
        for a in plan.assignments:
            if a.body_id not in self.fail_on:
                self.assignments[a.body_id] = BodyMaterialAssignment(
                    a.body_id, self.names[a.material_id], a.material_id
                )
        return self._outcome([a.body_id for a in plan.assignments])

    def clear_material(self, body_ids: Sequence[BodyId]) -> OperationResult[PartChangeOutcome]:
        self.cleared.append(list(body_ids))
        for body_id in body_ids:
            if body_id not in self.fail_on:
                self.assignments.pop(body_id, None)
        return self._outcome(body_ids)

    def _outcome(self, body_ids: Sequence[BodyId]) -> OperationResult[PartChangeOutcome]:
        failed = {b: self.fail_on[b] for b in body_ids if b in self.fail_on}
        if not failed:
            return OperationResult.success(PartChangeOutcome())
        return OperationResult(False, PartChangeOutcome(failed), "PARTIAL_FAILURE", "Some bodies failed.")


class FakeRepository:
    def __init__(self, *libraries: MaterialLibrary) -> None:
        self.libraries = {lib.id: lib for lib in libraries}

    def list_available_libraries(self) -> Sequence[MaterialLibraryReference]:
        return [MaterialLibraryReference(lib.id, lib.display_name, f"{lib.id}.xml") for lib in self.libraries.values()]

    def read_library_xml(self, library_id: MaterialLibraryId) -> str:
        """Only the catalog's check for an "allowed for" property reads the text (the fake loader parses nothing), so
        it names the properties the library's materials have."""
        return " ".join(p.name for m in self.libraries[library_id].materials for p in m.properties)


class FakeLoader(CachingMaterialLibraryLoader):
    def __init__(self, repository: FakeRepository) -> None:
        super().__init__(repository)
        self._libraries = repository.libraries

    def get_or_load(self, reference: MaterialLibraryReference) -> MaterialLibrary:
        return self._libraries[reference.id]


@dataclass
class FakeSheetMetal:
    table: SheetMetalMaterialTable
    preference: SheetMetalPartPreference | None = None
    thickness: dict[BodyId, float] = field(default_factory=dict)
    set_result: OperationResult[str] = field(default_factory=lambda: OperationResult.success("Preferences set."))
    set_rows: list[SheetMetalMaterialRow] = field(default_factory=list)
    standard_selection: SheetMetalStandardSelection = field(init=False)

    def __post_init__(self) -> None:
        self.standard_selection = SheetMetalStandardSelection(self.table)

    def read_part_preference(self) -> SheetMetalPartPreference | None:
        return self.preference

    def body_thickness_of(self, body_id: BodyId) -> float | None:
        return self.thickness.get(body_id)

    def set_preferences(self, row: SheetMetalMaterialRow) -> OperationResult[str]:
        self.set_rows.append(row)
        return self.set_result


class FakeDialogs:
    """Answers questions from `answers` in order (yes when it runs out) and records everything shown."""

    def __init__(self, *answers: bool) -> None:
        self.answers = list(answers)
        self.asked: list[str] = []
        self.errors: list[str] = []
        self.infos: list[tuple[str, str]] = []
        self.results: list[tuple[OperationResult[Any], str | None]] = []

    def ask(self, question: str) -> bool:
        self.asked.append(question)
        return self.answers.pop(0) if self.answers else True

    def show_error(self, message: str) -> None:
        self.errors.append(message)

    def show_info(self, title: str, message: str) -> None:
        self.infos.append((title, message))

    def show_result(self, result: OperationResult[Any], success_message: str | None = None) -> None:
        self.results.append((result, success_message))


def preference(selected: SheetMetalMaterialRow | None, count: int = 1) -> SheetMetalPartPreference:
    return SheetMetalPartPreference(
        selected.name if selected else None, True, selected.thickness if selected else 0.032, count, selected
    )


@dataclass
class World:
    part: FakePart
    sheet_metal: FakeSheetMetal
    dialogs: FakeDialogs
    session: AssignmentSession


def world(
    bodies: Sequence[BodyInfo],
    *libraries: MaterialLibrary,
    assignments: Sequence[BodyMaterialAssignment] = (),
    rows: Sequence[SheetMetalMaterialRow] = (),
    part_preference: SheetMetalPartPreference | None = None,
    answers: Sequence[bool] = (),
    sheet_metal_app: bool = False,
    fail_on: Mapping[str, str] | None = None,
    with_display_rules: bool = False,
) -> World:
    """The baseline rules, without the display material module unless asked: its warning (no coating defined) would
    otherwise ride along on every assignment."""
    repository = FakeRepository(*libraries)
    part = FakePart(
        list(bodies),
        {a.body_id: a for a in assignments},
        fail_on={BodyId(k): v for k, v in (fail_on or {}).items()},
    )
    service = MaterialAssignmentService(
        MaterialRuleSet.from_modules(
            m for m in MaterialRuleSet.baseline() if with_display_rules or m.module_id != "DISPLAY"
        ),
        part,
        repository,
        SheetMetalLibraries.NAME_HEURISTIC,
        is_sheet_metal_application=sheet_metal_app,
        loader=FakeLoader(repository),
    )
    table = SheetMetalMaterialTable(rows)
    sheet_metal = FakeSheetMetal(table, part_preference)
    dialogs = FakeDialogs(*answers)
    services = AssignmentServices(service, sheet_metal, SheetMetalAssignmentSupport(table), sheet_metal_app)
    return World(part, sheet_metal, dialogs, AssignmentSession(services, dialogs))


def ids(*names: str) -> list[BodyId]:
    return [BodyId(n) for n in names]
