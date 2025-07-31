import requests
import json
import datetime
from zoneinfo import ZoneInfo
from auth import config
from auth.tokenrefresh import refresh_token, load_tokens

def load_tokens():
    with open("auth/tokens.json", "r") as f:
        return json.load(f)

def safe_get(url, headers, params=None):
    """Make a GET request; if 401, refresh token and retry once."""
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 401:
        # print("Refreshing token")
        new_tokens = refresh_token()
        if not new_tokens:
            raise Exception("Failed to refresh access token")
        
        tokens = load_tokens()
        headers["Authorization"] = f"Bearer {tokens['access_token']}"
        response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    return response.json()

def get_current_season():
    now = datetime.datetime.now()
    month = now.month
    year = now.year

    if month in [1, 2, 3]:
        season = "winter"
    elif month in [4, 5, 6]:
        season = "spring"
    elif month in [7, 8, 9]:
        season = "summer"
    else:
        season = "fall"

    return season, year

def get_seasonal_anime(season, year, access_token):
    url = f"https://api.myanimelist.net/v2/anime/season/{year}/{season}"
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {
        "limit": 300,
        "fields": "broadcast,num_episodes,status,main_picture",
        "nsfw": True
    }

    seasonal = []
    while url:
        data = safe_get(url, headers, params)
        seasonal.extend(data["data"])
        url = data.get("paging", {}).get("next")

    return seasonal


def get_watching_list(username, access_token):
    url = f"https://api.myanimelist.net/v2/users/{username}/animelist"
    params = {
        "status": "watching",
        "limit": 300,
        "fields": "list_status",
        "nsfw": True
    }
    headers = {"Authorization": f"Bearer {access_token}"}
    data = safe_get(url, headers, params)
    return data["data"]

def get_weekday_index(day):
    order = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]
    return order.index(day.lower()) if day and day.lower() in order else -1

def query_anilist_by_mal_id(mal_id):
    """Query AniList GraphQL API to get airing info by MAL ID."""
    query = '''
    query ($idMal: Int) {
      Media(idMal: $idMal, type: ANIME) {
        episodes
        nextAiringEpisode {
          episode
          airingAt
          timeUntilAiring
        }
      }
    }
    '''
    variables = {"idMal": mal_id}
    response = requests.post("https://graphql.anilist.co", json={"query": query, "variables": variables})
    response.raise_for_status()
    return response.json()["data"]["Media"]

def fetch_anime_data():
    tokens = load_tokens()
    access_token = tokens["access_token"]
    username = config.USERNAME

    JST = ZoneInfo("Asia/Tokyo")
    now = datetime.datetime.now(tz=JST)

    season, year = get_current_season()
    seasonal_anime = get_seasonal_anime(season, year, access_token)
    seasonal_ids = {entry["node"]["id"]: entry["node"] for entry in seasonal_anime}

    watching_list = get_watching_list(username, access_token)
    anime_by_day = [[] for _ in range(7)]

    for entry in watching_list:
        anime_id = entry["node"]["id"]
        if anime_id not in seasonal_ids:
            continue
        anime = seasonal_ids[anime_id]
        title = anime["title"]
        broadcast = anime.get("broadcast", {})
        day = broadcast.get("day_of_the_week")
        weekday_idx = get_weekday_index(day)
        if weekday_idx == -1:
            continue

        watched_eps = entry["list_status"]["num_episodes_watched"]
        mal_eps = anime.get("num_episodes")
        total_eps = "?"
        next_ep = None

        try:
            anilist_info = query_anilist_by_mal_id(anime_id)
            anilist_eps = anilist_info.get("episodes")
            next_ep = anilist_info.get("nextAiringEpisode")

            if (
                isinstance(mal_eps, int) and mal_eps > 0 and
                isinstance(anilist_eps, int) and anilist_eps > 0
            ):
                offset = mal_eps - anilist_eps
                total_eps = anilist_eps + offset
                if next_ep and "episode" in next_ep:
                    next_ep["episode"] += offset
            else:
                total_eps = anilist_eps or mal_eps or "?"

            if next_ep:
                airing_timestamp = next_ep["airingAt"]
                airing_dt = datetime.datetime.fromtimestamp(airing_timestamp, JST)
                time_until_sec = next_ep["timeUntilAiring"]
                next_in_hours = int(time_until_sec // 3600)
            else:
                airing_dt = None
                next_in_hours = None

        except Exception:
            total_eps = mal_eps or "?"
            airing_dt = None
            next_in_hours = None
            next_ep = None

        if next_ep is None:
            status = "GREEN" if (isinstance(total_eps, int) and watched_eps >= total_eps > 0) else "RED"
        else:
            aired_eps = next_ep["episode"] - 1
            status = "GREEN" if watched_eps >= aired_eps else "RED"

        cover_url = None
        if "main_picture" in anime and anime["main_picture"]:
            cover_url = anime["main_picture"].get("medium") or anime["main_picture"].get("large")

        anime_info = {
            "title": title,
            "mal_id": anime_id,
            "watched_eps": watched_eps,
            "total_eps": total_eps,
            "next_in_hours": next_in_hours,
            "status": status,
            "cover_url": cover_url,
            "weekday_idx": weekday_idx,
            "score": entry["list_status"].get("score", 0)
        }

        anime_by_day[weekday_idx].append(anime_info)


    return anime_by_day


if __name__ == "__main__":
    data = fetch_anime_data()
    days = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    for i, day in enumerate(days):
        print(f"Day {i} ({day}):")
        for anime in data[i]:
            print(f"  {anime['title']} - {anime['watched_eps']}/{anime['total_eps']} eps - Next in {anime['next_in_hours']}h - Status: {anime['status']}")
