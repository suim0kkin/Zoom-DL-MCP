"""Model Context Protocol (MCP) server implementation for Zoom recording downloads."""

from __future__ import annotations

import json
import os
import sys
import traceback
from typing import Any, Dict, Optional

from zoom_dl_mcp.core import RecordingMetadata, ZoomDownloadError, ZoomRecordingClient

TOOLS_METADATA = [
    {
        "name": "zoom_get_recording_info",
        "description": "Extracts metadata (topic, duration, file size, direct stream URL) from a public or password-protected Zoom cloud recording link.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The Zoom cloud recording URL (e.g. https://zoom.us/rec/share/...)",
                },
                "password": {
                    "type": "string",
                    "description": "Passcode required to view or download the recording, if any.",
                },
            },
            "required": ["url"],
        },
    },
    {
        "name": "zoom_download_recording",
        "description": "Downloads a Zoom cloud recording directly to local disk using reverse-engineered Unified Player session tokens without browser automation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The Zoom cloud recording URL",
                },
                "password": {
                    "type": "string",
                    "description": "Passcode required to view or download the recording, if any.",
                },
                "output_path": {
                    "type": "string",
                    "description": "Destination file path or directory. Defaults to ./downloads/<topic>.mp4",
                },
            },
            "required": ["url"],
        },
    },
]


class ZoomMCPServer:
    """Zero-dependency stdio JSON-RPC MCP server adhering to 2024-11-05 protocol."""

    def __init__(self, default_download_dir: Optional[str] = None) -> None:
        self.client = ZoomRecordingClient()
        self.default_download_dir = default_download_dir or os.path.abspath("./downloads")

    def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any] | None:
        method = request.get("method")
        msg_id = request.get("id")

        if method == "notifications/initialized":
            return None

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "zoom-dl-mcp",
                        "version": "1.0.0",
                    },
                },
            }

        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": TOOLS_METADATA},
            }

        if method == "tools/call":
            params = request.get("params", {})
            tool_name = params.get("name")
            tool_args = params.get("arguments", {})

            try:
                if tool_name == "zoom_get_recording_info":
                    url = tool_args["url"]
                    password = tool_args.get("password")
                    metadata = self.client.fetch_recording_metadata(url, password=password)

                    response_body = {
                        "topic": metadata.topic,
                        "duration_seconds": metadata.duration_seconds,
                        "created_time_str": metadata.created_time_str,
                        "file_size_bytes": metadata.file_size_bytes,
                        "file_size_mb": round(
                            (metadata.file_size_bytes or 0) / (1024 * 1024), 2
                        ),
                        "safe_filename": metadata.safe_filename,
                        "play_url": metadata.play_url,
                    }
                    return {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": json.dumps(
                                        response_body, ensure_ascii=False, indent=2
                                    ),
                                }
                            ]
                        },
                    }

                if tool_name == "zoom_download_recording":
                    url = tool_args["url"]
                    password = tool_args.get("password")
                    output_target = tool_args.get("output_path")

                    metadata = self.client.fetch_recording_metadata(url, password=password)

                    if not output_target:
                        destination_path = os.path.join(
                            self.default_download_dir, metadata.safe_filename
                        )
                    elif os.path.isdir(output_target):
                        destination_path = os.path.join(
                            output_target, metadata.safe_filename
                        )
                    else:
                        destination_path = output_target

                    saved_path = self.client.download_file(metadata, destination_path)
                    saved_size = os.path.getsize(saved_path)

                    response_body = {
                        "status": "success",
                        "saved_path": os.path.abspath(saved_path),
                        "topic": metadata.topic,
                        "file_size_bytes": saved_size,
                        "file_size_mb": round(saved_size / (1024 * 1024), 2),
                    }
                    return {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": json.dumps(
                                        response_body, ensure_ascii=False, indent=2
                                    ),
                                }
                            ]
                        },
                    }

                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {tool_name}",
                    },
                }

            except Exception as execution_error:
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "isError": True,
                        "content": [
                            {
                                "type": "text",
                                "text": f"Error: {execution_error}\n{traceback.format_exc()}",
                            }
                        ],
                    },
                }

        if msg_id is not None:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": -32601,
                    "message": f"Unsupported method: {method}",
                },
            }
        return None

    def run(self) -> None:
        """Runs the stdio event loop."""
        for line in sys.stdin:
            stripped_line = line.strip()
            if not stripped_line:
                continue
            try:
                request = json.loads(stripped_line)
            except json.JSONDecodeError:
                continue

            response = self.handle_request(request)
            if response is not None:
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()


def run_server() -> None:
    server = ZoomMCPServer()
    server.run()


if __name__ == "__main__":
    run_server()
