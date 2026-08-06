"""Pure deterministic application connector matching."""

from .models import ApplicationConnectorMatch, MatchConfidence, MatchStatus


class ApplicationConnectorResolver:
    def __init__(self, mappings, connectors) -> None:
        self.mappings = mappings
        self.connectors = connectors

    def resolve(self, application) -> ApplicationConnectorMatch:
        mapping = self.mappings.find(application.bundle_identifier)
        base = dict(
            inventory_id=application.inventory_id,
            display_name=application.display_name,
            bundle_identifier=application.bundle_identifier,
            application_availability=application.availability.value,
            limitations=("Matching is observational; permissions and routing are not evaluated.",),
        )
        if not application.bundle_identifier:
            return ApplicationConnectorMatch(
                **base,
                status=MatchStatus.UNAVAILABLE_METADATA,
                confidence=MatchConfidence.NO_MATCH,
                reason_codes=("bundle_identifier_missing",),
            )
        if mapping is None:
            return ApplicationConnectorMatch(
                **base,
                status=MatchStatus.NO_MATCH,
                confidence=MatchConfidence.NO_MATCH,
                reason_codes=("no_provider_mapping",),
            )
        candidates = [
            item for item in self.connectors.list() if item.provider_id == mapping.provider_id
        ]
        compatible = [
            item
            for item in candidates
            if item.application_bundle_id in (None, application.bundle_identifier)
        ]
        if len(compatible) > 1:
            status, confidence, reason = (
                MatchStatus.AMBIGUOUS,
                MatchConfidence.AMBIGUOUS,
                "multiple_registered_connectors",
            )
        elif compatible:
            status, confidence, reason = (
                MatchStatus.MATCHED_REGISTERED_CONNECTOR,
                MatchConfidence.EXACT_BUNDLE_ID,
                "registered_connector_bundle_match",
            )
        else:
            status, confidence, reason = (
                MatchStatus.MATCHED_KNOWN_PROVIDER,
                MatchConfidence.EXPLICIT_PROVIDER_MAPPING,
                "provider_mapping_only",
            )
        return ApplicationConnectorMatch(
            **base,
            matched_provider_ids=(mapping.provider_id,),
            matched_registered_connector_ids=tuple(item.connector_id for item in compatible),
            status=status,
            confidence=confidence,
            reason_codes=(reason,),
            has_registered_connector=bool(compatible),
            connector_available=any(item.availability.value == "available" for item in compatible),
            candidate_connector_count=len(candidates),
        )
