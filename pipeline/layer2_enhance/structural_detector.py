"""Legacy structural issue module — Sprint 3 P7: StructuralIssue removed.

The dataclass ``StructuralIssue`` and enum ``StructuralIssueType`` that lived
here were a one-release-cycle shim introduced in Sprint 2 while callers
migrated to ``models.semantic_schemas.StructuralFinding``.

Sprint 3 P7 completed the migration:
- ``pipeline.layer2_enhance.enhancer.detect_structural_issues`` now returns
  ``list[StructuralFinding]`` directly (no adapter).
- ``models.semantic_schemas.StructuralFinding.to_legacy_issue()`` removed.

New structural checks go in ``pipeline.semantic.structural_detector``.
Importing ``StructuralIssue`` or ``StructuralIssueType`` from this module now
raises ``ImportError``.
"""
