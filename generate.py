import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


URL = "https://r.jina.ai/https://boardgamegeek.com/browse/boardgame?sort=rank"
OUTPUT = "top100.json"


def main():
    print("Fetching BGG through Jina Reader...")

    request = Request(
        URL,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; DnDClub-BGG-Cache/1.0)"
        },
    )

    try:
        with urlopen(request, timeout=60) as response:
            text = response.read().decode("utf-8", errors="replace")

    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        print(f"Jina HTTP error: {error.code}")
        print(body[:2000])
        raise

    except URLError as error:
        print(f"Jina connection error: {error}")
        raise

    print(f"Received {len(text)} characters from Jina")

    pattern = re.compile(
        r"^\s*\|?\s*(\d+)\s*\|\s*"
        r"\[([^\]]+)\]\(https://boardgamegeek\.com/boardgame/(\d+)"
        r"(?:/[^)]*)?\)\s*\|\s*"
        r"([0-9.]+)\s*\|\s*"
        r"([0-9.]+)\s*\|\s*"
        r"([\d,]+)\s*\|",
        re.MULTILINE,
    )

    games = []
    seen_ids = set()
    seen_ranks = set()

    for match in pattern.finditer(text):

        rank = int(match.group(1))
        name = match.group(2).strip()
        game_id = int(match.group(3))

        bayesaverage = match.group(4)
        average = match.group(5)
        numvoters = int(match.group(6).replace(",", ""))

        if rank in seen_ranks:
            continue

        if game_id in seen_ids:
            continue

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

        seen_ranks.add(rank)
        seen_ids.add(game_id)

        if len(games) >= 100:
            break

    games.sort(key=lambda game: game["rank"])

    print(f"Detected {len(games)} games")

    if len(games) < 100:
        print("Could not detect 100 games.")
        print("First 5000 characters received:")
        print(text[:5000])

        raise RuntimeError(
            f"Expected 100 games, found only {len(games)}"
        )

    with open(OUTPUT, "w", encoding="utf-8") as file:
        json.dump(
            games,
            file,
            ensure_ascii=False,
            indent=2,
        )

    print(
        f"Successfully saved {len(games)} games to {OUTPUT}"
    )

    first = games[0]

    print(
        f"Top game: #{first['rank']} {first['name']} "
        f"| Geek Rating: {first['bayesaverage']} "
        f"| Average: {first['average']} "
        f"| Voters: {first['numvoters']}"
    )


if __name__ == "__main__":
    main()
