import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("TMDB_API_KEY")
BASE_URL = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p/w500"


def get_movie_details(movie_name):
    try:
        url = f"{BASE_URL}/search/movie"
        params = {
            "api_key": API_KEY,
            "query": movie_name
        }

        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()

        data = response.json()

        if not data["results"]:
            return None

        movie = data["results"][0]

        poster = (
            IMAGE_BASE + movie["poster_path"]
            if movie.get("poster_path")
            else None
        )

        backdrop = (
            IMAGE_BASE + movie["backdrop_path"]
            if movie.get("backdrop_path")
            else None
        )

        return {
            "title": movie.get("title"),
            "rating": movie.get("vote_average"),
            "release_date": movie.get("release_date"),
            "overview": movie.get("overview"),
            "poster": poster,
            "backdrop": backdrop
        }

    except requests.exceptions.RequestException as e:
        print("TMDB API Error:", e)
        return None