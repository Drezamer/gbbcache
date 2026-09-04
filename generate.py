import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


URL = "https://r.jina.ai/https://boardgamegeek.com/browse/boardgame?sort=rank"
OUTPUT = "top100.json"

TIMEOUT = 60


def fetch_bgg():
    print("=== STEP 1: FETCH BGG ===")
    print(f"URL: {URL}")

    request = Request(
        URL,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; DnDClub-BGG-Cache/1.0)"
        },
    )

    try:
        with urlopen(request, timeout=TIMEOUT) as response:
            text = response.read().decode(
                "utf-8",
                errors="replace"
            )

    except HTTPError as error:
        body = error.read().decode(
            "utf-8",
            errors="replace"
        )

        print(f"ERROR: HTTP {error.code}")
        print(body[:2000])

        raise

    except URLError as error:
        print(f"ERROR: URL connection failed: {error}")
        raise

    except TimeoutError:
        print(
            f"ERROR: request timed out after {TIMEOUT} seconds"
        )
        raise

    print(f"SUCCESS: received {len(text)} characters")

    return text


def parse_games(text):
    print()
    print("=== STEP 2: PARSE BGG TABLE ===")

    games = []
    seen_ids = set()
    seen_ranks = set()

    table_rows = 0
    valid_rows = 0

    for line_number, line in enumerate(text.splitlines(), start=1):

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

        # -------------------------------------------------
        # Rank
        # Example first cell:
        # [](...) 1
        # -------------------------------------------------

        rank_match = re.search(
            r"(\d+)\s*$",
            cells[0]
        )

        if not rank_match:
            continue

        rank = int(rank_match.group(1))

        if rank < 1 or rank > 100:
            continue

        # -------------------------------------------------
        # Game title / ID
        #
        # Example:
        # [Brass: Birmingham](https://boardgamegeek.com/boardgame/224517/brass-birmingham)
        # -------------------------------------------------

        title_match = re.search(
            r"\[([^\]]+)\]\("
            r"https?://boardgamegeek\.com/boardgame/(\d+)"
            r"(?:/[^)]*)?\)",
            cells[2]
        )

        if not title_match:
            continue

        name = title_match.group(1).strip()
        game_id = int(title_match.group(2))

        # -------------------------------------------------
        # Duplicate protection
        # -------------------------------------------------

        if rank in seen_ranks:
            continue

        if game_id in seen_ids:
            continue

        # -------------------------------------------------
        # Ratings
        #
        # Expected columns:
        #
        # cells[3] = Geek Rating
        # cells[4] = Average Rating
        # cells[5] = Num Voters
        # -------------------------------------------------

        bayesaverage = None
        average = None
        numvoters = None

        if len(cells) > 3:
            value = cells[3].strip()

            if re.fullmatch(r"\d+(?:\.\d+)?", value):
                bayesaverage = value

        if len(cells) > 4:
            value = cells[4].strip()

            if re.fullmatch(r"\d+(?:\.\d+)?", value):
                average = value

        if len(cells) > 5:
            value = cells[5].replace(",", "").strip()

            if re.fullmatch(r"\d+", value):
                numvoters = int(value)

        # -------------------------------------------------
        # Save game
        # -------------------------------------------------

        game = {
            "rank": rank,
            "id": game_id,
            "name": name,
            "bayesaverage": bayesaverage,
            "average": average,
            "numvoters": numvoters,
        }

        games.append(game)

        seen_ranks.add(rank)
        seen_ids.add(game_id)

        valid_rows += 1

        # -------------------------------------------------
        # Diagnostic output
        # -------------------------------------------------

        if len(games) <= 3:
            print(
                f"Game #{rank}: "
                f"{name} | "
                f"Geek={bayesaverage} | "
                f"Average={average} | "
                f"Voters={numvoters}"
            )

        if len(games) >= 100:
            break

    print()
    print(f"Table rows detected: {table_rows}")
    print(f"Valid game rows: {valid_rows}")
    print(f"Unique games: {len(games)}")

    return games


def validate_games(games):
    print()
    print("=== STEP 3: VALIDATE DATA ===")

    if len(games) != 100:
        raise RuntimeError(
            f"Expected exactly 100 games, found {len(games)}"
        )

    print("Count check: OK (100 games)")

    for index, game in enumerate(games):

        expected_rank = index + 1

        if game["rank"] != expected_rank:
            raise RuntimeError(
                f"Invalid rank at index {index}: "
                f"expected {expected_rank}, "
                f"got {game['rank']}"
            )

        if not isinstance(game["id"], int) or game["id"] <= 0:
            raise RuntimeError(
                f"Invalid game ID at rank {game['rank']}"
            )

        if not game["name"]:
            raise RuntimeError(
                f"Missing game name at rank {game['rank']}"
            )

    print("Rank check: OK")
    print("Game ID check: OK")
    print("Game name check: OK")

    ratings_count = sum(
        1
        for game in games
        if game["bayesaverage"] is not None
    )

    averages_count = sum(
        1
        for game in games
        if game["average"] is not None
    )

    voters_count = sum(
        1
        for game in games
        if game["numvoters"] is not None
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

    print("Validation: SUCCESS")


def save_json(games):
    print()
    print("=== STEP 4: SAVE JSON ===")

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

    print(
        f"Saved {len(games)} games to {OUTPUT}"
    )

    print(
        f"File size: "
        f"{__import__('os').path.getsize(OUTPUT)} bytes"
    )


def main():

    print("========================================")
    print("BGG TOP 100 CACHE GENERATOR")
    print("========================================")

    text = fetch_bgg()

    games = parse_games(text)

    validate_games(games)

    save_json(games)

    print()
    print("=== STEP 5: FINAL RESULT ===")

    first = games[0]

    print(
        f"Top game: #{first['rank']} "
        f"{first['name']}"
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

    print()
    print("========================================")
    print("SUCCESS: BGG TOP 100 UPDATED")
    print("========================================")


if __name__ == "__main__":
    main()
