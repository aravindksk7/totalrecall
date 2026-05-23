from typing import Protocol


class CatalogueRepository(Protocol):
    pass


class TombstoneRepository(Protocol):
    pass


class AuditRepository(Protocol):
    pass


class ContextSnapshotRepository(Protocol):
    pass


class ProviderMappingRepository(Protocol):
    pass


class LearningRunRepository(Protocol):
    pass
