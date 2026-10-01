"""Symbol and import extraction with tree-sitter.

We walk syntax trees directly (rather than using query files) so the code is explicit about
which node types count as symbols for each language. Supported: Python, JavaScript (incl.
JSX), TypeScript, TSX, Java and Go. Other languages fall back to line-based chunking.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from functools import cache

from tree_sitter import Node, Parser

from apps.ingestion.languages import PARSEABLE


@dataclass(frozen=True)
class Symbol:
    name: str
    kind: str
    """function | class | method | interface | type | enum | struct | variable"""
    start_line: int
    end_line: int
    parent: str | None = None

    @property
    def qualified_name(self) -> str:
        return f"{self.parent}.{self.name}" if self.parent else self.name

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "kind": self.kind,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "parent": self.parent,
        }


@dataclass(frozen=True)
class ImportRef:
    module: str
    """Module specifier as written (``os.path``, ``./util``, ``github.com/x/y``)."""
    line: int
    level: int = 0
    """Python relative-import level (number of leading dots)."""
    names: tuple[str, ...] = ()


@dataclass
class ParsedFile:
    language: str
    symbols: list[Symbol] = field(default_factory=list)
    imports: list[ImportRef] = field(default_factory=list)
    package: str | None = None
    has_errors: bool = False


@cache
def _parser(language: str) -> Parser:
    from tree_sitter_language_pack import get_parser

    return get_parser(language)  # type: ignore[arg-type]


def _text(node: Node | None) -> str:
    if node is None or node.text is None:
        return ""
    return node.text.decode("utf-8", errors="replace")


def _start(node: Node) -> int:
    return node.start_point.row + 1


def _end(node: Node) -> int:
    row, column = node.end_point
    return row if column == 0 and row > node.start_point.row else row + 1


def _walk(node: Node) -> Iterator[Node]:
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(reversed(current.children))


def _strip_quotes(value: str) -> str:
    return value.strip().strip("'\"`")


# --- Python ------------------------------------------------------------------------------


def _python(root: Node, result: ParsedFile) -> None:
    def visit(node: Node, parent: str | None, outer: Node | None = None) -> None:
        outer = outer or node
        if node.type == "decorated_definition":
            inner = node.child_by_field_name("definition")
            if inner is not None:
                visit(inner, parent, outer=node)
            return
        if node.type == "function_definition":
            kind = "method" if parent else "function"
            name = _text(node.child_by_field_name("name"))
            result.symbols.append(Symbol(name, kind, _start(outer), _end(node), parent))
        elif node.type == "class_definition":
            name = _text(node.child_by_field_name("name"))
            result.symbols.append(Symbol(name, "class", _start(outer), _end(node), parent))
            body = node.child_by_field_name("body")
            if body is not None and parent is None:
                for child in body.named_children:
                    visit(child, name)

    for child in root.named_children:
        visit(child, None)

    for node in _walk(root):
        if node.type == "import_statement":
            for child in node.named_children:
                target = (
                    child.child_by_field_name("name") if child.type == "aliased_import" else child
                )
                if target is not None and target.type == "dotted_name":
                    result.imports.append(ImportRef(_text(target), _start(node)))
        elif node.type == "import_from_statement":
            module_node = node.child_by_field_name("module_name")
            names = tuple(
                _text(n.child_by_field_name("name") if n.type == "aliased_import" else n)
                for n in node.children_by_field_name("name")
            )
            if module_node is None:
                continue
            if module_node.type == "relative_import":
                prefix = next((c for c in module_node.children if c.type == "import_prefix"), None)
                dotted = next((c for c in module_node.children if c.type == "dotted_name"), None)
                level = len(_text(prefix))
                result.imports.append(ImportRef(_text(dotted), _start(node), level, names))
            else:
                result.imports.append(ImportRef(_text(module_node), _start(node), 0, names))


# --- JavaScript / TypeScript -------------------------------------------------------------

_JS_FUNCTION_VALUES = {"arrow_function", "function_expression", "function", "generator_function"}
_JS_DECLS = {
    "function_declaration": "function",
    "generator_function_declaration": "function",
    "class_declaration": "class",
    "abstract_class_declaration": "class",
    "interface_declaration": "interface",
    "type_alias_declaration": "type",
    "enum_declaration": "enum",
}


def _js(root: Node, result: ParsedFile) -> None:
    def class_members(body: Node | None, class_name: str) -> None:
        if body is None:
            return
        for member in body.named_children:
            if member.type in {
                "method_definition",
                "method_signature",
                "abstract_method_signature",
            }:
                name = _text(member.child_by_field_name("name"))
                result.symbols.append(
                    Symbol(name, "method", _start(member), _end(member), class_name)
                )
            elif member.type in {"public_field_definition", "field_definition"}:
                value = member.child_by_field_name("value")
                if value is not None and value.type in _JS_FUNCTION_VALUES:
                    name = _text(
                        member.child_by_field_name("name") or member.child_by_field_name("property")
                    )
                    result.symbols.append(
                        Symbol(name, "method", _start(member), _end(member), class_name)
                    )

    def declaration(node: Node, outer: Node) -> None:
        if node.type in _JS_DECLS:
            name = _text(node.child_by_field_name("name")) or "default"
            kind = _JS_DECLS[node.type]
            result.symbols.append(Symbol(name, kind, _start(outer), _end(node)))
            if kind == "class":
                class_members(node.child_by_field_name("body"), name)
        elif node.type in {"lexical_declaration", "variable_declaration"}:
            for declarator in node.named_children:
                if declarator.type != "variable_declarator":
                    continue
                value = declarator.child_by_field_name("value")
                name = _text(declarator.child_by_field_name("name"))
                if value is None or not name:
                    continue
                if value.type in _JS_FUNCTION_VALUES:
                    result.symbols.append(Symbol(name, "function", _start(outer), _end(node)))
                elif value.type == "class":
                    result.symbols.append(Symbol(name, "class", _start(outer), _end(node)))
                    class_members(value.child_by_field_name("body"), name)

    for child in root.named_children:
        if child.type == "export_statement":
            inner = child.child_by_field_name("declaration")
            if inner is not None:
                declaration(inner, child)
            else:
                value = child.child_by_field_name("value")
                if value is not None and value.type in _JS_FUNCTION_VALUES | {"class"}:
                    kind = "class" if value.type == "class" else "function"
                    result.symbols.append(Symbol("default", kind, _start(child), _end(child)))
        else:
            declaration(child, child)

    for node in _walk(root):
        if node.type in {"import_statement", "export_statement"}:
            source = node.child_by_field_name("source")
            if source is not None:
                result.imports.append(ImportRef(_strip_quotes(_text(source)), _start(node)))
        elif node.type == "call_expression":
            function = node.child_by_field_name("function")
            arguments = node.child_by_field_name("arguments")
            if (
                function is not None
                and _text(function) in {"require", "import"}
                and arguments is not None
                and arguments.named_child_count == 1
                and arguments.named_children[0].type in {"string", "template_string"}
            ):
                spec = _strip_quotes(_text(arguments.named_children[0]))
                if spec and "${" not in spec:
                    result.imports.append(ImportRef(spec, _start(node)))


# --- Java --------------------------------------------------------------------------------

_JAVA_TYPES = {
    "class_declaration": "class",
    "interface_declaration": "interface",
    "enum_declaration": "enum",
    "record_declaration": "class",
    "annotation_type_declaration": "interface",
}


def _java(root: Node, result: ParsedFile) -> None:
    def visit_type(node: Node, parent: str | None) -> None:
        name = _text(node.child_by_field_name("name"))
        result.symbols.append(
            Symbol(name, _JAVA_TYPES[node.type], _start(node), _end(node), parent)
        )
        body = node.child_by_field_name("body")
        if body is None:
            return
        for member in body.named_children:
            if member.type in {"method_declaration", "constructor_declaration"}:
                method = _text(member.child_by_field_name("name"))
                result.symbols.append(Symbol(method, "method", _start(member), _end(member), name))
            elif member.type in _JAVA_TYPES:
                visit_type(member, name)

    for child in root.named_children:
        if child.type == "package_declaration":
            result.package = _text(child).removeprefix("package").strip().rstrip(";").strip()
        elif child.type == "import_declaration":
            spec = _text(child).removeprefix("import").strip().rstrip(";").strip()
            spec = spec.removeprefix("static").strip()
            result.imports.append(ImportRef(spec.replace(" ", ""), _start(child)))
        elif child.type in _JAVA_TYPES:
            visit_type(child, None)


# --- Go ----------------------------------------------------------------------------------


def _go(root: Node, result: ParsedFile) -> None:
    for child in root.named_children:
        if child.type == "package_clause":
            result.package = _text(child).removeprefix("package").strip()
        elif child.type == "import_declaration":
            for node in _walk(child):
                if node.type == "import_spec":
                    path = node.child_by_field_name("path")
                    result.imports.append(ImportRef(_strip_quotes(_text(path)), _start(node)))
        elif child.type == "function_declaration":
            name = _text(child.child_by_field_name("name"))
            result.symbols.append(Symbol(name, "function", _start(child), _end(child)))
        elif child.type == "method_declaration":
            name = _text(child.child_by_field_name("name"))
            receiver = child.child_by_field_name("receiver")
            receiver_type = None
            if receiver is not None:
                for node in _walk(receiver):
                    if node.type == "type_identifier":
                        receiver_type = _text(node)
                        break
            result.symbols.append(Symbol(name, "method", _start(child), _end(child), receiver_type))
        elif child.type == "type_declaration":
            for spec in child.named_children:
                if spec.type not in {"type_spec", "type_alias"}:
                    continue
                type_node = spec.child_by_field_name("type")
                kind = {"struct_type": "struct", "interface_type": "interface"}.get(
                    type_node.type if type_node is not None else "", "type"
                )
                name = _text(spec.child_by_field_name("name"))
                # Single specs span the whole declaration (includes the `type` keyword).
                start = _start(child) if child.named_child_count == 1 else _start(spec)
                end = _end(child) if child.named_child_count == 1 else _end(spec)
                result.symbols.append(Symbol(name, kind, start, end))


_VISITORS = {
    "python": _python,
    "javascript": _js,
    "typescript": _js,
    "tsx": _js,
    "java": _java,
    "go": _go,
}


def parse_source(language: str, source: str) -> ParsedFile | None:
    """Extract symbols/imports, or ``None`` for languages we do not parse."""
    if language not in PARSEABLE:
        return None
    tree = _parser(language).parse(source.encode("utf-8"))
    result = ParsedFile(language=language, has_errors=tree.root_node.has_error)
    _VISITORS[language](tree.root_node, result)
    result.symbols = [s for s in result.symbols if s.name]
    result.symbols.sort(key=lambda s: (s.start_line, -s.end_line))
    return result
