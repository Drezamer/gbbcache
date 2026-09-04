import json
import re
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


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
    html = response.read().decode("utf-8", errors="replace")

print(html[:5000])
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        print(f"Jina HTTP error: {error.code}")
        print(body[:1000])
        raise
    except URLError as error:
        print(f"Jina connection error: {error}")
        raise

    print(f"Received {len(html)} characters from Jina")

    pattern = re.compile(
        r"\[([^\]]+)\]\(https://boardgamegeek\.com/boardgame/(\d+)(?:/[^)]*)?\)"
    )

    games = []
    seen_ids = set()

    for match in pattern.finditer(html):
        name = match.group(1).strip()
        game_id = int(match.group(2))

        if game_id in seen_ids:
            continue

        seen_ids.add(game_id)

        games.append(
            {
                "rank": len(games) + 1,
                "id": game_id,
                "name": name,
                "bayesaverage": None,
                "average": None,
            }
        )

        if len(games) >= 100:
            break

    print(f"Detected {len(games)} unique games")

    if len(games) < 100:
        print("Could not find 100 games.")
        print("First 5000 characters received from Jina:")
        print(html[:5000])
        raise RuntimeError(
            f"Expected 100 games, found only {len(games)}"
        )

    with open(OUTPUT, "w", encoding="utf-8") as file:
        json.dump(
            games,
            file,
            ensure_ascii=False,
            indent=2
        )

    print(f"Successfully saved {len(games)} games to {OUTPUT}")
    print(f"Top game: #{games[0]['rank']} {games[0]['name']}")


if __name__ == "__main__":
    main()
