"""Unit tests for LocalStorageBackend."""

import os

import pytest

from app.services.storage.local import LocalStorageBackend


class TestLocalStorageBackend:
    """Tests for local filesystem storage operations."""

    @pytest.fixture
    def storage(self, tmp_path):
        """Create storage backed by a temp directory."""
        return LocalStorageBackend(base_path=str(tmp_path))

    async def test_save_creates_file_and_returns_path(self, storage, tmp_path):
        """save() writes content and returns full path."""
        path = await storage.save("test/doc.pdf", b"pdf-content")
        assert os.path.isfile(path)
        assert path == os.path.normpath(os.path.join(str(tmp_path), "test/doc.pdf"))

    async def test_save_creates_subdirectories(self, storage, tmp_path):
        """save() creates nested directories automatically."""
        await storage.save("a/b/c/file.txt", b"data")
        assert os.path.isdir(os.path.join(str(tmp_path), "a", "b", "c"))

    async def test_read_returns_saved_content(self, storage):
        """read() returns the exact content that was saved."""
        await storage.save("data.bin", b"binary-data-here")
        content = await storage.read("data.bin")
        assert content == b"binary-data-here"

    async def test_read_nonexistent_raises(self, storage):
        """read() raises FileNotFoundError for missing files."""
        with pytest.raises(FileNotFoundError):
            await storage.read("does-not-exist.pdf")

    async def test_delete_removes_file(self, storage, tmp_path):
        """delete() removes an existing file."""
        await storage.save("to-delete.pdf", b"content")
        assert os.path.isfile(os.path.join(str(tmp_path), "to-delete.pdf"))
        await storage.delete("to-delete.pdf")
        assert not os.path.isfile(os.path.join(str(tmp_path), "to-delete.pdf"))

    async def test_delete_nonexistent_no_error(self, storage):
        """delete() does not raise for missing files."""
        await storage.delete("nonexistent-file.pdf")  # Should not raise

    async def test_exists_true_for_saved_file(self, storage):
        """exists() returns True after saving."""
        await storage.save("check.pdf", b"data")
        assert await storage.exists("check.pdf") is True

    async def test_exists_false_for_missing_file(self, storage):
        """exists() returns False for non-existent files."""
        assert await storage.exists("no-such-file.pdf") is False
