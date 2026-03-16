"""
Unit tests for storage backends.

Tests LocalStorage and GCSStorage with mocked dependencies.
"""

import io
import os
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from app.core.storage import get_storage, LocalStorage, GCSStorage


def test_gcs_storage_disabled_uses_local():
    """Test get_storage returns LocalStorage when USE_GCS=false."""
    mock_settings = Mock()
    mock_settings.use_gcs = False

    with patch('app.core.storage.get_settings', return_value=mock_settings):
        storage = get_storage()
        assert isinstance(storage, LocalStorage)
        assert not isinstance(storage, GCSStorage)


def test_local_storage_save_returns_localhost_url(tmp_path):
    """Test LocalStorage.save writes file and returns localhost URL."""
    # Create LocalStorage with temp directory
    storage = LocalStorage(base_dir=str(tmp_path))

    # Create fake file
    file_content = b"fake audio data"
    file = io.BytesIO(file_content)

    # Save file
    path = "voice-notes/log123/audio.mp3"
    url = storage.save(file, path)

    # Verify file was written
    full_path = tmp_path / path
    assert full_path.exists()
    assert full_path.read_bytes() == file_content

    # Verify URL format
    assert url.startswith("http://localhost:8000/uploads/")
    assert url.endswith(path)


def test_local_storage_delete_removes_file(tmp_path):
    """Test LocalStorage.delete removes file from filesystem."""
    # Create LocalStorage with temp directory
    storage = LocalStorage(base_dir=str(tmp_path))

    # Create a file
    path = "voice-notes/log123/audio.mp3"
    full_path = tmp_path / path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_bytes(b"fake audio data")

    # Verify file exists
    assert full_path.exists()

    # Delete file
    storage.delete(path)

    # Verify file was deleted
    assert not full_path.exists()


def test_local_storage_delete_nonexistent_file_does_not_raise(tmp_path):
    """Test LocalStorage.delete handles nonexistent files gracefully."""
    storage = LocalStorage(base_dir=str(tmp_path))

    # Should not raise even if file doesn't exist
    storage.delete("nonexistent/path/file.mp3")


def test_gcs_storage_requires_bucket_name():
    """Test GCSStorage raises ValueError if GCS_BUCKET_NAME is not set."""
    mock_settings = Mock()
    mock_settings.gcs_bucket_name = None
    mock_settings.google_application_credentials = None

    with patch('app.core.storage.get_settings', return_value=mock_settings):
        with pytest.raises(ValueError) as exc_info:
            GCSStorage()

        assert "GCS_BUCKET_NAME" in str(exc_info.value)


def test_gcs_storage_save_uploads_to_bucket():
    """Test GCSStorage.save uploads file to GCS bucket and generates signed URL."""
    # Mock settings and GCS client
    mock_settings = Mock()
    mock_settings.gcs_bucket_name = "test-bucket"
    mock_settings.google_application_credentials = None

    # Mock the signed URL return value
    fake_signed_url = "https://storage.googleapis.com/test-bucket/voice-notes/log123/audio.mp3?X-Goog-Signature=..."
    mock_blob = Mock()
    mock_blob.generate_signed_url.return_value = fake_signed_url

    mock_bucket = Mock()
    mock_bucket.blob.return_value = mock_blob

    mock_client = Mock()
    mock_client.bucket.return_value = mock_bucket

    with patch('app.core.storage.get_settings', return_value=mock_settings):
        with patch('app.core.storage.storage.Client', return_value=mock_client):
            storage = GCSStorage()

            # Create fake file
            file_content = b"fake audio data"
            file = io.BytesIO(file_content)

            # Save file
            path = "voice-notes/log123/audio.mp3"
            url = storage.save(file, path)

            # Verify blob was created and uploaded
            mock_bucket.blob.assert_called_once_with(path)
            mock_blob.upload_from_file.assert_called_once()

            # Verify generate_signed_url was called
            mock_blob.generate_signed_url.assert_called_once()

            # Verify signed URL was returned
            assert url == fake_signed_url


def test_gcs_storage_delete_removes_blob():
    """Test GCSStorage.delete removes blob from GCS bucket."""
    # Mock settings and GCS client
    mock_settings = Mock()
    mock_settings.gcs_bucket_name = "test-bucket"
    mock_settings.google_application_credentials = None

    mock_blob = Mock()
    mock_bucket = Mock()
    mock_bucket.blob.return_value = mock_blob

    mock_client = Mock()
    mock_client.bucket.return_value = mock_bucket

    with patch('app.core.storage.get_settings', return_value=mock_settings):
        with patch('app.core.storage.storage.Client', return_value=mock_client):
            storage = GCSStorage()

            # Delete file
            path = "voice-notes/log123/audio.mp3"
            storage.delete(path)

            # Verify blob was deleted
            mock_bucket.blob.assert_called_with(path)
            mock_blob.delete.assert_called_once()


def test_gcs_storage_get_content_type():
    """Test GCSStorage._get_content_type returns correct MIME types."""
    # Mock minimal setup
    mock_settings = Mock()
    mock_settings.gcs_bucket_name = "test-bucket"
    mock_settings.google_application_credentials = None

    mock_client = Mock()
    mock_bucket = Mock()
    mock_client.bucket.return_value = mock_bucket

    with patch('app.core.storage.get_settings', return_value=mock_settings):
        with patch('app.core.storage.storage.Client', return_value=mock_client):
            storage = GCSStorage()

            # Test various file extensions
            assert storage._get_content_type("file.jpg") == "image/jpeg"
            assert storage._get_content_type("file.png") == "image/png"
            assert storage._get_content_type("file.mp3") == "audio/mpeg"
            assert storage._get_content_type("file.m4a") == "audio/mp4"
            assert storage._get_content_type("file.unknown") == "application/octet-stream"
