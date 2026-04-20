class ResourceNotFoundError(Exception):
    def __init__(self, name: str, key: str = "") -> None:
        super().__init__(f"Resource {name} with key {key} not found" if key else f"Resource {name} not found")
        self.name = name
        self.key = key


class ResourceAlreadyExistsError(Exception):
    def __init__(self, name: str) -> None:
        super().__init__(f"Resource {name} alraady exists")
        self.name = name


class SectorConfigurationError(Exception):
    def __init__(self, sector: str, message: str) -> None:
        super().__init__(f"Sector {sector} configuration error: {message}")
        self.sector = sector
        self.message = message
