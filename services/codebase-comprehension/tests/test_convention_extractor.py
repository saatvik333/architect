"""Tests for the convention extractor."""

from __future__ import annotations

from codebase_comprehension.convention_extractor import ConventionExtractor
from codebase_comprehension.models import CodebaseIndex


class TestConventionExtractor:
    """Tests for ConventionExtractor."""

    def test_detect_snake_case_naming(self, sample_codebase_index: CodebaseIndex) -> None:
        extractor = ConventionExtractor()
        report = extractor.extract(sample_codebase_index)

        assert "functions" in report.naming_patterns
        assert "snake_case" in report.naming_patterns["functions"]

    def test_detect_pascal_case_classes(self, sample_codebase_index: CodebaseIndex) -> None:
        extractor = ConventionExtractor()
        report = extractor.extract(sample_codebase_index)

        assert "classes" in report.naming_patterns
        assert "PascalCase" in report.naming_patterns["classes"]

    def test_detect_file_organization(self, sample_codebase_index: CodebaseIndex) -> None:
        extractor = ConventionExtractor()
        report = extractor.extract(sample_codebase_index)

        # The sample index has src/ and tests/ directories
        org_text = " ".join(report.file_organization)
        assert "src/" in org_text or "tests/" in org_text

    def test_detect_test_patterns(self, sample_codebase_index: CodebaseIndex) -> None:
        extractor = ConventionExtractor()
        report = extractor.extract(sample_codebase_index)

        # Should detect test files
        assert len(report.test_patterns) > 0
        test_text = " ".join(report.test_patterns)
        assert "test" in test_text.lower()
