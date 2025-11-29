"""Tests for structured error types."""

from io import StringIO

import pytest

from nyl.core.errors import NylError


def test_nyl_error_basic():
    """Test basic NylError creation."""
    error = NylError("Something went wrong")

    assert str(error) == "Something went wrong"
    assert error.message == "Something went wrong"
    assert error.hint is None
    assert error.cause is None
    assert error.details == {}


def test_nyl_error_with_hint():
    """Test NylError with hint."""
    error = NylError("Operation failed", hint="Try using --force flag")

    assert "Try using --force flag" in str(error)
    assert error.hint == "Try using --force flag"


def test_nyl_error_with_cause():
    """Test NylError with underlying cause."""
    cause = ValueError("Invalid input")
    error = NylError("Validation failed", cause=cause)

    assert error.cause is cause
    assert "ValueError" in str(error)


def test_nyl_error_with_details():
    """Test NylError with additional details."""
    error = NylError(
        "File not found", details={"file": "/path/to/file.yaml", "checked_paths": 3}
    )

    assert error.details["file"] == "/path/to/file.yaml"
    assert error.details["checked_paths"] == 3
    error_str = str(error)
    assert "/path/to/file.yaml" in error_str


def test_nyl_error_with_all_fields():
    """Test NylError with all fields populated."""
    cause = FileNotFoundError("No such file")
    error = NylError(
        message="Failed to load configuration",
        hint="Check that the file exists and is readable",
        cause=cause,
        details={"file": "config.yaml", "attempts": 3},
    )

    assert error.message == "Failed to load configuration"
    assert error.hint == "Check that the file exists and is readable"
    assert error.cause is cause
    assert error.details["file"] == "config.yaml"

    error_str = str(error)
    assert "Failed to load configuration" in error_str
    assert "Check that the file exists and is readable" in error_str
    assert "config.yaml" in error_str
    assert "FileNotFoundError" in error_str


def test_nyl_error_render_basic():
    """Test rendering NylError with rich (basic)."""
    pytest.importorskip("rich")  # Skip if rich not installed
    from rich.console import Console

    error = NylError("Test error message")
    console = Console(file=StringIO(), force_terminal=True, width=80)

    error.render(console)

    output = console.file.getvalue()
    assert "Test error message" in output
    assert "Error:" in output


def test_nyl_error_render_with_hint():
    """Test rendering NylError with hint."""
    pytest.importorskip("rich")
    from rich.console import Console

    error = NylError("Operation failed", hint="Try running with --verbose")
    console = Console(file=StringIO(), force_terminal=True, width=80)

    error.render(console)

    output = console.file.getvalue()
    assert "Operation failed" in output
    assert "Hint:" in output
    assert "Try running with --verbose" in output


def test_nyl_error_render_with_details():
    """Test rendering NylError with details."""
    pytest.importorskip("rich")
    from rich.console import Console

    error = NylError(
        "Process failed", details={"pid": 12345, "exit_code": 1, "signal": "SIGTERM"}
    )
    console = Console(file=StringIO(), force_terminal=True, width=80)

    error.render(console)

    output = console.file.getvalue()
    assert "Process failed" in output
    assert "Details:" in output
    assert "12345" in output
    assert "SIGTERM" in output


def test_nyl_error_render_with_cause():
    """Test rendering NylError with cause."""
    pytest.importorskip("rich")
    from rich.console import Console

    cause = RuntimeError("Underlying issue")
    error = NylError("High-level error", cause=cause)
    console = Console(file=StringIO(), force_terminal=True, width=80)

    error.render(console)

    output = console.file.getvalue()
    assert "High-level error" in output
    assert "Caused by:" in output
    assert "RuntimeError" in output
    assert "Underlying issue" in output


def test_nyl_error_inheritance():
    """Test that NylError can be subclassed."""

    class CustomError(NylError):
        def __init__(self, resource_name: str):
            super().__init__(
                f"Resource '{resource_name}' not found",
                hint=f"Check that {resource_name} exists in your cluster",
                details={"resource": resource_name},
            )

    error = CustomError("my-deployment")

    assert isinstance(error, NylError)
    assert isinstance(error, Exception)
    assert "my-deployment" in error.message
    assert "my-deployment" in error.hint
    assert error.details["resource"] == "my-deployment"
