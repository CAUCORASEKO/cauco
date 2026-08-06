"""Typed connector runtime errors."""


class ConnectorError(RuntimeError):
    """Base connector error."""


class DuplicateConnectorError(ConnectorError):
    """A connector ID is already registered."""


class ConnectorNotFoundError(ConnectorError):
    """A connector ID is not registered."""
