"""Base error handling with rich formatting support for Nyl.

This module provides structured error types that replace the scattered
`exit(1)` calls throughout the codebase. Errors include helpful hints
and are formatted beautifully using the rich library.
"""

from typing import Any


class NylError(Exception):
    """Base class for all Nyl errors.

    Provides structured error information with:
    - Clear error message
    - Optional hint for how to fix the issue
    - Optional cause (underlying exception)
    - Optional additional details

    Errors can be rendered with rich formatting for better terminal output.
    """

    def __init__(
        self,
        message: str,
        hint: str | None = None,
        cause: Exception | None = None,
        details: dict[str, Any] | None = None,
    ):
        """Create a new Nyl error.

        Args:
            message: The main error message
            hint: Optional suggestion for how to fix the issue
            cause: Optional underlying exception that caused this error
            details: Optional dictionary of additional context
        """
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.cause = cause
        self.details = details or {}

    def render(self, console: Any) -> None:
        """Render this error with rich formatting.

        Args:
            console: A rich.console.Console instance
        """
        # Import here to avoid requiring rich if not used
        from rich.panel import Panel
        from rich.text import Text

        # Build error message
        error_text = Text()
        error_text.append("Error: ", style="bold red")
        error_text.append(self.message)

        # Add hint if present
        if self.hint:
            error_text.append("\n\n")
            error_text.append("Hint: ", style="bold yellow")
            error_text.append(self.hint, style="yellow")

        # Add details if present
        if self.details:
            error_text.append("\n\n")
            error_text.append("Details:\n", style="bold dim")
            for key, value in self.details.items():
                error_text.append(f"  {key}: ", style="dim")
                error_text.append(f"{value}\n")

        # Add cause if present
        if self.cause:
            error_text.append("\n")
            error_text.append("Caused by: ", style="bold dim")
            error_text.append(f"{type(self.cause).__name__}: {self.cause}", style="dim")

        # Render in a panel
        console.print(
            Panel(
                error_text,
                title=f"[bold red]{type(self).__name__}[/]",
                border_style="red",
                expand=False,
            )
        )

    def __str__(self) -> str:
        """Return a plain text representation of the error."""
        parts = [self.message]
        if self.hint:
            parts.append(f"\nHint: {self.hint}")
        if self.details:
            parts.append("\nDetails:")
            for key, value in self.details.items():
                parts.append(f"  {key}: {value}")
        if self.cause:
            parts.append(f"\nCaused by: {type(self.cause).__name__}: {self.cause}")
        return "\n".join(parts)
