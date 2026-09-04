import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


URL = "https://r.jina.ai/https://boardgamegeek.com/browse/boardgame?sort=rank"

OUTPUT = "top100.json"

IMAGES_DIR = "images"

GITHUB_RAW_BASE = (
    "https://raw.githubusercontent.com/"
    "Drezamer/gbbcache/main/images"
)

TIMEOUT = 60


def fetch_url(url, user_agent, timeout=TIMEOUT):

    request = Request(
        url,
        headers={
            "User-Agent": user_agent
        },
    )

    with urlopen(
        request,
        timeout=timeout
    ) as response:

        data = response.read()

    return data


def fetch_bgg():

    print("========================================")
    print("STEP 1: FETCH BGG")
    print("========================================")
    print(f"URL: {URL}")

    try:

        data = fetch_url(
            URL,
            (
                "Mozilla/5.0 "
                "(compatible; DnDClub-BGG-Cache/1.0)"
            ),
        )

        text = data.decode(
            "utf-8",
            errors="replace"
        )

    except HTTPError as error:

        body = error.read().decode(
            "utf-8",
            errors="replace"
        )

        print(
            f"ERROR: HTTP {error.code}"
        )

        print(
            body[:2000]
        )

        raise

    except URLError as error:

        print(
            f"ERROR: URL connection failed: {error}"
        )

        raise

    except TimeoutError:

        print(
            f"ERROR: request timed out "
            f"after {TIMEOUT} seconds"
        )

        raise

    print(
        f"SUCCESS: received {len(text)} characters"
    )

    return text


def parse_games(text):

    print()
    print("========================================")
    print("STEP 2: PARSE BGG TABLE")
    print("========================================")

    games = []

    seen_ids = set()
    seen_ranks = set()

    table_rows = 0
    valid_rows = 0

    for line_number, line in enumerate(
        text.splitlines(),
        start=1
    ):

        line = line.strip()

        if "|" not in line:
            continue

        table_rows += 1

        cells = [
            cell.strip()
            for cell in line.strip("|").split("|")
        ]

        if len(cells) < 6:
            continue

        # ----------------------------------------
        # Rank
        # ----------------------------------------

        rank_match = re.search(
            r"(\d+)\s*$",
            cells[0]
        )

        if not rank_match:
            continue

        rank = int(
            rank_match.group(1)
        )

        if rank < 1 or rank > 100:
            continue

        # ----------------------------------------
        # Game link and ID
        # ----------------------------------------

        title_match = re.search(
            r"\[([^\]]+)\]\("
            r"https?://boardgamegeek\.com/"
            r"boardgame/(\d+)"
            r"(?:/[^)]*)?\)",
            cells[2]
        )

        if not title_match:
            continue

        name = title_match.group(1).strip()

        game_id = int(
            title_match.group(2)
        )

        # ----------------------------------------
        # Duplicate protection
        # ----------------------------------------

        if rank in seen_ranks:
            continue

        if game_id in seen_ids:
            continue

        # ----------------------------------------
        # Year
        # ----------------------------------------

        after_title = cells[2][
            title_match.end():
        ].strip()

        year = None

        year_match = re.match(
            r"\((\d{4})\)",
            after_title
        )

        if year_match:

            year = int(
                year_match.group(1)
            )

            after_title = after_title[
                year_match.end():
            ].strip()

        # ----------------------------------------
        # Description
        # ----------------------------------------

        description = after_title.strip()

        if not description:
            description = None

        # ----------------------------------------
        # Thumbnail URL
        # ----------------------------------------

        source_thumbnail = None

        if len(cells) > 1:

            image_match = re.search(
                r"(https?://cf\.geekdo-images\.com/.*?\.(?:jpg|jpeg|png|webp))",
                cells[1],
                re.IGNORECASE
            )

            if image_match:

                source_thumbnail = (
                    image_match.group(1)
                )

        # ----------------------------------------
        # Ratings
        # ----------------------------------------

        bayesaverage = None

        average = None

        numvoters = None

        if len(cells) > 3:

            value = cells[3].strip()

            if re.fullmatch(
                r"\d+(?:\.\d+)?",
                value
            ):

                bayesaverage = value

        if len(cells) > 4:

            value = cells[4].strip()

            if re.fullmatch(
                r"\d+(?:\.\d+)?",
                value
            ):

                average = value

        if len(cells) > 5:

            value = cells[5].replace(
                ",",
                ""
            ).strip()

            if re.fullmatch(
                r"\d+",
                value
            ):

                numvoters = int(
                    value
                )

        # ----------------------------------------
        # Initial game object
        # ----------------------------------------

        game = {

            "rank": rank,

            "id": game_id,

            "name": name,

            "year": year,

            "description": description,

            "thumbnail": source_thumbnail,

            "source_thumbnail": source_thumbnail,

            "bayesaverage": bayesaverage,

            "average": average,

            "numvoters": numvoters,

        }

        games.append(game)

        seen_ranks.add(rank)

        seen_ids.add(game_id)

        valid_rows += 1

        # ----------------------------------------
        # Diagnostics
        # ----------------------------------------

        if len(games) <= 3:

            print(
                f"Game #{rank}: {name}"
            )

            print(
                f"  Year: {year}"
            )

            print(
                f"  Geek Rating: "
                f"{bayesaverage}"
            )

            print(
                f"  Average: "
                f"{average}"
            )

            print(
                f"  Voters: "
                f"{numvoters}"
            )

            print(
                "  Source Thumbnail: "
                f"{'YES' if source_thumbnail else 'NO'}"
            )

            print(
                f"  Description: "
                f"{'YES' if description else 'NO'}"
            )

        if len(games) >= 100:
            break

    games.sort(
        key=lambda game: game["rank"]
    )

    print()

    print(
        f"Table rows detected: "
        f"{table_rows}"
    )

    print(
        f"Valid game rows: "
        f"{valid_rows}"
    )

    print(
        f"Unique games: "
        f"{len(games)}"
    )

    return games


def get_image_extension(content_type):

    if not content_type:
        return ".jpg"

    content_type = content_type.lower()

    if "image/jpeg" in content_type:
        return ".jpg"

    if "image/png" in content_type:
        return ".png"

    if "image/webp" in content_type:
        return ".webp"

    if "image/gif" in content_type:
        return ".gif"

    return ".jpg"


def download_thumbnail(game):

    game_id = game["id"]

    source_url = game.get(
        "source_thumbnail"
    )

    if not source_url:

        raise RuntimeError(
            f"No source thumbnail for "
            f"game {game_id}"
        )

    os.makedirs(
        IMAGES_DIR,
        exist_ok=True
    )

    # ----------------------------------------
    # Check whether image already exists
    # ----------------------------------------

    possible_extensions = [
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".gif",
    ]

    for extension in possible_extensions:

        existing_path = os.path.join(
            IMAGES_DIR,
            f"{game_id}{extension}"
        )

        if os.path.isfile(existing_path):

            game["thumbnail"] = (
                f"{GITHUB_RAW_BASE}/"
                f"{game_id}{extension}"
            )

            print(
                f"  EXISTS: {existing_path}"
            )

            return

    # ----------------------------------------
    # Download image
    # ----------------------------------------

    print(
        f"  DOWNLOAD: {source_url}"
    )

    request = Request(
        source_url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "(compatible; DnDClub-BGG-ImageCache/1.0)"
            ),

            "Referer":
                "https://boardgamegeek.com/",
        },
    )

    try:

        with urlopen(
            request,
            timeout=TIMEOUT
        ) as response:

            image_data = response.read()

            content_type = response.headers.get(
                "Content-Type",
                ""
            )

    except HTTPError as error:

        raise RuntimeError(
            f"Image download failed for "
            f"game {game_id}: "
            f"HTTP {error.code}"
        )

    except URLError as error:

        raise RuntimeError(
            f"Image download failed for "
            f"game {game_id}: "
            f"{error}"
        )

    if not image_data:

        raise RuntimeError(
            f"Empty image received for "
            f"game {game_id}"
        )

    extension = get_image_extension(
        content_type
    )

    filename = (
        f"{game_id}{extension}"
    )

    filepath = os.path.join(
        IMAGES_DIR,
        filename
    )

    with open(
        filepath,
        "wb"
    ) as file:

        file.write(
            image_data
        )

    file_size = os.path.getsize(
        filepath
    )

    print(
        f"  SAVED: {filepath} "
        f"({file_size} bytes)"
    )

    game["thumbnail"] = (
        f"{GITHUB_RAW_BASE}/"
        f"{filename}"
    )


def cache_images(games):

    print()
    print("========================================")
    print("STEP 3: CACHE THUMBNAILS")
    print("========================================")

    success_count = 0

    for index, game in enumerate(
        games,
        start=1
    ):

        print(
            f"[{index}/{len(games)}] "
            f"#{game['rank']} "
            f"{game['name']}"
        )

        download_thumbnail(
            game
        )

        success_count += 1

    print()

    print(
        f"Thumbnail cache complete: "
        f"{success_count}/{len(games)}"
    )


def remove_source_thumbnail(games):

    for game in games:

        game.pop(
            "source_thumbnail",
            None
        )


def validate_games(games):

    print()
    print("========================================")
    print("STEP 4: VALIDATE DATA")
    print("========================================")

    if len(games) != 100:

        raise RuntimeError(
            f"Expected exactly 100 games, "
            f"found {len(games)}"
        )

    print(
        "Count check: OK (100 games)"
    )

    for index, game in enumerate(
        games
    ):

        expected_rank = index + 1

        if game["rank"] != expected_rank:

            raise RuntimeError(
                f"Invalid rank at index "
                f"{index}: expected "
                f"{expected_rank}, got "
                f"{game['rank']}"
            )

        if (
            not isinstance(
                game["id"],
                int
            )
            or game["id"] <= 0
        ):

            raise RuntimeError(
                f"Invalid game ID at rank "
                f"{game['rank']}"
            )

        if not game["name"]:

            raise RuntimeError(
                f"Missing game name at "
                f"rank {game['rank']}"
            )

        if not game["thumbnail"]:

            raise RuntimeError(
                f"Missing cached thumbnail "
                f"at rank {game['rank']}"
            )

    print(
        "Rank check: OK"
    )

    print(
        "Game ID check: OK"
    )

    print(
        "Game name check: OK"
    )

    ratings_count = sum(
        1
        for game in games
        if game["bayesaverage"]
        is not None
    )

    averages_count = sum(
        1
        for game in games
        if game["average"]
        is not None
    )

    voters_count = sum(
        1
        for game in games
        if game["numvoters"]
        is not None
    )

    years_count = sum(
        1
        for game in games
        if game["year"]
        is not None
    )

    thumbnails_count = sum(
        1
        for game in games
        if game["thumbnail"]
        is not None
    )

    descriptions_count = sum(
        1
        for game in games
        if game["description"]
        is not None
    )

    print(
        f"Geek Ratings found: "
        f"{ratings_count}/100"
    )

    print(
        f"Average Ratings found: "
        f"{averages_count}/100"
    )

    print(
        f"Num Voters found: "
        f"{voters_count}/100"
    )

    print(
        f"Years found: "
        f"{years_count}/100"
    )

    print(
        f"Cached thumbnails found: "
        f"{thumbnails_count}/100"
    )

    print(
        f"Descriptions found: "
        f"{descriptions_count}/100"
    )

    if ratings_count < 90:

        raise RuntimeError(
            "Too many missing Geek Ratings"
        )

    if averages_count < 90:

        raise RuntimeError(
            "Too many missing Average Ratings"
        )

    if voters_count < 90:

        raise RuntimeError(
            "Too many missing Num Voters"
        )

    if thumbnails_count < 90:

        raise RuntimeError(
            "Too many missing cached thumbnails"
        )

    print(
        "Validation: SUCCESS"
    )


def save_json(games):

    print()
    print("========================================")
    print("STEP 5: SAVE JSON")
    print("========================================")

    with open(
        OUTPUT,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            games,
            file,
            ensure_ascii=False,
            indent=2
        )

    file_size = os.path.getsize(
        OUTPUT
    )

    print(
        f"Saved {len(games)} games "
        f"to {OUTPUT}"
    )

    print(
        f"File size: {file_size} bytes"
    )


def main():

    print(
        "========================================"
    )

    print(
        "BGG TOP 100 CACHE GENERATOR"
    )

    print(
        "========================================"
    )

    text = fetch_bgg()

    games = parse_games(
        text
    )

    cache_images(
        games
    )

    remove_source_thumbnail(
        games
    )

    validate_games(
        games
    )

    save_json(
        games
    )

    print()

    print(
        "========================================"
    )

    print(
        "STEP 6: FINAL RESULT"
    )

    print(
        "========================================"
    )

    first = games[0]

    print(
        f"Top game: #{first['rank']} "
        f"{first['name']}"
    )

    print(
        f"Year: {first['year']}"
    )

    print(
        f"Geek Rating: "
        f"{first['bayesaverage']}"
    )

    print(
        f"Average Rating: "
        f"{first['average']}"
    )

    print(
        f"Num Voters: "
        f"{first['numvoters']}"
    )

    print(
        f"Thumbnail: "
        f"{first['thumbnail']}"
    )

    print()

    print(
        "========================================"
    )

    print(
        "SUCCESS: BGG TOP 100 UPDATED"
    )

    print(
        "========================================"
    )


if __name__ == "__main__":

    main()
