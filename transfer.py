import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlencode


BASE_URL = os.environ.get("SYNC_URL", "").strip()
TOKEN = os.environ.get("SYNC_TOKEN", "").strip()
RUN_ID = os.environ.get("GITHUB_RUN_ID", "local").strip()


if not BASE_URL:
    raise RuntimeError("Missing SYNC_URL")

if not TOKEN:
    raise RuntimeError("Missing SYNC_TOKEN")


BASE_URL = BASE_URL.rstrip("?")


def post(action, data=b"", params=None, content_type="application/octet-stream"):
    query = {
        "action": action,
        "run_id": RUN_ID,
    }

    if params:
        query.update(params)

    url = BASE_URL + "?" + urlencode(query)

    request = Request(
        url,
        data=data,
        method="POST",
        headers={
            "User-Agent": "DataTransfer/1.0",
            "X-Sync-Token": TOKEN,
            "Content-Type": content_type,
        },
    )

    try:
        with urlopen(request, timeout=60) as response:
            body = response.read().decode("utf-8", errors="replace")
            if response.status < 200 or response.status >= 300:
                raise RuntimeError(f"HTTP {response.status}: {body[:500]}")
            return body
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {error.code}: {body[:500]}") from error
    except URLError as error:
        raise RuntimeError(f"Connection failed: {error}") from error


root = Path(__file__).resolve().parent
json_path = root / "top100.json"
images_dir = root / "images"


with json_path.open("rb") as file:
    manifest = file.read()


games = json.loads(manifest.decode("utf-8"))

if not isinstance(games, list) or not games:
    raise RuntimeError("Invalid data file")


print(f"Starting transfer: {len(games)} games")
post("start", manifest, content_type="application/json")
print("Remote staging created")


processed = 0

try:
    for game in games:
        game_id = str(game["id"])
        relative = str(game.get("thumbnail_local", ""))

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

        post(
            "image",
            image_data,
            params={"name": filename},
        )

        processed += 1

        print(
            f"[{processed}/{len(games)}] {game['name']}"
        )

    post("finish", b"", content_type="text/plain")
    print(
        f"Transfer complete: {processed}/{len(games)}"
    )

except Exception as error:
    print(f"TRANSFER FAILED: {error}", file=sys.stderr)
    try:
        post("fail", str(error).encode("utf-8"), content_type="text/plain")
    except Exception as notify_error:
        print(
            f"Could not report failure: {notify_error}",
            file=sys.stderr,
        )
    raise
