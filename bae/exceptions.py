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
