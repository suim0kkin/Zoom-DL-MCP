"""Unit tests for Zoom-DL-MCP core logic."""

import unittest
from zoom_dl_mcp.core import RecordingMetadata, ZoomRecordingClient, ZoomDownloadError


class TestZoomRecordingClient(unittest.TestCase):
    def test_recording_metadata_safe_filename(self):
        meta = RecordingMetadata(
            topic="Test / Meeting: Topic *with* ?bad <chars> | and spaces",
            duration_seconds=3600,
            created_time_str="2026-11-10",
            play_url="https://example.com/video.mp4",
            file_size_bytes=1024 * 1024 * 50
        )
        self.assertEqual(meta.safe_filename, "Test_Meeting_Topic_with_bad_chars_and_spaces.mp4")

    def test_recording_metadata_fallback_filename(self):
        meta = RecordingMetadata(
            topic="   ///???   ",
            duration_seconds=120,
            created_time_str="2026-11-10",
            play_url="https://example.com/video.mp4"
        )
        self.assertEqual(meta.safe_filename, "zoom_recording.mp4")

    def test_extract_play_info_api_path(self):
        client = ZoomRecordingClient()
        html = '''
        <html>
        <script>
        window.__zm_unified_player__ = {
            playInfoApi: "\\/nws\\/recording\\/2.0\\/share\\/12345678-ABCD-EF01-2345-6789ABCDEF01?pageType=web"
        };
        </script>
        </html>
        '''
        path = client._extract_play_info_api_path(html)
        self.assertEqual(path, "/nws/recording/2.0/share/12345678-ABCD-EF01-2345-6789ABCDEF01?pageType=web")

    def test_extract_play_info_api_path_missing(self):
        client = ZoomRecordingClient()
        html = "<html><body>No script here</body></html>"
        with self.assertRaises(ZoomDownloadError):
            client._extract_play_info_api_path(html)


if __name__ == "__main__":
    unittest.main()
