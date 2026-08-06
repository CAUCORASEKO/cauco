"""Explicit bundle-ID provider mappings."""

from threading import RLock

from .models import ProviderMapping


class ProviderMappingRegistry:
    def __init__(self, mappings: tuple[ProviderMapping, ...] | None = None) -> None:
        self._mappings: dict[str, ProviderMapping] = {}
        self._bundle_owners: dict[str, str] = {}
        self._lock = RLock()
        for mapping in mappings or default_mappings():
            self.register(mapping)

    def register(self, mapping: ProviderMapping) -> None:
        with self._lock:
            if mapping.provider_id in self._mappings:
                raise ValueError("Provider mapping is already registered.")
            for bundle_id in mapping.bundle_identifiers:
                if bundle_id in self._bundle_owners:
                    raise ValueError("Bundle identifier has multiple owners.")
            self._mappings[mapping.provider_id] = mapping
            for bundle_id in mapping.bundle_identifiers:
                self._bundle_owners[bundle_id] = mapping.provider_id

    def list(self, limit: int = 100) -> tuple[ProviderMapping, ...]:
        if not 1 <= limit <= 100:
            raise ValueError("Limit must be between 1 and 100.")
        with self._lock:
            return tuple(self._mappings[key] for key in sorted(self._mappings))[:limit]

    def find(self, bundle_identifier: str | None) -> ProviderMapping | None:
        if not bundle_identifier:
            return None
        with self._lock:
            provider_id = self._bundle_owners.get(bundle_identifier)
            return self._mappings.get(provider_id) if provider_id else None


def default_mappings() -> tuple[ProviderMapping, ...]:
    return (
        ProviderMapping("apple_calendar", ("com.apple.iCal",)),
        ProviderMapping("apple_contacts", ("com.apple.AddressBook",)),
        ProviderMapping("apple_mail", ("com.apple.mail",)),
        ProviderMapping("chrome", ("com.google.Chrome",)),
        ProviderMapping("finder", ("com.apple.finder",)),
        ProviderMapping("safari", ("com.apple.Safari",)),
        ProviderMapping("vscode", ("com.microsoft.VSCode",)),
    )
