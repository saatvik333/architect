"""Tests for the context assembler."""

from __future__ import annotations

from codebase_comprehension.context_assembler import ContextAssembler
from codebase_comprehension.index_store import IndexStore


class TestContextAssembler:
    """Tests for ContextAssembler."""

    def test_assemble_for_known_function(
        self,
        populated_store: IndexStore,
    ) -> None:
        assembler = ContextAssembler(index_store=populated_store)
        ctx = assembler.assemble("greet")

        assert len(ctx.relevant_files) > 0
        assert any("greet" in f for f in ctx.relevant_files)

    def test_related_tests_found(
        self,
        populated_store: IndexStore,
    ) -> None:
        assembler = ContextAssembler(index_store=populated_store)
        ctx = assembler.assemble("greet")

        assert any("test_greet" in t for t in ctx.related_tests)

    def test_empty_query_returns_empty(
        self,
        populated_store: IndexStore,
    ) -> None:
        assembler = ContextAssembler(index_store=populated_store)
        # Single character keyword (length < 2) should be filtered out
        ctx = assembler.assemble("x")

        assert ctx.relevant_files == []
        assert ctx.related_tests == []

    def test_keyword_matching_works(
        self,
        populated_store: IndexStore,
    ) -> None:
        assembler = ContextAssembler(index_store=populated_store)
        ctx = assembler.assemble("Calculator add")

        assert len(ctx.relevant_files) > 0
        assert any("calc" in f for f in ctx.relevant_files)

    def test_respects_index_store_state(self) -> None:
        empty_store = IndexStore()
        assembler = ContextAssembler(index_store=empty_store)
        ctx = assembler.assemble("anything")

        assert ctx.relevant_files == []
        assert ctx.related_symbols == []
        assert ctx.related_tests == []
