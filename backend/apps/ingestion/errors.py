class IngestionError(Exception):
    """A failure whose message is safe and useful to show to the user."""


class LimitExceededError(IngestionError):
    """The repository is too large for RepoGuide's limits."""


class RepositoryNotFoundError(IngestionError):
    """The repository does not exist or the user cannot access it."""


class CloneError(IngestionError):
    """git could not fetch the repository."""
