"""Semantic chunker that splits source files into symbol-level chunks."""

from __future__ import annotations

from codebase_comprehension.models import CodeChunk, FileIndex


class SemanticChunker:
    """Break source files into symbol-level chunks for embedding.

    Each chunk corresponds to a function, method, or class and includes the
    symbol body plus any preceding comments or decorators.
    """

    def __init__(self, max_tokens: int = 512) -> None:
        self._max_tokens = max_tokens

    def chunk_file(self, source: str, file_index: FileIndex) -> list[CodeChunk]:
        """Split *source* into :class:`CodeChunk` instances based on symbols in *file_index*.

        Returns one chunk per function, method, and class.
        """
        lines = source.splitlines(keepends=True)
        chunks: list[CodeChunk] = []

        for func in file_index.functions:
            chunk = self._build_chunk(
                lines=lines,
                file_path=file_index.path,
                symbol_name=func.name,
                symbol_kind="function",
                start_line=func.line_number,
                end_line=self._estimate_end_line(func.line_number, lines),
                decorators=func.decorators,
            )
            if chunk is not None:
                chunks.append(chunk)

        for cls in file_index.classes:
            chunk = self._build_chunk(
                lines=lines,
                file_path=file_index.path,
                symbol_name=cls.name,
                symbol_kind="class",
                start_line=cls.line_number,
                end_line=self._estimate_class_end(cls.line_number, lines),
                decorators=[],
            )
            if chunk is not None:
                chunks.append(chunk)

            for method in cls.methods:
                chunk = self._build_chunk(
                    lines=lines,
                    file_path=file_index.path,
                    symbol_name=f"{cls.name}.{method.name}",
                    symbol_kind="method",
                    start_line=method.line_number,
                    end_line=self._estimate_end_line(method.line_number, lines),
                    decorators=method.decorators,
                )
                if chunk is not None:
                    chunks.append(chunk)

        return chunks

    def _build_chunk(
        self,
        *,
        lines: list[str],
        file_path: str,
        symbol_name: str,
        symbol_kind: str,
        start_line: int,
        end_line: int,
        decorators: list[str],
    ) -> CodeChunk | None:
        """Build a single code chunk from source lines."""
        if start_line < 1 or start_line > len(lines):
            return None

        # Grab preceding context (comments/blank lines/decorators above the symbol)
        context_start = max(0, start_line - 2)  # 0-indexed
        # Walk backwards to find contiguous comments/decorators
        idx = start_line - 2  # 0-indexed, line before the symbol
        while idx >= 0:
            stripped = lines[idx].strip()
            if stripped.startswith("#") or stripped.startswith("@") or stripped == "":
                context_start = idx
                idx -= 1
            else:
                break
        context_lines = lines[context_start : start_line - 1]
        context = "".join(context_lines).rstrip()

        # Clamp end_line
        end_line = min(end_line, len(lines))

        # Extract symbol source
        source_lines = lines[start_line - 1 : end_line]
        source_text = "".join(source_lines).rstrip()

        # Truncate if over max_tokens (rough char-based estimate: 1 token ~ 4 chars)
        max_chars = self._max_tokens * 4
        if len(source_text) > max_chars:
            source_text = source_text[:max_chars] + "\n# ... truncated"

        return CodeChunk(
            file_path=file_path,
            symbol_name=symbol_name,
            symbol_kind=symbol_kind,
            line_number=start_line,
            end_line=end_line,
            source=source_text,
            context=context,
        )

    @staticmethod
    def _estimate_end_line(start_line: int, lines: list[str]) -> int:
        """Estimate where a function ends based on indentation."""
        if start_line < 1 or start_line > len(lines):
            return start_line

        # Get the indentation of the def/function line
        def_line = lines[start_line - 1]
        base_indent = len(def_line) - len(def_line.lstrip())

        end = start_line  # 1-indexed, at least the def line itself
        for i in range(start_line, len(lines)):  # 0-indexed = start_line (next line)
            line = lines[i]
            stripped = line.strip()
            if stripped == "":
                continue
            current_indent = len(line) - len(line.lstrip())
            if current_indent <= base_indent:
                break
            end = i + 1  # convert to 1-indexed

        return end

    @staticmethod
    def _estimate_class_end(start_line: int, lines: list[str]) -> int:
        """Estimate where a class ends based on indentation."""
        if start_line < 1 or start_line > len(lines):
            return start_line

        def_line = lines[start_line - 1]
        base_indent = len(def_line) - len(def_line.lstrip())

        end = start_line
        for i in range(start_line, len(lines)):
            line = lines[i]
            stripped = line.strip()
            if stripped == "":
                continue
            current_indent = len(line) - len(line.lstrip())
            if current_indent <= base_indent:
                break
            end = i + 1

        return end
