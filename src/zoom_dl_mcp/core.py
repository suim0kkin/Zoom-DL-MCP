"""Core client engine for reverse-engineering Zoom Unified Player sessions."""

from __future__ import annotations

import http.cookiejar
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass(frozen=True)
class RecordingMetadata:
    """Immutable data container holding parsed Zoom recording properties."""

    topic: str
    duration_seconds: int
    created_time_str: str
    play_url: str
    file_size_bytes: Optional[int] = None

    @property
    def safe_filename(self) -> str:
        """Derives a filesystem-safe filename from the topic name."""
        sanitized_topic = re.sub(r'[\\/*?:"<>| ]+', "_", self.topic).strip("_")
        return f"{sanitized_topic or 'zoom_recording'}.mp4"


class ZoomDownloadError(Exception):
    """Raised when Zoom session initialization, authentication, or streaming fails."""

    pass


class ZoomRecordingClient:
    """Reverse-engineered HTTP client communicating directly with Zoom Unified Player APIs.

    Avoids headless browsers by replicating Zoom player's internal state machine:
    1. Initial GET -> Harvest session cookies & parse playInfoApi.
    2. Optional Passcode POST -> Authenticate session against /verify-passcode.
    3. Authenticated GET -> Obtain signed CDN streaming MP4 URL.
    4. Stream GET -> Direct Range/Chunk download with session cookie authentication.
    """

    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    def __init__(self, user_agent: Optional[str] = None) -> None:
        self.cookie_jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookie_jar)
        )
        self.user_agent = user_agent or self.DEFAULT_USER_AGENT

    def _build_request_headers(
        self,
        referer: Optional[str] = None,
        content_type: Optional[str] = None,
        origin: Optional[str] = None,
    ) -> dict[str, str]:
        headers = {"User-Agent": self.user_agent}
        if referer:
            headers["Referer"] = referer
        if content_type:
            headers["Content-Type"] = content_type
        if origin:
            headers["Origin"] = origin
        return headers

    def _extract_play_info_api_path(self, html_body: str) -> str:
        """Parses the relative playInfoApi endpoint from landing page JavaScript."""
        match = re.search(r'playInfoApi:\s*["\']([^"\']+)["\']', html_body)
        if not match:
            raise ZoomDownloadError("Failed to locate playInfoApi endpoint in Zoom page HTML.")
        raw_api_path = match.group(1)
        # Handle JSON escaped slashes (e.g. \/nws\/recording\/...)
        return raw_api_path.replace(r"\/", "/")

    def fetch_recording_metadata(
        self, share_url: str, password: Optional[str] = None
    ) -> RecordingMetadata:
        """Authenticates against the Zoom cloud player and extracts media metadata."""
        init_request = urllib.request.Request(
            share_url,
            headers=self._build_request_headers(referer="https://zoom.us/"),
        )
        try:
            with self.opener.open(init_request) as response:
                html_body = response.read().decode("utf-8", errors="replace")
        except urllib.error.URLError as connection_error:
            raise ZoomDownloadError(
                f"Failed to access Zoom URL: {connection_error}"
            ) from connection_error

        api_relative_path = self._extract_play_info_api_path(html_body)
        parsed_url = urllib.parse.urlparse(share_url)
        origin_domain = f"{parsed_url.scheme}://{parsed_url.netloc}"
        play_info_url = urllib.parse.urljoin(origin_domain, api_relative_path)

        # Check authentication requirements via playInfoApi
        play_info_request = urllib.request.Request(
            play_info_url,
            headers=self._build_request_headers(referer=share_url),
        )
        with self.opener.open(play_info_request) as response:
            initial_info = json.loads(response.read().decode("utf-8"))

        result_payload = initial_info.get("result", {})
        middle_page_info = (
            result_payload.get("middlePageInfo")
            if isinstance(result_payload, dict)
            else None
        )

        # Handle passcode verification if requested by Zoom player
        if middle_page_info and middle_page_info.get("pageType") == "verifyPasscode":
            if not password:
                raise ZoomDownloadError(
                    "Recording is passcode-protected, but no password was provided."
                )

            verify_api_path = (
                middle_page_info.get("operation", {})
                .get("action", {})
                .get("postApi")
            )
            if not verify_api_path:
                raise ZoomDownloadError("Failed to identify verify-passcode endpoint in player response.")

            verify_url = urllib.parse.urljoin(origin_domain, verify_api_path)
            post_payload = json.dumps({"passwd": password.strip()}).encode("utf-8")
            auth_headers = self._build_request_headers(
                referer=share_url,
                content_type="application/json",
                origin=origin_domain,
            )
            verify_request = urllib.request.Request(
                verify_url, data=post_payload, headers=auth_headers
            )

            with self.opener.open(verify_request) as response:
                verify_result = json.loads(response.read().decode("utf-8"))

            if not verify_result.get("status"):
                error_message = (
                    verify_result.get("errorMessage")
                    or "Invalid passcode or verification failed."
                )
                raise ZoomDownloadError(f"Passcode authentication failed: {error_message}")

            # Re-fetch metadata with now-authenticated session cookies
            auth_play_info_request = urllib.request.Request(
                play_info_url,
                headers=self._build_request_headers(referer=share_url),
            )
            with self.opener.open(auth_play_info_request) as response:
                play_data = json.loads(response.read().decode("utf-8"))
        else:
            play_data = initial_info

        media_info = play_data.get("result", {}).get("mediaInfo", {})
        play_url = media_info.get("playUrl")
        if not play_url:
            raise ZoomDownloadError(
                "Authenticated successfully, but no direct playUrl was returned by Zoom."
            )

        topic = media_info.get("mediaTopic") or "Zoom_Recording"
        duration_seconds = int(media_info.get("mediaDuration") or 0)
        created_time_str = media_info.get("createdTimeStr") or ""

        # Measure content length using Range header
        file_size_bytes: Optional[int] = None
        range_probe_request = urllib.request.Request(
            play_url,
            headers={
                **self._build_request_headers(referer="https://zoom.us/"),
                "Range": "bytes=0-0",
            },
        )
        try:
            with self.opener.open(range_probe_request) as range_response:
                content_range = range_response.headers.get("Content-Range", "")
                if "/" in content_range:
                    file_size_bytes = int(content_range.rsplit("/", 1)[-1])
        except Exception:
            file_size_bytes = None

        return RecordingMetadata(
            topic=topic,
            duration_seconds=duration_seconds,
            created_time_str=created_time_str,
            play_url=play_url,
            file_size_bytes=file_size_bytes,
        )

    def download_file(
        self,
        metadata: RecordingMetadata,
        destination_path: str,
        chunk_size: int = 1024 * 1024,
        progress_callback: Optional[Callable[[int, Optional[int]], None]] = None,
    ) -> str:
        """Streams the video data to local storage using the authenticated session."""
        os.makedirs(os.path.dirname(os.path.abspath(destination_path)), exist_ok=True)

        stream_request = urllib.request.Request(
            metadata.play_url,
            headers=self._build_request_headers(referer="https://zoom.us/"),
        )

        with self.opener.open(stream_request) as response, open(
            destination_path, "wb"
        ) as output_file:
            downloaded_bytes = 0
            total_bytes = metadata.file_size_bytes

            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                output_file.write(chunk)
                downloaded_bytes += len(chunk)
                if progress_callback:
                    progress_callback(downloaded_bytes, total_bytes)

        return destination_path
