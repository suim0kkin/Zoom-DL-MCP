"""Zoom-DL-MCP: Zero-dependency Zoom Cloud Recording Downloader & MCP Server."""

from zoom_dl_mcp.core import RecordingMetadata, ZoomDownloadError, ZoomRecordingClient

__version__ = "1.0.0"
__all__ = ["ZoomRecordingClient", "RecordingMetadata", "ZoomDownloadError"]
