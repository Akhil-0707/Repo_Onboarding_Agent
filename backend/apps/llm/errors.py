class LLMError(Exception):
    """Base class for language-model failures."""


class ModelOfflineError(LLMError):
    """The model server is unreachable or kept failing after all retries.

    Callers treat this as "pause and resume later", never as a permanent failure.
    """


class LLMRequestError(LLMError):
    """The server rejected the request (4xx). Retrying the same request will not help."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
