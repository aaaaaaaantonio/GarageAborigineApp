from pathlib import Path
from typing import Protocol

from app.core.config import settings


class FileStorage(Protocol):
    def save(self, content: bytes, relative_path: str) -> str: ...


class LocalFileStorage:
    """MVP-реализация поверх локальной ФС. Замена на S3-совместимое
    хранилище — новый класс с тем же интерфейсом, без изменений в
    DocumentService."""

    def __init__(self, root: str | None = None):
        self.root = Path(root or settings.file_storage_root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, content: bytes, relative_path: str) -> str:
        full_path = self.root / relative_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(content)
        return str(full_path)
