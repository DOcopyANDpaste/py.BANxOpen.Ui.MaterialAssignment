# Changelog

## [Unreleased]

### Changed
- **Breaking:** targets NX 2606 (Designcenter) and its embedded CPython 3.12. `requires-python` is now `==3.12.*` (was `==3.11.*`), and the code uses 3.12+ syntax (type-parameter generics such as `class OperationResult[T]`), so it no longer runs on NX 2412's Python 3.11.
- Every module starts with `from __future__ import annotations`, enforced by ruff (`required-imports`). Python 3.12 evaluates annotations as soon as the code is run, so a class naming itself in an annotation, or a name imported only under `TYPE_CHECKING`, raised `NameError` on import (for example `from banxopen.foundation.nx import NxSessionContext`). Multi-exception `except` clauses are parenthesised again (`except A, B:` needs Python 3.14).

## [1.0.0] - 2026-10-28

### Added
- Python port of C# BANxOpen.Ui.MaterialAssignment for NX 2412 (CPython 3.11).
- Needs BANxOpen.Foundation 1.1.0 (ui-kit trees and menus) and BANxOpen.SheetMetal 1.1.0
  (`set_preferences` holds its own undo mark).
