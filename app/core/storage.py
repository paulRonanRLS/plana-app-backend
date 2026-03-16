"""
Storage abstraction for file uploads.

Supports local filesystem storage and Google Cloud Storage.

Set USE_GCS=true to use Google Cloud Storage, or USE_GCS=false for local storage.
GCS uses GOOGLE_APPLICATION_CREDENTIALS from environment (same credentials as Vision API).
"""

import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO

from google.cloud import storage

from app.config import get_settings

logger = logging.getLogger(__name__)


class StorageBackend(ABC):
    """Abstract base class for storage backends."""

    @abstractmethod
    def save(self, file: BinaryIO, path: str) -> str:
        """
        Save a file to storage.

        Args:
            file: File-like object to save
            path: Relative path where file should be stored

        Returns:
            Accessible URL to the saved file
        """
        pass

    @abstractmethod
    def delete(self, path: str) -> None:
        """
        Delete a file from storage.

        Args:
            path: Relative path of file to delete
        """
        pass


class LocalStorage(StorageBackend):
    """Local filesystem storage backend."""

    def __init__(self, base_dir: str = "uploads"):
        """
        Initialize local storage.

        Args:
            base_dir: Base directory for uploads (relative to project root)
        """
        self.base_dir = Path(base_dir)
        # Create base directory if it doesn't exist
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, file: BinaryIO, path: str) -> str:
        """
        Save file to local filesystem.

        Args:
            file: File-like object to save
            path: Relative path (e.g., "voice-notes/log123/abc.mp3")

        Returns:
            Accessible localhost URL
        """
        # Full path on disk
        full_path = self.base_dir / path

        # Create parent directories if needed
        full_path.parent.mkdir(parents=True, exist_ok=True)

        # Write file to disk
        with open(full_path, "wb") as f:
            content = file.read()
            f.write(content)

        # Return localhost URL
        settings = get_settings()
        # Construct URL based on environment
        base_url = os.getenv("BASE_URL", "http://localhost:8000")
        return f"{base_url}/uploads/{path}"

    def delete(self, path: str) -> None:
        """
        Delete file from local filesystem.

        Args:
            path: Relative path of file to delete
        """
        full_path = self.base_dir / path

        if full_path.exists():
            full_path.unlink()


class GCSStorage(StorageBackend):
    """Google Cloud Storage backend."""

    def __init__(self):
        """
        Initialize Google Cloud Storage client.

        Reads GCS_BUCKET_NAME from settings.
        Uses GOOGLE_APPLICATION_CREDENTIALS automatically (same as Vision API).
        """
        settings = get_settings()
        self.bucket_name = settings.gcs_bucket_name
        if not self.bucket_name:
            raise ValueError("GCS_BUCKET_NAME must be configured in settings when USE_GCS=true")

        # Set GOOGLE_APPLICATION_CREDENTIALS if provided in settings
        # (same pattern as vision_client.py)
        if settings.google_application_credentials and isinstance(settings.google_application_credentials, str):
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = settings.google_application_credentials
            logger.info(f"Set GOOGLE_APPLICATION_CREDENTIALS for GCS: {settings.google_application_credentials}")

        try:
            self.client = storage.Client()
            self.bucket = self.client.bucket(self.bucket_name)
            logger.info(f"Google Cloud Storage client initialized for bucket: {self.bucket_name}")
        except Exception as e:
            logger.error(f"Failed to initialize Google Cloud Storage client: {e}")
            raise

    def save(self, file: BinaryIO, path: str) -> str:
        """
        Save file to Google Cloud Storage.

        Args:
            file: File-like object to save
            path: Relative path (e.g., "voice-notes/log123/abc.mp3")

        Returns:
            Signed URL valid for 1 hour
        """
        from datetime import timedelta

        try:
            # Create blob in bucket
            blob = self.bucket.blob(path)

            # Determine content type from file extension
            content_type = self._get_content_type(path)

            # Upload file bytes
            file.seek(0)  # Ensure we're at the beginning
            blob.upload_from_file(file, content_type=content_type)

            # Generate signed URL (valid for 1 hour)
            signed_url = blob.generate_signed_url(
                version="v4",
                expiration=timedelta(hours=1),
                method="GET"
            )

            logger.info(f"Uploaded file to GCS and generated signed URL: {path}")
            return signed_url

        except Exception as e:
            logger.error(f"Failed to upload file to GCS: {e}")
            raise RuntimeError(f"Failed to upload file to Google Cloud Storage: {e}") from e

    def delete(self, path: str) -> None:
        """
        Delete file from Google Cloud Storage.

        Args:
            path: Relative path of file to delete
        """
        try:
            blob = self.bucket.blob(path)
            blob.delete()
            logger.info(f"Deleted file from GCS: {path}")
        except Exception as e:
            logger.warning(f"Failed to delete file from GCS: {e}")
            # Don't raise - file might already be deleted or not exist

    def _get_content_type(self, path: str) -> str:
        """
        Determine content type from file extension.

        Args:
            path: File path with extension

        Returns:
            MIME type string
        """
        extension = Path(path).suffix.lower()
        content_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.mp3': 'audio/mpeg',
            '.m4a': 'audio/mp4',
            '.wav': 'audio/wav',
            '.pdf': 'application/pdf',
            '.json': 'application/json',
        }
        return content_types.get(extension, 'application/octet-stream')


def get_storage() -> StorageBackend:
    """
    Get the configured storage backend.

    Returns GCSStorage if USE_GCS=true in environment, otherwise LocalStorage.

    Returns:
        Configured StorageBackend instance
    """
    settings = get_settings()

    if settings.use_gcs:
        return GCSStorage()
    else:
        return LocalStorage()
