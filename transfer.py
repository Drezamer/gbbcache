import hashlib
import json
import os
import struct
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlencode


BASE_URL = os.environ.get("SYNC_URL", "").strip()
TOKEN = os.environ.get("SYNC_TOKEN", "").strip()
RUN_ID = os.environ.get("GITHUB_RUN_ID", "local").strip()

MAX_BATCH_IMAGES = 15
MAX_BATCH_BYTES = 7_000_000
MAX_RETRIES = 5

if not BASE_URL:
    raise RuntimeError("Missing SYNC_URL")

if not TOKEN:
    raise RuntimeError("Missing SYNC_TOKEN")

BASE_URL = BASE_URL.rstrip("?")


def request_status_code(error):
    if isinstance(error, HTTPError):
        return int(error.code)
    return 0


def post(action, data=b"", params=None, content_type="application/octet-stream", extra_headers=None):
    query = {
        "action": action,
        "run_id": RUN_ID,
    }

    if params:
        query.update(params)

    url = BASE_URL + "?" + urlencode(query)

    headers = {
        "User-Agent": "DataTransfer/2.0",
        "X-Sync-Token": TOKEN,
        "Content-Type": content_type,
        "Cache-Control": "no-cache",
    }

    if extra_headers:
        headers.update(extra_headers)

    request = Request(
        url,
        data=data,
        method="POST",
        headers=headers,
    )

    try:
        with urlopen(request, timeout=90) as response:
            body = response.read().decode("utf-8", errors="replace")
            if response.status < 200 or response.status >= 300:
                raise RuntimeError(
                    f"HTTP {response.status}: {body[:500]}"
                )
            return body

    except HTTPError as error:
        body = error.read().decode(
            "utf-8",
            errors="replace"
        )
        raise RuntimeError(
            f"HTTP {error.code}: {body[:500]}"
        ) from error

    except URLError as error:
        raise RuntimeError(
            f"Connection failed: {error}"
        ) from error


def post_with_retry(action, data=b"", params=None, content_type="application/octet-stream", extra_headers=None):
    delays = [3, 6, 12, 24, 30]

    last_error = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            return post(
                action,
                data=data,
                params=params,
                content_type=content_type,
                extra_headers=extra_headers,
            )

        except Exception as error:
            last_error = error
            code = request_status_code(error)

            retryable = (
                code in (403, 408, 409, 425, 429)
                or code >= 500
                or code == 0
            )

            if not retryable or attempt >= MAX_RETRIES:
                raise

            delay = delays[min(attempt, len(delays) - 1)]

            print(
                f"Retryable transfer error ({code or 'network'}): "
                f"{error}. Retry in {delay}s...",
                file=sys.stderr,
            )

            time.sleep(delay)

    raise last_error


def build_batch(items):
    payload = bytearray()
    payload.extend(b"DCP1")
    payload.extend(struct.pack("!I", len(items)))

    for filename, image_data in items:
        filename_bytes = filename.encode("utf-8")

        if len(filename_bytes) > 65535:
            raise RuntimeError(
                f"Filename too long: {filename}"
            )

        if len(image_data) > 0xFFFFFFFF:
            raise RuntimeError(
                f"Image too large: {filename}"
            )

        payload.extend(
            struct.pack(
                "!H",
                len(filename_bytes)
            )
        )

        payload.extend(
            struct.pack(
                "!I",
                len(image_data)
            )
        )

        payload.extend(filename_bytes)
        payload.extend(image_data)

    return bytes(payload)


root = Path(__file__).resolve().parent
json_path = root / "top100.json"

with json_path.open("rb") as file:
    manifest = file.read()

games = json.loads(
    manifest.decode("utf-8")
)

if not isinstance(games, list) or not games:
    raise RuntimeError("Invalid data file")

print(
    f"Starting transfer: {len(games)} games"
)

post_with_retry(
    "start",
    manifest,
    content_type="application/json"
)

print("Remote staging created")

batch_items = []
batch_bytes = 8
batch_index = 0
processed = 0

try:
    for game in games:
        game_id = str(game["id"])
        relative = str(
            game.get("thumbnail_local", "")
        )

        if not relative.startswith("images/"):
            raise RuntimeError(
                f"Invalid image path for game {game_id}: {relative}"
            )

        filename = Path(relative).name
        image_path = root / relative

        if not image_path.is_file():
            raise RuntimeError(
                f"Missing image for game {game_id}: {relative}"
            )

        image_data = image_path.read_bytes()
        item_size = len(image_data) + len(filename.encode("utf-8")) + 6

        if image_data == b"":
            raise RuntimeError(
                f"Empty image for game {game_id}"
            )

        if batch_items and (
            len(batch_items) >= MAX_BATCH_IMAGES
            or batch_bytes + item_size > MAX_BATCH_BYTES
        ):
            batch_data = build_batch(batch_items)
            digest = hashlib.sha256(batch_data).hexdigest()

            batch_index += 1

            post_with_retry(
                "batch",
                batch_data,
                params={
                    "batch": str(batch_index),
                },
                content_type="application/octet-stream",
                extra_headers={
                    "X-Batch-SHA256": digest,
                },
            )

            processed += len(batch_items)

            percent = int(
                (processed / len(games)) * 100
            )

            print(
                f"BATCH {batch_index}: "
                f"{processed}/{len(games)} "
                f"({percent}%)"
            )

            batch_items = []
            batch_bytes = 8

            # Gentle spacing helps shared-hosting WAFs.
            time.sleep(2)

        batch_items.append(
            (
                filename,
                image_data
            )
        )

        batch_bytes += item_size

    if batch_items:
        batch_data = build_batch(batch_items)
        digest = hashlib.sha256(batch_data).hexdigest()

        batch_index += 1

        post_with_retry(
            "batch",
            batch_data,
            params={
                "batch": str(batch_index),
            },
            content_type="application/octet-stream",
            extra_headers={
                "X-Batch-SHA256": digest,
            },
        )

        processed += len(batch_items)

        percent = int(
            (processed / len(games)) * 100
        )

        print(
            f"BATCH {batch_index}: "
            f"{processed}/{len(games)} "
            f"({percent}%)"
        )

    if processed != len(games):
        raise RuntimeError(
            f"Transfer count mismatch: "
            f"{processed}/{len(games)}"
        )

    post_with_retry(
        "finish",
        b"",
        content_type="text/plain"
    )

    print(
        f"Transfer complete: "
        f"{processed}/{len(games)}"
    )

except Exception as error:
    print(
        f"TRANSFER FAILED: {error}",
        file=sys.stderr
    )

    try:
        post_with_retry(
            "fail",
            str(error).encode("utf-8"),
            content_type="text/plain"
        )
    except Exception as notify_error:
        print(
            f"Could not report failure: {notify_error}",
            file=sys.stderr,
        )

    raise
