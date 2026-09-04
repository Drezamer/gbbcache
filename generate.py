import json
import re
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup


URL = "https://boardgamegeek.com/browse/boardgame?sort=rank"
OUTPUT = "top100.json"


def main():
    request = Request(
        URL,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; DnDClub-BGG-Cache/1.0)"
        },
    )

    with urlopen(request, timeout=30) as response:
        html = response.read()

    soup = BeautifulSoup(html, "html.parser")

    games = []
    seen_ids = set()

    for row in soup.find_all("tr"):
        cells = row.find_all("td")

        if len(cells) < 5:
            continue

        link = row.find(
            "a",
            href=re.compile(r"^/boardgame/\d+(?:/.*)?$")
        )

        if not link:
            continue

        match = re.search(
            r"/boardgame/(\d+)",
            link.get("href", "")
        )

        if not match:
            continue

        game_id = int(match.group(1))

        if game_id in seen_ids:
            continue

        rank_text = cells[0].get_text(" ", strip=True)
        rank_match = re.search(r"\d+", rank_text)

        if not rank_match:
            continue

        name = link.get_text(" ", strip=True)
        rank = int(rank_match.group())

        geek_rating = cells[3].get_text(" ", strip=True)
        average = cells[4].get_text(" ", strip=True)

        games.append(
            {
                "rank": rank,
                "id": game_id,
                "name": name,
                "bayesaverage": geek_rating,
                "average": average,
            }
        )

        seen_ids.add(game_id)

        if len(games) >= 100:
            break

    if len(games) < 100:
        raise RuntimeError(
            f"Expected 100 games, found only {len(games)}"
        )

    games.sort(key=lambda game: game["rank"])

    with open(OUTPUT, "w", encoding="utf-8") as file:
        json.dump(
            games,
            file,
            ensure_ascii=False,
            indent=2
        )

    print(
        f"Successfully saved {len(games)} games to {OUTPUT}"
    )

    print(
        f"Top game: #{games[0]['rank']} {games[0]['name']}"
    )


if __name__ == "__main__":
    main()
