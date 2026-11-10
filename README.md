# Zoom-DL-MCP

Zoom Cloud Recording Downloader & Model Context Protocol (MCP) Server.

パスワード保護されたZoomクラウド録画から、ヘッドレスブラウザ（Selenium/Playwright）を用いずに直接MP4動画を抽出・ダウンロードするためのCLIツールおよびMCPサーバーです。Python標準ライブラリのみで実装されています。

---

## 概要

Zoomのウェブ版Unified Playerの認証通信をプロトコルレベルでエミュレートし、セッションCookieのハンドシェイクとパスコード認証APIを経て、署名付きCDNストリームURLを直接解決します。

- 外部依存パッケージなし（Python 3.8+ 標準ライブラリのみ）
- ブラウザプロセス（Chromium等）の起動オーバーヘッドなし
- 署名付きCDN（AWS CloudFront）からの直接ストリーミング転送
- MCP（Model Context Protocol）、CLI、Pythonモジュールに対応

---

## システム要件

- Python 3.8 以上

---

## インストール

```bash
git clone https://github.com/suim0kkin/Zoom-DL-MCP.git
cd Zoom-DL-MCP
pip install -e .
```

※ インストールを行わず、リポジトリ内のスクリプトを直接実行することも可能です。

---

## CLI の使用方法

### 基本構文

```bash
zoom-dl "<ZOOM_URL>" -p "<PASSCODE>"
```

### オプション

- `-p`, `--password`: パスコード保護されている録画のパスワード。
- `-o`, `--output`: 保存先のファイルパスまたはディレクトリ（デフォルト: `./downloads/<トピック名>.mp4`）。
- `--info-only`: ダウンロードを実行せず、メタデータと署名付きCDN URLのみを表示。

### 実行例

```bash
# ダウンロード実行
zoom-dl "https://zoom.us/rec/share/..." -p "secret123" -o ./recordings/

# メタデータ確認のみ
zoom-dl "https://zoom.us/rec/share/..." -p "secret123" --info-only
```

---

## MCP サーバー設定

Claude Desktop、Antigravity、Cursor等のMCPクライアント設定ファイル（`claude_desktop_config.json` 等）に以下を追加します。

```json
{
  "mcpServers": {
    "zoom-dl": {
      "command": "python3",
      "args": [
        "/path/to/Zoom-DL-MCP/src/zoom_dl_mcp/server.py"
      ]
    }
  }
}
```

### 提供ツール仕様

#### `zoom_get_recording_info`
- **引数**:
  - `url` (string, 必須): Zoom録画の共有URL。
  - `password` (string, 任意): 録画のパスコード。
- **返却値**:
  - `topic`: 会議名 / トピック。
  - `duration_seconds`: 録画時間（秒）。
  - `file_size_bytes`: 動画ファイルサイズ（バイト）。
  - `play_url`: 署名付きCDN MP4 URL。

#### `zoom_download_recording`
- **引数**:
  - `url` (string, 必須): Zoom録画の共有URL。
  - `password` (string, 任意): 録画のパスコード。
  - `output_path` (string, 任意): 保存先ファイルパスまたはディレクトリ。
- **返却値**:
  - `saved_path`: 保存完了したローカル絶対パス。
  - `file_size_bytes`: 保存されたファイルサイズ。

---

## Python API

```python
from zoom_dl_mcp import ZoomRecordingClient

client = ZoomRecordingClient()

# メタデータの取得
metadata = client.fetch_recording_metadata(
    share_url="https://zoom.us/rec/share/...",
    password="secret_passcode"
)
print(f"Topic: {metadata.topic}")
print(f"Duration: {metadata.duration_seconds}s")
print(f"URL: {metadata.play_url}")

# ダウンロードの実行
saved_path = client.download_file(
    metadata=metadata,
    destination_path="./downloads/output.mp4"
)
```

---

## 内部シーケンス

```
[Client]                      [Zoom Web]                  [Zoom CDN]
   |                              |                           |
   |-- 1. GET /rec/share/{id} --->|                           |
   |   (CookieJar初期化)          |                           |
   |<-- HTML (playInfoApi抽出) ---|                           |
   |                              |                           |
   |-- 2. GET playInfoApi ------->|                           |
   |<-- middlePageInfo (認証要求) -|                           |
   |                              |                           |
   |-- 3. POST /verify-passcode ->|                           |
   |   {"passwd": "..."}          |                           |
   |<-- 200 OK (Cookie付与) ------|                           |
   |                              |                           |
   |-- 4. GET playInfoApi ------->|                           |
   |<-- mediaInfo (playUrl解決) --|                           |
   |                                                          |
   |-- 5. GET playUrl (Range: bytes=0-0) -------------------->|
   |<-- 206 Partial Content (サイズ確定) ---------------------|
   |                                                          |
   |-- 6. GET playUrl (ストリーム転送) ----------------------->|
   |<-- 200/206 Binary Data (MP4) ----------------------------|
```

---

## テスト

```bash
python3 -m unittest discover -s tests
```

---

## ライセンス

MIT License
