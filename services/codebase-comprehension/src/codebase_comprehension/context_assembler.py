"""Context assembler that builds CodeContext from an IndexStore.

Supports hybrid mode: uses semantic search via VectorStore when available,
falls back to keyword matching otherwise.
"""

from __future__ import annotations

import pathlib

import structlog

from codebase_comprehension.index_store import IndexStore
from codebase_comprehension.models import CodeContext, SymbolInfo

logger = structlog.get_logger()


class ContextAssembler:
    """Assemble relevant code context for a task.

    When *vector_store* and *embedding_generator* are provided, uses semantic
    search for the first pass and supplements with keyword matching.  Otherwise,
    falls back to pure keyword matching.
    """

    def __init__(
        self,
        index_store: IndexStore,
        vector_store: object | None = None,
        embedding_generator: object | None = None,
    ) -> None:
        self._index_store = index_store
        self._vector_store = vector_store
        self._embedding_generator = embedding_generator

    def assemble(self, task_description: str, max_tokens: int = 50_000) -> CodeContext:
        """Build a :class:`CodeContext` by keyword-searching the stored index.

        Uses simple keyword matching against file paths and symbol names
        (no embeddings).
        """
        relevant_files = self._find_relevant_files(task_description)
        related_symbols = self._index_store.search_symbols(task_description, limit=20)
        related_tests = self._find_related_tests(relevant_files)

        # Build import graph for matched files
        import_graph: dict[str, list[str]] = {}
        for index in self._index_store._indices.values():
            for file_path, file_index in index.files.items():
                if file_path in relevant_files:
                    modules = [imp.module for imp in file_index.imports if imp.module]
                    import_graph[file_path] = modules

        # Build file chunks (truncated content placeholder)
        file_chunks: dict[str, str] = {}
        for fp in relevant_files:
            file_chunks[fp] = f"# Content of {fp}"

        return CodeContext(
            relevant_files=relevant_files,
            file_chunks=file_chunks,
            related_symbols=related_symbols,
            related_tests=related_tests,
            import_graph=import_graph,
        )

    async def assemble_semantic(
        self,
        task_description: str,
        root_path: str | None = None,
        max_tokens: int = 50_000,
    ) -> CodeContext:
        """Build :class:`CodeContext` using semantic search when available.

        Falls back to keyword matching if vector store is unavailable or has
        no embeddings for the root path.
        """
        # Import here to avoid circular imports at module level
        from codebase_comprehension.embeddings import EmbeddingGenerator
        from codebase_comprehension.vector_store import VectorStore

        vs: VectorStore | None = self._vector_store  # type: ignore[assignment]
        eg: EmbeddingGenerator | None = self._embedding_generator  # type: ignore[assignment]

        if vs is not None and eg is not None:
            try:
                has_data = root_path is not None and await vs.has_embeddings(root_path)
            except Exception:
                logger.warning("vector_store_check_failed", exc_info=True)
                has_data = False

            if has_data:
                try:
                    query_vec = eg.embed_query(task_description)
                    results = await vs.search(query_vec, root_path=root_path, limit=20)

                    relevant_files = sorted(
                        {r.file_path for r in results}
                    )
                    related_symbols = [
                        SymbolInfo(
                            name=r.symbol_name,
                            kind="function",
                            file_path=r.file_path,
                            line_number=r.line_number,
                        )
                        for r in results
                    ]
                    related_tests = self._find_related_tests(relevant_files)

                    file_chunks: dict[str, str] = {}
                    for r in results:
                        if r.file_path not in file_chunks:
                            file_chunks[r.file_path] = r.source_chunk
                        else:
                            file_chunks[r.file_path] += f"\n\n{r.source_chunk}"

                    import_graph: dict[str, list[str]] = {}
                    for index in self._index_store._indices.values():
                        for fp, fi in index.files.items():
                            if fp in relevant_files:
                                import_graph[fp] = [
                                    imp.module for imp in fi.imports if imp.module
                                ]

                    return CodeContext(
                        relevant_files=relevant_files,
                        file_chunks=file_chunks,
                        related_symbols=related_symbols,
                        related_tests=related_tests,
                        import_graph=import_graph,
                    )
                except Exception:
                    logger.warning("semantic_search_failed", exc_info=True)

        # Fall back to keyword matching
        return self.assemble(task_description, max_tokens=max_tokens)

    def _find_relevant_files(self, task_description: str) -> list[str]:
        """Find files whose paths or symbol names match keywords in *task_description*."""
        keywords = self._extract_keywords(task_description)
        if not keywords:
            return []

        matched: list[str] = []
        for index in self._index_store._indices.values():
            for file_path, file_index in index.files.items():
                if self._matches_keywords(file_path, keywords):
                    matched.append(file_path)
                    continue

                # Check symbol names
                for func in file_index.functions:
                    if self._matches_keywords(func.name, keywords):
                        matched.append(file_path)
                        break
                else:
                    for cls in file_index.classes:
                        if self._matches_keywords(cls.name, keywords):
                            matched.append(file_path)
                            break

        return sorted(set(matched))

    def _find_related_tests(self, file_paths: list[str]) -> list[str]:
        """For each file, look for ``test_<filename>.py`` in tests/ directories."""
        test_files: list[str] = []
        for fp in file_paths:
            stem = pathlib.PurePosixPath(fp).stem
            test_name = f"test_{stem}.py"

            for index in self._index_store._indices.values():
                for indexed_path in index.files:
                    if indexed_path.endswith(test_name):
                        test_files.append(indexed_path)

        return sorted(set(test_files))

    @staticmethod
    def _extract_keywords(text: str) -> list[str]:
        """Split task description into lowercase keywords (length >= 2)."""
        words = text.lower().replace("_", " ").replace("-", " ").split()
        return [w for w in words if len(w) >= 2]

    @staticmethod
    def _matches_keywords(text: str, keywords: list[str]) -> bool:
        """Return True if any keyword appears in *text* (case-insensitive)."""
        text_lower = text.lower()
        return any(kw in text_lower for kw in keywords)

    def _get_related_symbols(self, task_description: str) -> list[SymbolInfo]:
        """Search index store for matching symbols."""
        return self._index_store.search_symbols(task_description, limit=20)
