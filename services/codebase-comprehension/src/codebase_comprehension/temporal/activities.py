"""Temporal activity definitions for codebase indexing."""

from __future__ import annotations

import pathlib

import structlog

from codebase_comprehension.ast_indexer import ASTIndexer
from codebase_comprehension.chunker import SemanticChunker
from codebase_comprehension.index_store import IndexStore
from codebase_comprehension.tree_sitter_indexer import TreeSitterIndexer

logger = structlog.get_logger()

# File extension -> language mapping
_EXTENSION_LANGUAGES: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
}

# Glob patterns per language
_LANGUAGE_GLOBS: dict[str, str] = {
    "python": "**/*.py",
    "javascript": "**/*.js",
    "typescript": "**/*.ts",
}


async def index_codebase(
    directory: str,
    *,
    max_files: int = 10000,
    use_tree_sitter: bool = True,
    generate_embeddings: bool = False,
    database_url: str | None = None,
) -> dict[str, int]:
    """Temporal activity: index a codebase directory.

    Returns a summary dict with total_files, total_symbols, and
    optionally total_embeddings.
    """
    root = pathlib.Path(directory)
    if not root.is_dir():
        raise ValueError(f"Directory does not exist: {directory}")

    indexer: ASTIndexer | TreeSitterIndexer = (
        TreeSitterIndexer() if use_tree_sitter else ASTIndexer()
    )

    store = IndexStore()

    # Use the AST indexer's directory scanning for Python files
    if isinstance(indexer, ASTIndexer):
        index = indexer.index_directory(directory, max_files=max_files)
        store.store(index)
        result = {
            "total_files": index.total_files,
            "total_symbols": index.total_symbols,
        }
    else:
        # Tree-sitter: scan multiple file types
        from codebase_comprehension.models import CodebaseIndex, FileIndex

        files: dict[str, FileIndex] = {}
        total_symbols = 0
        file_count = 0

        for ext, language in _EXTENSION_LANGUAGES.items():
            for file_path in sorted(root.rglob(f"*{ext}")):
                if file_count >= max_files:
                    break
                if not file_path.is_file():
                    continue
                try:
                    source = file_path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    logger.warning("read_error", file_path=str(file_path))
                    continue

                rel_path = str(file_path.relative_to(root))
                file_index = indexer.index_file(source, rel_path, language)
                files[rel_path] = file_index
                total_symbols += (
                    len(file_index.functions) + len(file_index.classes) + len(file_index.imports)
                )
                file_count += 1

        index = CodebaseIndex(
            root_path=directory,
            files=files,
            total_files=len(files),
            total_symbols=total_symbols,
        )
        store.store(index)
        result = {
            "total_files": index.total_files,
            "total_symbols": index.total_symbols,
        }

    # Optionally generate embeddings
    if generate_embeddings and database_url:
        try:
            from codebase_comprehension.embeddings import EmbeddingGenerator
            from codebase_comprehension.vector_store import VectorStore

            chunker = SemanticChunker()
            generator = EmbeddingGenerator()
            vs = VectorStore(database_url)

            all_chunks = []
            for fpath, file_index in index.files.items():
                try:
                    source = (root / fpath).read_text(encoding="utf-8")
                    chunks = chunker.chunk_file(source, file_index)
                    all_chunks.extend(chunks)
                except (OSError, UnicodeDecodeError):
                    continue

            if all_chunks:
                embedded = generator.embed_chunks(all_chunks)
                count = await vs.store_embeddings(directory, embedded)
                result["total_embeddings"] = count

            await vs.close()
        except Exception:
            logger.warning("embedding_generation_failed", exc_info=True)

    return result
