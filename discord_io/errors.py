"""Failure facts shared by Discord adapters and domain services."""
class DiscordFailure(RuntimeError):
    def __init__(self, message: str, *, retry: bool = False, partial: bool = False, missing: bool = False,
                 resource_id: int | None = None):
        super().__init__(message)
        self.retry, self.partial, self.missing = retry, partial, missing
        self.resource_id = resource_id
