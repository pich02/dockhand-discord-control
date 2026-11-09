"""Small exception classes used by the domain layer.

Use cases map these into :class:`~dockhand_discord_control.domain.models.ActionResult`
instances instead of letting them leak to callers.
"""


class DomainError(Exception):
    """Base class for all domain errors."""


class ContainerNotFoundError(DomainError):
    """Raised when a container cannot be found."""


class MappingNotFoundError(DomainError):
    """Raised when no channel mapping exists for a channel id."""


class UnauthorizedError(DomainError):
    """Raised when a channel is not authorized for a container."""


class DockhandClientError(DomainError):
    """Raised when the Dockhand client port fails."""
