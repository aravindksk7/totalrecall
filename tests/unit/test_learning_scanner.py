"""Unit tests for the learning scanner, parser, classifier, and redactor."""

from pathlib import Path  # noqa: I001
import textwrap

from totalrecall.learning.classifier import classify
from totalrecall.learning.models import LearningDiscoveryType
from totalrecall.learning.parser import ExtractedPattern, extract_patterns
from totalrecall.learning.redactor import redact
from totalrecall.learning.scanner import scan_path


# --- scanner ---


def test_scan_path_finds_python_files(tmp_path: Path) -> None:
    (tmp_path / "page.py").write_text("class LoginPage: pass")
    (tmp_path / "README.md").write_text("# docs")

    files = scan_path(tmp_path)

    assert len(files) == 1
    assert files[0].language == "python"
    assert files[0].path.name == "page.py"


def test_scan_path_finds_typescript_files(tmp_path: Path) -> None:
    (tmp_path / "login.page.ts").write_text("export class LoginPage {}")

    files = scan_path(tmp_path)

    assert len(files) == 1
    assert files[0].language == "typescript"


def test_scan_path_produces_content_hash(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1")

    files = scan_path(tmp_path)

    assert len(files[0].content_hash) == 32  # MD5 hex


def test_scan_path_respects_max_files(tmp_path: Path) -> None:
    for i in range(10):
        (tmp_path / f"f{i}.py").write_text(f"x = {i}")

    files = scan_path(tmp_path, max_files=3)

    assert len(files) == 3


def test_scan_path_returns_empty_for_unknown_extensions(tmp_path: Path) -> None:
    (tmp_path / "data.json").write_text("{}")
    (tmp_path / "styles.css").write_text("body {}")

    assert scan_path(tmp_path) == []


def test_scan_path_is_recursive(tmp_path: Path) -> None:
    subdir = tmp_path / "pages"
    subdir.mkdir()
    (subdir / "home.py").write_text("class HomePage: pass")

    files = scan_path(tmp_path)

    assert any(f.path.name == "home.py" for f in files)


# --- parser: Python ---


def test_parser_finds_page_object_class(tmp_path: Path) -> None:
    src = textwrap.dedent("""\
        class LoginPage:
            def __init__(self, page):
                self.page = page
    """)
    path = tmp_path / "login.py"
    path.write_text(src)

    patterns = extract_patterns(src, path, "python")

    assert any(p.pattern_type == "page_object_class" and p.name == "LoginPage" for p in patterns)


def test_parser_finds_fixture_function(tmp_path: Path) -> None:
    src = textwrap.dedent("""\
        import pytest

        @pytest.fixture
        def browser_page(playwright):
            yield playwright.chromium.launch()
    """)
    path = tmp_path / "conftest.py"

    patterns = extract_patterns(src, path, "python")

    assert any(p.pattern_type == "fixture_function" and p.name == "browser_page" for p in patterns)


def test_parser_finds_test_function(tmp_path: Path) -> None:
    src = "def test_login_redirects(page):\n    assert page.url == '/dashboard'\n"
    path = tmp_path / "test_auth.py"

    patterns = extract_patterns(src, path, "python")

    assert any(
        p.pattern_type == "test_function" and p.name == "test_login_redirects" for p in patterns
    )


def test_parser_skips_invalid_python_syntax(tmp_path: Path) -> None:
    src = "def broken(:\n    pass\n"
    path = tmp_path / "broken.py"

    patterns = extract_patterns(src, path, "python")

    assert patterns == []


def test_parser_utility_class_not_page_object(tmp_path: Path) -> None:
    src = "class DataLoader:\n    pass\n"
    path = tmp_path / "util.py"

    patterns = extract_patterns(src, path, "python")

    assert any(p.pattern_type == "utility_class" and p.name == "DataLoader" for p in patterns)


# --- parser: TypeScript ---


def test_parser_finds_ts_page_class(tmp_path: Path) -> None:
    src = "export class CheckoutPage {\n  constructor(private page: Page) {}\n}\n"
    path = tmp_path / "checkout.page.ts"

    patterns = extract_patterns(src, path, "typescript")

    assert any(p.pattern_type == "page_object_class" and p.name == "CheckoutPage" for p in patterns)


def test_parser_finds_ts_test_block(tmp_path: Path) -> None:
    src = "test('user can log in', async ({ page }) => {\n  await page.goto('/');\n});\n"
    path = tmp_path / "auth.spec.ts"

    patterns = extract_patterns(src, path, "typescript")

    assert any(p.pattern_type == "test_function" and "user can log in" in p.name for p in patterns)


def test_parser_ts_utility_class(tmp_path: Path) -> None:
    src = "export class ApiClient {\n  async get(url: string) {}\n}\n"
    path = tmp_path / "api.ts"

    patterns = extract_patterns(src, path, "typescript")

    assert any(p.pattern_type == "utility_class" and p.name == "ApiClient" for p in patterns)


# --- classifier ---


def _pattern(ptype: str) -> ExtractedPattern:
    return ExtractedPattern(
        pattern_type=ptype,
        name="Example",
        source_excerpt="class Example {}",
        file_path="/test/example.ts",
        start_line=1,
        language="typescript",
    )


def test_classifier_page_object_is_static_skill_candidate() -> None:
    assert classify(_pattern("page_object_class")) == LearningDiscoveryType.STATIC_SKILL_CANDIDATE


def test_classifier_fixture_is_dynamic_memory() -> None:
    assert classify(_pattern("fixture_function")) == LearningDiscoveryType.DYNAMIC_MEMORY


def test_classifier_test_function_is_catalogue_reference() -> None:
    assert classify(_pattern("test_function")) == LearningDiscoveryType.CATALOGUE_REFERENCE


def test_classifier_utility_class_is_catalogue_reference() -> None:
    assert classify(_pattern("utility_class")) == LearningDiscoveryType.CATALOGUE_REFERENCE


# --- redactor ---


def test_redactor_removes_api_key_assignments() -> None:
    text = 'API_KEY = "sk-supersecret12345678901234567890"'
    result, warnings = redact(text)

    assert "[REDACTED]" in result
    assert len(warnings) > 0


def test_redactor_removes_openai_style_key() -> None:
    text = "const key = sk-abcdefghijklmnopqrstuvwxyz1234567890"
    result, warnings = redact(text)

    assert "[REDACTED]" in result


def test_redactor_leaves_clean_text_unchanged() -> None:
    text = "class LoginPage:\n    def goto(self, page):\n        page.goto('/login')\n"
    result, warnings = redact(text)

    assert result == text
    assert warnings == []


def test_redactor_returns_warnings_for_each_pattern_that_fires() -> None:
    text = "token = 'sk-abc1234567890abcdef1234567890abcdef12'"
    _, warnings = redact(text)

    assert len(warnings) >= 1
