"""Typed inventory errors."""


class ApplicationInventoryError(RuntimeError):
    """Base inventory error."""


class ApplicationNotFoundError(ApplicationInventoryError):
    """Inventory ID was not found."""
