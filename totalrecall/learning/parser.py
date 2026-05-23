"""Pattern extractor for Python and TypeScript test/page-object source files."""

import ast
import re
from dataclasses import dataclass
from pathlib import Path

_PAGE_KEYWORDS = frozenset({"page", "component", "widget", "modal", "form", "dialog", "screen"})
_TS_CLASS_RE = re.compile(r"^(?:export\s+)?(?:abstract\s+)?class\s+(\w+)", re.MULTILINE)
_TS_TEST_RE = re.compile(r"^(?:test|it|describe)\s*\(\s*['\"`]([^'\"`]{1,80})", re.MULTILINE)


@dataclass(frozen=True)
class ExtractedPattern:
    pattern_type: str  # page_object_class | fixture_function | test_function | utility_class
    name: str
    source_excerpt: str
    file_path: str
    start_line: int
    language: str


def extract_patterns(content: str, file_path: Path, language: str) -> list[ExtractedPattern]:
    if language == "python":
        return _extract_python(content, file_path)
    if language == "typescript":
        return _extract_typescript(content, file_path)
    return []


def _extract_python(content: str, file_path: Path) -> list[ExtractedPattern]:
    patterns: list[ExtractedPattern] = []
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return patterns

    lines = content.splitlines()

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            excerpt = "\n".join(lines[node.lineno - 1 : node.lineno + 9])
            ptype = "page_object_class" if _is_page_name(node.name) else "utility_class"
            patterns.append(
                ExtractedPattern(
                    pattern_type=ptype,
                    name=node.name,
                    source_excerpt=excerpt,
                    file_path=str(file_path),
                    start_line=node.lineno,
                    language="python",
                )
            )
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            if _has_fixture_decorator(node):
                excerpt = "\n".join(lines[node.lineno - 1 : node.lineno + 4])
                patterns.append(
                    ExtractedPattern(
                        pattern_type="fixture_function",
                        name=node.name,
                        source_excerpt=excerpt,
                        file_path=str(file_path),
                        start_line=node.lineno,
                        language="python",
                    )
                )
            elif node.name.startswith("test_"):
                excerpt = "\n".join(lines[node.lineno - 1 : node.lineno + 4])
                patterns.append(
                    ExtractedPattern(
                        pattern_type="test_function",
                        name=node.name,
                        source_excerpt=excerpt,
                        file_path=str(file_path),
                        start_line=node.lineno,
                        language="python",
                    )
                )

    return patterns


def _is_page_name(name: str) -> bool:
    lower = name.lower()
    return any(kw in lower for kw in _PAGE_KEYWORDS)


def _has_fixture_decorator(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for d in node.decorator_list:
        if isinstance(d, ast.Name) and d.id == "fixture":
            return True
        if isinstance(d, ast.Attribute) and d.attr == "fixture":
            return True
        if isinstance(d, ast.Call):
            inner = d.func
            if isinstance(inner, ast.Name) and inner.id == "fixture":
                return True
            if isinstance(inner, ast.Attribute) and inner.attr == "fixture":
                return True
    return False


def _extract_typescript(content: str, file_path: Path) -> list[ExtractedPattern]:
    patterns: list[ExtractedPattern] = []
    lines = content.splitlines()

    for match in _TS_CLASS_RE.finditer(content):
        line_no = content[: match.start()].count("\n") + 1
        name = match.group(1)
        excerpt = "\n".join(lines[line_no - 1 : line_no + 9])
        ptype = "page_object_class" if _is_page_name(name) else "utility_class"
        patterns.append(
            ExtractedPattern(
                pattern_type=ptype,
                name=name,
                source_excerpt=excerpt,
                file_path=str(file_path),
                start_line=line_no,
                language="typescript",
            )
        )

    for match in _TS_TEST_RE.finditer(content):
        line_no = content[: match.start()].count("\n") + 1
        name = match.group(1)
        excerpt = "\n".join(lines[line_no - 1 : line_no + 4])
        patterns.append(
            ExtractedPattern(
                pattern_type="test_function",
                name=name,
                source_excerpt=excerpt,
                file_path=str(file_path),
                start_line=line_no,
                language="typescript",
            )
        )

    return patterns
