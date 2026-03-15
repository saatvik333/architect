"""Multi-language code indexer using tree-sitter."""
# mypy: disable-error-code="attr-defined, no-any-return, union-attr, call-overload, unused-ignore"

from __future__ import annotations

import structlog

from codebase_comprehension.models import (
    ClassDef,
    FileIndex,
    FunctionDef,
    ImportInfo,
)

logger = structlog.get_logger()

# Language loading: tree-sitter v0.23+ uses per-language packages that expose
# a ``language()`` callable returning a capsule. We wrap each in a try/except
# so missing grammars degrade gracefully.

_LANGUAGES: dict[str, object] = {}


def _load_language(name: str) -> object | None:
    """Lazy-load and cache a tree-sitter Language object."""
    if name in _LANGUAGES:
        return _LANGUAGES[name]

    try:
        import tree_sitter

        if name == "python":
            import tree_sitter_python as tsp

            lang = tree_sitter.Language(tsp.language())
        elif name == "javascript":
            import tree_sitter_javascript as tsjs

            lang = tree_sitter.Language(tsjs.language())
        elif name == "typescript":
            import tree_sitter_typescript as tsts

            lang = tree_sitter.Language(tsts.language_typescript())
        else:
            logger.warning("unsupported_language", language=name)
            _LANGUAGES[name] = None  # type: ignore[assignment]
            return None

        _LANGUAGES[name] = lang
        return lang
    except Exception:
        logger.warning("language_load_failed", language=name, exc_info=True)
        _LANGUAGES[name] = None  # type: ignore[assignment]
        return None


class TreeSitterIndexer:
    """Parse source files using tree-sitter and build a structured index of their symbols.

    Supports Python, JavaScript, and TypeScript.  Falls back to an empty
    :class:`FileIndex` when the requested language grammar is unavailable.
    """

    def index_file(self, source: str, file_path: str, language: str = "python") -> FileIndex:
        """Parse *source* with tree-sitter and extract functions, classes, imports.

        Returns an empty :class:`FileIndex` when the language is unsupported or
        parsing fails.
        """
        lang_obj = _load_language(language)
        if lang_obj is None:
            return FileIndex(path=file_path, language=language, line_count=source.count("\n") + 1)

        try:
            import tree_sitter

            parser = tree_sitter.Parser(lang_obj)
            tree = parser.parse(source.encode("utf-8"))
        except Exception:
            logger.warning("parse_failed", file_path=file_path, language=language)
            return FileIndex(path=file_path, language=language, line_count=source.count("\n") + 1)

        root = tree.root_node
        functions = self._extract_functions(root, file_path, language, source)
        classes = self._extract_classes(root, file_path, language, source)
        imports = self._extract_imports(root, file_path, language, source)
        line_count = source.count("\n") + 1

        return FileIndex(
            path=file_path,
            language=language,
            functions=functions,
            classes=classes,
            imports=imports,
            line_count=line_count,
        )

    # -- Extraction helpers --------------------------------------------------

    def _extract_functions(
        self, root: object, file_path: str, language: str, source: str
    ) -> list[FunctionDef]:
        """Extract top-level function definitions from the tree-sitter AST."""
        results: list[FunctionDef] = []

        for child in root.children:  # type: ignore[attr-defined]
            node_type = child.type  # type: ignore[attr-defined]
            if language == "python" and node_type in (
                "function_definition",
                "decorated_definition",
            ):
                func_node = child
                decorators: list[str] = []
                if node_type == "decorated_definition":
                    for dec_child in child.children:  # type: ignore[attr-defined]
                        if dec_child.type == "decorator":  # type: ignore[attr-defined]
                            decorators.append(
                                source[dec_child.start_byte : dec_child.end_byte]  # type: ignore[attr-defined]
                            )
                        elif dec_child.type == "function_definition":  # type: ignore[attr-defined]
                            func_node = dec_child
                results.append(
                    self._parse_python_function(func_node, file_path, source, decorators)
                )
            elif language in ("javascript", "typescript") and node_type in (
                "function_declaration",
                "export_statement",
            ):
                if node_type == "export_statement":
                    for sub in child.children:  # type: ignore[attr-defined]
                        if sub.type == "function_declaration":  # type: ignore[attr-defined]
                            results.append(self._parse_js_function(sub, file_path, source))
                else:
                    results.append(self._parse_js_function(child, file_path, source))
        return results

    def _extract_classes(
        self, root: object, file_path: str, language: str, source: str
    ) -> list[ClassDef]:
        """Extract class definitions from the tree-sitter AST."""
        results: list[ClassDef] = []

        for child in root.children:  # type: ignore[attr-defined]
            node_type = child.type  # type: ignore[attr-defined]
            if language == "python" and node_type in (
                "class_definition",
                "decorated_definition",
            ):
                cls_node = child
                if node_type == "decorated_definition":
                    for dec_child in child.children:  # type: ignore[attr-defined]
                        if dec_child.type == "class_definition":  # type: ignore[attr-defined]
                            cls_node = dec_child
                            break
                    else:
                        continue
                results.append(self._parse_python_class(cls_node, file_path, source))
            elif language in ("javascript", "typescript") and node_type in (
                "class_declaration",
                "export_statement",
            ):
                if node_type == "export_statement":
                    for sub in child.children:  # type: ignore[attr-defined]
                        if sub.type == "class_declaration":  # type: ignore[attr-defined]
                            results.append(self._parse_js_class(sub, file_path, source))
                else:
                    results.append(self._parse_js_class(child, file_path, source))
        return results

    def _extract_imports(
        self, root: object, file_path: str, language: str, source: str
    ) -> list[ImportInfo]:
        """Extract import statements from the tree-sitter AST."""
        results: list[ImportInfo] = []

        for child in root.children:  # type: ignore[attr-defined]
            node_type = child.type  # type: ignore[attr-defined]
            if language == "python":
                if node_type == "import_statement":
                    results.extend(self._parse_python_import(child, file_path, source))
                elif node_type == "import_from_statement":
                    results.extend(self._parse_python_from_import(child, file_path, source))
            elif language in ("javascript", "typescript") and node_type == "import_statement":
                results.extend(self._parse_js_import(child, file_path, source))
        return results

    # -- Python-specific parsers ---------------------------------------------

    def _parse_python_function(
        self,
        node: object,
        file_path: str,
        source: str,
        decorators: list[str] | None = None,
    ) -> FunctionDef:
        """Parse a Python function_definition node."""
        name = ""
        parameters: list[str] = []
        return_type = ""
        is_async = False
        calls: list[str] = []
        docstring = ""

        for child in node.children:  # type: ignore[attr-defined]
            ctype = child.type  # type: ignore[attr-defined]
            if ctype == "identifier" and not name:
                name = source[child.start_byte : child.end_byte]  # type: ignore[attr-defined]
            elif ctype == "parameters":
                parameters = self._extract_python_params(child, source)
            elif ctype == "type":
                return_type = source[child.start_byte : child.end_byte]  # type: ignore[attr-defined]
            elif ctype == "block":
                calls = self._extract_python_calls(child, source)
                docstring = self._extract_python_docstring(child, source)
            elif ctype == "async":
                is_async = True

        # Check if the node text starts with "async"
        node_text = source[node.start_byte : node.end_byte]  # type: ignore[attr-defined]
        if node_text.startswith("async "):
            is_async = True

        return FunctionDef(
            name=name,
            file_path=file_path,
            line_number=node.start_point[0] + 1,  # type: ignore[attr-defined]
            parameters=parameters,
            return_type=return_type,
            is_async=is_async,
            decorators=decorators or [],
            calls=calls,
            docstring=docstring,
        )

    def _parse_python_class(self, node: object, file_path: str, source: str) -> ClassDef:
        """Parse a Python class_definition node."""
        name = ""
        bases: list[str] = []
        methods: list[FunctionDef] = []
        docstring = ""

        for child in node.children:  # type: ignore[attr-defined]
            ctype = child.type  # type: ignore[attr-defined]
            if ctype == "identifier" and not name:
                name = source[child.start_byte : child.end_byte]  # type: ignore[attr-defined]
            elif ctype == "argument_list":
                for arg in child.children:  # type: ignore[attr-defined]
                    if arg.type not in ("(", ")", ","):  # type: ignore[attr-defined]
                        bases.append(source[arg.start_byte : arg.end_byte])  # type: ignore[attr-defined]
            elif ctype == "block":
                docstring = self._extract_python_docstring(child, source)
                for block_child in child.children:  # type: ignore[attr-defined]
                    if block_child.type in (  # type: ignore[attr-defined]
                        "function_definition",
                        "decorated_definition",
                    ):
                        func_node = block_child
                        decorators: list[str] = []
                        if block_child.type == "decorated_definition":  # type: ignore[attr-defined]
                            for dec_child in block_child.children:  # type: ignore[attr-defined]
                                if dec_child.type == "decorator":  # type: ignore[attr-defined]
                                    decorators.append(
                                        source[
                                            dec_child.start_byte : dec_child.end_byte  # type: ignore[attr-defined]
                                        ]
                                    )
                                elif dec_child.type == "function_definition":  # type: ignore[attr-defined]
                                    func_node = dec_child
                        methods.append(
                            self._parse_python_function(func_node, file_path, source, decorators)
                        )

        return ClassDef(
            name=name,
            file_path=file_path,
            line_number=node.start_point[0] + 1,  # type: ignore[attr-defined]
            bases=bases,
            methods=methods,
            docstring=docstring,
        )

    def _parse_python_import(self, node: object, file_path: str, source: str) -> list[ImportInfo]:
        """Parse a Python ``import x`` statement."""
        results: list[ImportInfo] = []
        for child in node.children:  # type: ignore[attr-defined]
            if child.type == "dotted_name":  # type: ignore[attr-defined]
                module = source[child.start_byte : child.end_byte]  # type: ignore[attr-defined]
                results.append(
                    ImportInfo(
                        module=module,
                        names=[module.split(".")[-1]],
                        is_relative=False,
                        file_path=file_path,
                        line_number=node.start_point[0] + 1,  # type: ignore[attr-defined]
                    )
                )
            elif child.type == "aliased_import":  # type: ignore[attr-defined]
                name_node = child.children[0]  # type: ignore[attr-defined]
                module = source[name_node.start_byte : name_node.end_byte]  # type: ignore[attr-defined]
                results.append(
                    ImportInfo(
                        module=module,
                        names=[module.split(".")[-1]],
                        is_relative=False,
                        file_path=file_path,
                        line_number=node.start_point[0] + 1,  # type: ignore[attr-defined]
                    )
                )
        return results

    def _parse_python_from_import(
        self, node: object, file_path: str, source: str
    ) -> list[ImportInfo]:
        """Parse a Python ``from x import y`` statement."""
        module = ""
        is_relative = False

        # First pass: find the module and detect relative imports
        for child in node.children:  # type: ignore[attr-defined]
            ctype = child.type  # type: ignore[attr-defined]
            if ctype == "relative_import":
                is_relative = True
                for sub in child.children:  # type: ignore[attr-defined]
                    if sub.type == "dotted_name":  # type: ignore[attr-defined]
                        module = source[sub.start_byte : sub.end_byte]  # type: ignore[attr-defined]
            elif ctype == "dotted_name":
                # Module name (for non-relative: ``from pathlib import Path``)
                # But only set if we haven't passed the "import" keyword yet
                break_text = source[child.start_byte : child.end_byte]  # type: ignore[attr-defined]
                if not module:
                    module = break_text

        # Second pass: extract imported names (everything after "import" keyword)
        names: list[str] = []
        past_import = False
        for child in node.children:  # type: ignore[attr-defined]
            text = source[child.start_byte : child.end_byte]  # type: ignore[attr-defined]
            ctype = child.type  # type: ignore[attr-defined]
            if ctype == "import":
                past_import = True
                continue
            if past_import and ctype not in ("(", ")", ",", "comment"):
                if ctype == "aliased_import":
                    alias_name = child.children[0]  # type: ignore[attr-defined]
                    names.append(
                        source[alias_name.start_byte : alias_name.end_byte]  # type: ignore[attr-defined]
                    )
                elif ctype == "dotted_name" or ctype == "identifier":
                    names.append(text)

        return [
            ImportInfo(
                module=module,
                names=names,
                is_relative=is_relative,
                file_path=file_path,
                line_number=node.start_point[0] + 1,  # type: ignore[attr-defined]
            )
        ]

    # -- JavaScript/TypeScript-specific parsers ------------------------------

    def _parse_js_function(self, node: object, file_path: str, source: str) -> FunctionDef:
        """Parse a JS/TS function_declaration node."""
        name = ""
        parameters: list[str] = []
        is_async = False

        for child in node.children:  # type: ignore[attr-defined]
            ctype = child.type  # type: ignore[attr-defined]
            if ctype == "identifier":
                name = source[child.start_byte : child.end_byte]  # type: ignore[attr-defined]
            elif ctype == "formal_parameters":
                for param in child.children:  # type: ignore[attr-defined]
                    if param.type in ("identifier", "required_parameter", "optional_parameter"):  # type: ignore[attr-defined]
                        parameters.append(
                            source[param.start_byte : param.end_byte]  # type: ignore[attr-defined]
                        )
            elif ctype == "async":
                is_async = True

        return FunctionDef(
            name=name,
            file_path=file_path,
            line_number=node.start_point[0] + 1,  # type: ignore[attr-defined]
            parameters=parameters,
            is_async=is_async,
        )

    def _parse_js_class(self, node: object, file_path: str, source: str) -> ClassDef:
        """Parse a JS/TS class_declaration node."""
        name = ""
        bases: list[str] = []
        methods: list[FunctionDef] = []

        for child in node.children:  # type: ignore[attr-defined]
            ctype = child.type  # type: ignore[attr-defined]
            if ctype == "type_identifier" or (ctype == "identifier" and not name):
                name = source[child.start_byte : child.end_byte]  # type: ignore[attr-defined]
            elif ctype == "class_heritage":
                for heritage_child in child.children:  # type: ignore[attr-defined]
                    if heritage_child.type == "identifier":  # type: ignore[attr-defined]
                        bases.append(
                            source[heritage_child.start_byte : heritage_child.end_byte]  # type: ignore[attr-defined]
                        )
            elif ctype == "class_body":
                for body_child in child.children:  # type: ignore[attr-defined]
                    if body_child.type == "method_definition":  # type: ignore[attr-defined]
                        methods.append(self._parse_js_method(body_child, file_path, source))

        return ClassDef(
            name=name,
            file_path=file_path,
            line_number=node.start_point[0] + 1,  # type: ignore[attr-defined]
            bases=bases,
            methods=methods,
        )

    def _parse_js_method(self, node: object, file_path: str, source: str) -> FunctionDef:
        """Parse a JS/TS method_definition node."""
        name = ""
        parameters: list[str] = []

        for child in node.children:  # type: ignore[attr-defined]
            ctype = child.type  # type: ignore[attr-defined]
            if ctype == "property_identifier":
                name = source[child.start_byte : child.end_byte]  # type: ignore[attr-defined]
            elif ctype == "formal_parameters":
                for param in child.children:  # type: ignore[attr-defined]
                    if param.type in ("identifier", "required_parameter", "optional_parameter"):  # type: ignore[attr-defined]
                        parameters.append(
                            source[param.start_byte : param.end_byte]  # type: ignore[attr-defined]
                        )

        return FunctionDef(
            name=name,
            file_path=file_path,
            line_number=node.start_point[0] + 1,  # type: ignore[attr-defined]
            parameters=parameters,
        )

    def _parse_js_import(self, node: object, file_path: str, source: str) -> list[ImportInfo]:
        """Parse a JS/TS import statement."""
        module = ""
        names: list[str] = []

        for child in node.children:  # type: ignore[attr-defined]
            ctype = child.type  # type: ignore[attr-defined]
            if ctype == "string":
                # Remove quotes
                text = source[child.start_byte : child.end_byte]  # type: ignore[attr-defined]
                module = text.strip("'\"")
            elif ctype == "import_clause":
                for clause_child in child.children:  # type: ignore[attr-defined]
                    if clause_child.type == "identifier":  # type: ignore[attr-defined]
                        names.append(
                            source[clause_child.start_byte : clause_child.end_byte]  # type: ignore[attr-defined]
                        )
                    elif clause_child.type == "named_imports":  # type: ignore[attr-defined]
                        for imp in clause_child.children:  # type: ignore[attr-defined]
                            if imp.type == "import_specifier":  # type: ignore[attr-defined]
                                for spec_child in imp.children:  # type: ignore[attr-defined]
                                    if spec_child.type == "identifier":  # type: ignore[attr-defined]
                                        names.append(
                                            source[
                                                spec_child.start_byte : spec_child.end_byte  # type: ignore[attr-defined]
                                            ]
                                        )
                                        break

        is_relative = module.startswith(".")
        return [
            ImportInfo(
                module=module,
                names=names,
                is_relative=is_relative,
                file_path=file_path,
                line_number=node.start_point[0] + 1,  # type: ignore[attr-defined]
            )
        ]

    # -- Utility helpers -----------------------------------------------------

    @staticmethod
    def _extract_python_params(node: object, source: str) -> list[str]:
        """Extract parameter names from a parameters node."""
        params: list[str] = []
        for child in node.children:  # type: ignore[attr-defined]
            ctype = child.type  # type: ignore[attr-defined]
            if ctype == "identifier":
                params.append(source[child.start_byte : child.end_byte])  # type: ignore[attr-defined]
            elif ctype in (
                "typed_parameter",
                "typed_default_parameter",
                "default_parameter",
            ):
                # First child is usually the name
                for sub in child.children:  # type: ignore[attr-defined]
                    if sub.type == "identifier":  # type: ignore[attr-defined]
                        params.append(source[sub.start_byte : sub.end_byte])  # type: ignore[attr-defined]
                        break
            elif ctype in ("list_splat_pattern", "dictionary_splat_pattern"):
                for sub in child.children:  # type: ignore[attr-defined]
                    if sub.type == "identifier":  # type: ignore[attr-defined]
                        params.append(source[sub.start_byte : sub.end_byte])  # type: ignore[attr-defined]
                        break
        return params

    @staticmethod
    def _extract_python_calls(node: object, source: str) -> list[str]:
        """Walk a block node to find call expressions."""
        calls: list[str] = []
        stack = list(node.children)  # type: ignore[attr-defined]
        while stack:
            child = stack.pop()
            if child.type == "call":  # type: ignore[attr-defined]
                func_node = child.children[0]  # type: ignore[attr-defined]
                call_text = source[func_node.start_byte : func_node.end_byte]  # type: ignore[attr-defined]
                if call_text:
                    calls.append(call_text)
            stack.extend(child.children)  # type: ignore[attr-defined]
        return calls

    @staticmethod
    def _extract_python_docstring(block_node: object, source: str) -> str:
        """Extract a docstring from the first expression_statement in a block."""
        for child in block_node.children:  # type: ignore[attr-defined]
            if child.type == "expression_statement":  # type: ignore[attr-defined]
                for sub in child.children:  # type: ignore[attr-defined]
                    if sub.type == "string":  # type: ignore[attr-defined]
                        # tree-sitter v0.23+ string nodes may have
                        # string_start / string_content / string_end children
                        for string_child in sub.children:  # type: ignore[attr-defined]
                            if string_child.type == "string_content":  # type: ignore[attr-defined]
                                return source[
                                    string_child.start_byte : string_child.end_byte  # type: ignore[attr-defined]
                                ].strip()
                        # Fallback: extract from raw text
                        raw = source[sub.start_byte : sub.end_byte]  # type: ignore[attr-defined]
                        for prefix in ('"""', "'''", '"', "'"):
                            if raw.startswith(prefix) and raw.endswith(prefix):
                                return raw[len(prefix) : -len(prefix)].strip()
                        return raw.strip("\"'").strip()
                break
        return ""
