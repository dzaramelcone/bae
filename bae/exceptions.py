"""Bae exception hierarchy.

All bae exceptions inherit from BaeError and support cause chaining.
"""


class BaeError(Exception):
    """Base exception for all bae errors.

    Wraps original errors as __cause__ for proper exception chaining.
    """

    def __init__(self, message: str, cause: Exception | None = None):
        super().__init__(message)
        if cause is not None:
            self.__cause__ = cause


class BaeParseError(BaeError):
    """Raised when parsing or validation fails.

    Examples: invalid node field types, malformed annotations,
    schema validation errors.
    """

    pass


class BaeLMError(BaeError):
    """Raised when LLM API fails.

    Examples: timeout, rate limit, network error, invalid response.
    """

    pass


class RecallError(BaeError):
    """Raised when Recall() finds no matching field in the execution trace."""

    pass


class DepError(BaeError):
    """Raised when a Dep function fails during field resolution."""

    def __init__(
        self,
        message: str,
        *,
        node_type: type | None = None,
        field_name: str = "",
        cause: Exception | None = None,
    ):
        super().__init__(message, cause=cause)
        self.node_type = node_type
        self.field_name = field_name
        self.trace: list | None = None


class FillError(BaeError):
    """Raised when LM fill validation fails after retries."""

    def __init__(
        self,
        message: str,
        *,
        node_type: type | None = None,
        validation_errors: str = "",
        attempts: int = 0,
        cause: Exception | None = None,
    ):
        super().__init__(message, cause=cause)
        self.node_type = node_type
        self.validation_errors = validation_errors
        self.attempts = attempts
        self.trace: list | None = None
