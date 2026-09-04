import json
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


URL = "https://r.jina.ai/https://boardgamegeek.com/browse/boardgame?sort=rank"
OUTPUT = "top100.json"

MAX_ATTEMPTS = 3
CLIENT_TIMEOUT = 50


def fetch_bgg():
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; DnDClub-BGG-Cache/1.0)",
        "X-Engine": "curl",
        "X-Respond-Timing": "visible-content",
        "X-Timeout": "40",
        "X-Retain-Images": "none",
    }

    last_error = None

    for attempt in range(1, MAX_ATTEMPTS + 1):

        print(f"Jina request attempt {attempt}/{MAX_ATTEMPTS}...")

        request = Request(URL, headers=headers)

        try:
            with urlopen(request, timeout=CLIENT_TIMEOUT) as response:
                data = response.read()

            text = data.decode("utf-8", errors="replace")

            print(f"Jina returned {len(text)} characters")

            return text

        except HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            last_error = f"HTTP {error.code}: {body[:500]}"
            print(last_error)

        except (URLError, TimeoutError) as error:
            last_error = str(error)
            print(f"Jina connection error: {last_error}")

        except Exception as error:
            last_error = repr(error)
            print(f"Unexpected error: {last_error}")

        if attempt < MAX_ATTEMPTS:
            print("Waiting before retry...")
            time.sleep(5)

    raise RuntimeError(
        f"Jina request failed after {MAX_ATTEMPTS} attempts: {last_error}"
    )


def parse_games(text):
    games = []
    seen_ids = set()
    seen_ranks = set()

    for line in text.splitlines():

        line = line.strip()

        if "|" not in line:
            continue

        cells = [
            cell.strip()
            for cell in line.strip("|").split("|")
        ]

        if not cells:
            continue

        rank_match = re.fullmatch(r"\d+", cells[0])

        if not rank_match:
            continue

        rank = int(rank_match.group())

        if rank < 1 or rank > 100:
            continue

        game_match = re.search(
            r"\[([^\]]+)\]\("
            r"https?://boardgamegeek\.com/boardgame/(\d+)"
            r"(?:/[^)]*)?\)",
            line,
        )

        if not game_match:
            continue

        name = game_match.group(1).strip()
        game_id = int(game_match.group(2))

        if game_id in seen_ids or rank in seen_ranks:
            continue

        link_cell_index = None

        for index, cell in enumerate(cells):

            if game_match.group(0) in cell:
                link_cell_index = index
                break

        if link_cell_index is None:
            continue

        following_cells = cells[link_cell_index + 1:]

        numbers = []

        for cell in following_cells:

            value = cell.replace(",", "").strip()

            if re.fullmatch(r"\d+\.\d+", value):
                numbers.append(value)

            elif re.fullmatch(r"\d+", value):
                numbers.append(value)

        bayesaverage = None
        average = None
        numvoters = None

        decimal_numbers = [
            value
            for value in numbers
            if re.fullmatch(r"\d+\.\d+", value)
        ]

        integer_numbers = [
            value
            for value in numbers
            if re.fullmatch(r"\d+", value)
        ]

        if len(decimal_numbers) >= 1:
            bayesaverage = decimal_numbers[0]

        if len(decimal_numbers) >= 2:
            average = decimal_numbers[1]

        if integer_numbers:
            numvoters = int(integer_numbers[0])

        games.append(
            {
                "rank": rank,
                "id": game_id,
                "name": name,
                "bayesaverage": bayesaverage,
                "average": average,
                "numvoters": numvoters,
            }
        )

        seen_ids.add(game_id)
        seen_ranks.add(rank)

    games.sort(key=lambda game: game["rank"])

    return games


def main():

    print("Fetching BGG through Jina Reader...")

    text = fetch_bgg()

    print("Parsing BGG ranking...")

    games = parse_games(text)

    print(f"Detected {len(games)} games")

    if len(games) < 100:

        print("Could not detect 100 games.")

        print("First 8000 characters received:")
        print(text[:8000])

        raise RuntimeError(
            f"Expected 100 games, found only {len(games)}"
        )

    games = games[:100]

    with open(OUTPUT, "w", encoding="utf-8") as file:

        json.dump(
            games,
            file,
            ensure_ascii=False,
            indent=2,
        )

    first = games[0]

    print(
        f"Successfully saved {len(games)} games to {OUTPUT}"
    )

    print(
        f"Top game: #{first['rank']} {first['name']}"
    )

    print(
        f"Geek Rating: {first['bayesaverage']}"
    )

    print(
        f"Average Rating: {first['average']}"
    )

    print(
        f"Voters: {first['numvoters']}"
    )


if __name__ == "__main__":
    main()
