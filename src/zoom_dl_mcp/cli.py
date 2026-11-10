"""Command line interface for Zoom-DL-MCP."""

from __future__ import annotations

import argparse
import os
import sys
import time

from zoom_dl_mcp.core import ZoomDownloadError, ZoomRecordingClient


def format_bytes(total_bytes: int) -> str:
    """Formats bytes into a readable unit."""
    units = ["B", "KB", "MB", "GB", "TB"]
    current_value = float(total_bytes)
    for unit in units:
        if current_value < 1024.0 or unit == units[-1]:
            return f"{current_value:.2f} {unit}"
        current_value /= 1024.0
    return f"{total_bytes} B"


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="zoom-dl",
        description="Fast, browserless Zoom cloud recording downloader.",
    )
    parser.add_argument("url", help="Zoom recording share URL (https://zoom.us/rec/share/...)")
    parser.add_argument("-p", "--password", help="Passcode for protected recordings", default=None)
    parser.add_argument("-o", "--output", help="Destination file path or output directory", default=None)
    parser.add_argument(
        "--info-only", action="store_true", help="Display metadata and direct CDN link without downloading"
    )

    args = parser.parse_args()

    client = ZoomRecordingClient()
    sys.stdout.write(f"[*] Probing Zoom Unified Player for: {args.url}\n")
    sys.stdout.flush()

    try:
        metadata = client.fetch_recording_metadata(args.url, password=args.password)
    except ZoomDownloadError as error:
        sys.stderr.write(f"[!] Extraction Error: {error}\n")
        return 1

    sys.stdout.write("=" * 60 + "\n")
    sys.stdout.write(f"Topic:        {metadata.topic}\n")
    sys.stdout.write(
        f"Duration:     {metadata.duration_seconds // 60}m {metadata.duration_seconds % 60}s\n"
    )
    sys.stdout.write(f"Created:      {metadata.created_time_str}\n")
    size_label = (
        format_bytes(metadata.file_size_bytes)
        if metadata.file_size_bytes
        else "Unknown (Streaming)"
    )
    sys.stdout.write(f"File Size:    {size_label}\n")
    sys.stdout.write("=" * 60 + "\n")

    if args.info_only:
        sys.stdout.write(f"Direct Signed CDN URL:\n{metadata.play_url}\n")
        return 0

    if args.output:
        if os.path.isdir(args.output):
            destination_path = os.path.join(args.output, metadata.safe_filename)
        else:
            destination_path = args.output
    else:
        destination_path = os.path.join("./downloads", metadata.safe_filename)

    sys.stdout.write(f"[*] Initiating download to: {destination_path}\n")
    sys.stdout.flush()

    start_timestamp = time.time()

    def on_progress(downloaded_bytes: int, total_bytes: int | None) -> None:
        elapsed_seconds = max(0.001, time.time() - start_timestamp)
        throughput_bps = downloaded_bytes / elapsed_seconds
        throughput_label = f"{format_bytes(int(throughput_bps))}/s"

        if total_bytes:
            percentage = (downloaded_bytes / total_bytes) * 100.0
            sys.stdout.write(
                f"\rProgress: [{downloaded_bytes:,} / {total_bytes:,} bytes] ({percentage:.1f}%) @ {throughput_label}"
            )
        else:
            sys.stdout.write(
                f"\rProgress: {downloaded_bytes:,} bytes @ {throughput_label}"
            )
        sys.stdout.flush()

    try:
        saved_file = client.download_file(
            metadata, destination_path, progress_callback=on_progress
        )
        sys.stdout.write(f"\n[+] Successfully saved: {saved_file}\n")
        return 0
    except Exception as download_error:
        sys.stderr.write(f"\n[!] Download failed: {download_error}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
