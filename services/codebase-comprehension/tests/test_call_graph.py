"""Tests for the call graph builder."""

from __future__ import annotations

from codebase_comprehension.call_graph import CallGraphBuilder
from codebase_comprehension.models import CodebaseIndex


class TestCallGraphBuilder:
    """Tests for CallGraphBuilder."""

    def test_simple_call_chain(self, call_chain_index: CodebaseIndex) -> None:
        builder = CallGraphBuilder()
        graph = builder.build(call_chain_index)

        # caller() calls helper() and print()
        assert "main.py::caller" in graph
        callees = graph["main.py::caller"]
        assert "helper" in callees
        assert "print" in callees

    def test_no_calls(self, call_chain_index: CodebaseIndex) -> None:
        builder = CallGraphBuilder()
        builder.build(call_chain_index)

        # helper() has no calls
        callees = builder.get_callees("main.py::helper")
        assert callees == []

    def test_cross_file_reference(self, call_chain_index: CodebaseIndex) -> None:
        builder = CallGraphBuilder()
        builder.build(call_chain_index)

        # func_a calls func_b
        callees = builder.get_callees("a.py::func_a")
        assert "func_b" in callees

    def test_callers_query(self, call_chain_index: CodebaseIndex) -> None:
        builder = CallGraphBuilder()
        builder.build(call_chain_index)

        # helper is called by caller
        callers = builder.get_callers("helper")
        assert "main.py::caller" in callers

    def test_method_calls(self, call_chain_index: CodebaseIndex) -> None:
        builder = CallGraphBuilder()
        builder.build(call_chain_index)

        # Service.handle calls self.validate() and self.process()
        callees = builder.get_callees("service.py::Service.handle")
        assert "self.validate" in callees
        assert "self.process" in callees
