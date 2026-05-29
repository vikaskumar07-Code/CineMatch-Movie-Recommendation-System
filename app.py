import streamlit as st
import requests
from recommender import MovieRecommender
import time
import re
from html import escape
from concurrent.futures import ThreadPoolExecutor

# ─── PAGE CONFIG ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="CineMatch",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── LOAD MODEL ─────────────────────────────────────────────────────────────
@st.cache_resource
def load_recommender():
    return MovieRecommender()

recommender = load_recommender()

# ─── TMDB POSTER FETCH ───────────────────────────────────────────────────────
from dotenv import load_dotenv
import os

load_dotenv()

TMDB_API_KEY = os.getenv("TMDB_API_KEY")

if "favorites" not in st.session_state:
    st.session_state["favorites"] = []
if "watch_history" not in st.session_state:
    st.session_state["watch_history"] = []


def build_tmdb_queries(movie_name):
    original = movie_name.strip()
    without_year = re.sub(r"\s*\(\d{4}\)\s*", " ", original).strip()
    cleaned = re.sub(r"[^A-Za-z0-9\s]", " ", without_year)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    first_three_words = " ".join(cleaned.split()[:3])

    queries = []
    for query in (original, cleaned, first_three_words):
        if query and query not in queries:
            queries.append(query)
    return queries

def safe_tmdb_fetch(url, params=None, retries=3):

    for attempt in range(retries):

        try:

            r = requests.get(
                url,
                params=params,
                timeout=10,
                headers={
                    "User-Agent": "Mozilla/5.0"
                }
            )

            if r.status_code == 200:
                return r.json()

            elif r.status_code == 429:
                time.sleep(2 ** attempt)
                continue

            elif r.status_code == 404:
                return None

            else:
                return None

        except requests.exceptions.Timeout:

            if attempt < retries - 1:
                time.sleep(1)
                continue

        except requests.exceptions.ConnectionError:
            return None

        except requests.RequestException:
            return None

    return None

def format_tmdb_movie(movie):
    poster_path = movie.get("poster_path")
    poster = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None
    overview = movie.get("overview", "")
    if len(overview) > 180:
        overview = overview[:177].rstrip() + "..."
    rating = movie.get("vote_average", 0)
    year = movie.get("release_date", "")[:4]
    genre_ids = movie.get("genre_ids", [])
    return poster, overview, rating, year, genre_ids


def fetch_movie_data_uncached(movie_name):
    fallback_data = None
    url = "https://api.themoviedb.org/3/search/movie"

    for query in build_tmdb_queries(movie_name):
        params = {
            "api_key": TMDB_API_KEY,
            "query": query,
            "language": "en-US",
        }

        data = safe_tmdb_fetch(url, params=params)
        if not data:
            continue

        results = data.get("results", [])
        if results and fallback_data is None:
            fallback_data = format_tmdb_movie(results[0])

        movie_with_poster = next(
            (movie for movie in results if movie.get("poster_path")),
            None,
        )
        if movie_with_poster:
            return format_tmdb_movie(movie_with_poster)

    return fallback_data or (None, "", 0, "", [])


@st.cache_data(ttl=3600)
def fetch_movie_data_cached(movie_name):
    data = fetch_movie_data_uncached(movie_name)
    if data[0]:
        return data
    raise ValueError("TMDB poster not found; do not cache this failed result.")


def fetch_movie_data(movie_name):
    """Returns (poster_url, overview, rating, year, genre_ids) without caching failed posters."""
    try:
        return fetch_movie_data_cached(movie_name)
    except Exception:
        return fetch_movie_data_uncached(movie_name)


def fetch_all_movies(recommendations):
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(fetch_movie_data, recommendations))
    return results


if "movie_data_cache_cleared" not in st.session_state:
    fetch_movie_data_cached.clear()
    st.session_state.movie_data_cache_cleared = True


@st.cache_data(ttl=1800)
def fetch_tmdb_collection(endpoint):
    url = f"https://api.themoviedb.org/3/{endpoint}"
    data = safe_tmdb_fetch(url, params={"api_key": TMDB_API_KEY})
    return data.get("results", []) if data else []


def format_tmdb_collection_movie(movie):
    poster_path = movie.get("poster_path")
    backdrop_path = movie.get("backdrop_path")
    overview = movie.get("overview", "")
    if len(overview) > 180:
        overview = overview[:177].rstrip() + "..."
    return {
        "id": movie.get("id"),
        "title": movie.get("title") or movie.get("name") or "Untitled",
        "poster": f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None,
        "backdrop": f"https://image.tmdb.org/t/p/w1280{backdrop_path}" if backdrop_path else None,
        "overview": overview,
        "rating": movie.get("vote_average", 0),
        "year": (movie.get("release_date") or "")[:4],
        "genre_ids": movie.get("genre_ids", []),
    }


@st.cache_data(ttl=3600)
def fetch_trending_movies():

    data = fetch_tmdb_collection("movie/popular")

    if not data:
        return []

    movies = []

    for item in data[:10]:

        title = item.get("title", "Unknown")

        poster_path = item.get("poster_path")

        poster = (
            f"https://image.tmdb.org/t/p/w500{poster_path}"
            if poster_path else None
        )

        overview = item.get("overview", "No overview available")

        rating = item.get("vote_average", "N/A")

        year = item.get("release_date", "")[:4]

        movies.append({
            "title": title,
            "poster": poster,
            "overview": overview,
            "rating": rating,
            "year": year,
        })

    return movies
def fetch_top_rated_movies():
    return [format_tmdb_collection_movie(movie) for movie in fetch_tmdb_collection("movie/top_rated")]


def add_favorite(movie_dict):
    if movie_dict not in st.session_state["favorites"]:
        st.session_state["favorites"].append(movie_dict)


def remove_favorite(title):
    st.session_state["favorites"] = [
        movie for movie in st.session_state["favorites"]
        if movie["title"] != title
    ]


def is_favorite(title):
    return any(movie.get("title") == title for movie in st.session_state["favorites"])


def toggle_favorite(movie_dict):
    if is_favorite(movie_dict["title"]):
        remove_favorite(movie_dict["title"])
    else:
        add_favorite(movie_dict)


def set_movie_input(movie_title):
    st.session_state["movie_input"] = movie_title


def rerun_app():
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()


def remember_search(movie_title):
    if movie_title not in st.session_state["watch_history"]:
        st.session_state["watch_history"].insert(0, movie_title)
        st.session_state["watch_history"] = st.session_state["watch_history"][:10]


def render_favorite_button(movie_dict, key_suffix):
    added = is_favorite(movie_dict["title"])
    heart = "♥" if added else "♡"
    color = "#e50914" if added else "#555"
    bg = "rgba(229,9,20,0.15)" if added else "rgba(255,255,255,0.05)"
    
    st.markdown(f"""
    <div style="text-align:center;margin:6px 0 10px;">
        <span style="
            display:inline-block;
            background:{bg};
            color:{color};
            border:1px solid {color};
            border-radius:999px;
            padding:4px 14px;
            font-size:11px;
            font-weight:600;
            letter-spacing:1px;
            cursor:pointer;
        ">{heart} {'ADDED' if added else 'ADD'}</span>
    </div>
    """, unsafe_allow_html=True)
    
    # Invisible button for click functionality
    if st.button(
        f"{'♥ Added' if added else '♡ Add'}",
        key=f"fav_{key_suffix}_{movie_dict['title']}",
        help=f"{'Remove from' if added else 'Add to'} favorites"
    ):
        toggle_favorite(movie_dict)
        rerun_app()


def render_section_heading(title):
    st.markdown(f'<div class="section-heading">{title}</div>', unsafe_allow_html=True)


def render_collection_card(movie, key_suffix="collection"):
    rating_html = f'&#9733; {movie["rating"]:.1f}' if movie.get("rating") else "&#9733; N/A"
    year_html = movie.get("year") or "Year N/A"
    overview_html = escape(movie.get("overview") or "No description available.")
    title = escape(movie.get("title", "Untitled"))

    if movie.get("poster"):
        st.markdown(f"""
        <div style="
            background:#141414;
            border-radius:10px;
            border:1px solid #1f1f1f;
            margin-bottom:16px;
            overflow:hidden;
            transition:transform 0.25s ease,box-shadow 0.25s ease;
        ">
            <div style="width:100%;aspect-ratio:2/3;overflow:hidden;">
                <img src="{movie['poster']}" 
                    style="
                        width:100%;
                        height:100%;
                        object-fit:cover;
                        object-position:center top;
                        display:block;
                    "
                />
            </div>
            <div style="padding:12px 14px 14px;">
                <div style="font-size:13px;font-weight:700;color:#fff;
                            white-space:nowrap;overflow:hidden;
                            text-overflow:ellipsis;margin-bottom:5px;"
                    title="{title}">{title}</div>
                <div style="display:flex;gap:8px;align-items:center;margin-bottom:6px;">
                    <span style="color:#777;font-size:11px;">{year_html}</span>
                    <span style="color:#f5c518;font-weight:600;font-size:11px;">{rating_html}</span>
                </div>
                <p style="font-size:11px;color:#aaa;line-height:1.5;margin:0;
                        display:-webkit-box;-webkit-line-clamp:3;
                        -webkit-box-orient:vertical;overflow:hidden;">{overview_html}</p>
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div class="movie-card" style="background:#141414;border-radius:10px;
                    border:1px solid #1f1f1f;margin-bottom:16px;
                    overflow:hidden;transition:transform 0.25s ease,box-shadow 0.25s ease;">
            <div class="no-poster-art" style="min-height:300px;height:300px;
                        background:linear-gradient(160deg,#1a0000,#0d0d0d);
                        display:flex;flex-direction:column;
                        align-items:center;justify-content:center;gap:8px;">
                <span style="font-size:40px;">&#127916;</span>
                <span style="font-size:10px;letter-spacing:2px;color:#888;
                             text-transform:uppercase;font-weight:600;">No Poster</span>
            </div>
            <div class="movie-info-card" style="padding:12px 14px 14px;">
                <div class="no-poster-title" style="font-size:13px;font-weight:700;color:#fff;
                            white-space:nowrap;overflow:hidden;
                            text-overflow:ellipsis;margin-bottom:5px;" title="{title}">{title}</div>
                <div style="display:flex;gap:8px;align-items:center;margin-bottom:6px;">
                    <span style="color:#777;font-size:11px;">{year_html}</span>
                    <span style="color:#f5c518;font-weight:600;font-size:11px;">{rating_html}</span>
                </div>
                <p style="font-size:11px;color:#aaa;line-height:1.5;margin:0;
                          display:-webkit-box;-webkit-line-clamp:3;
                          -webkit-box-orient:vertical;overflow:hidden;">{overview_html}</p>
            </div>
        </div>
        """, unsafe_allow_html=True)
    render_favorite_button(movie, key_suffix)


def render_movie_grid(title, movies, limit=10, columns=5):
    render_section_heading(title)
    movies = movies[:limit]
    for row_start in range(0, len(movies), columns):
        cols = st.columns(columns)
        for col, movie in zip(cols, movies[row_start:row_start + columns]):
            with col:
                render_collection_card(movie, f"grid_{title}_{row_start}_{movie.get('id') or movie.get('title')}")


def render_hero_carousel(movies):
    cards = []
    for movie in movies[:5]:
        title = escape(movie.get("title", "Untitled"))
        overview = escape(movie.get("overview") or "No description available.")
        rating = f'{movie["rating"]:.1f}' if movie.get("rating") else "N/A"
        backdrop = movie.get("backdrop") or movie.get("poster") or ""
        cards.append(
            f'<div class="carousel-card" style="background-image:linear-gradient(rgba(0,0,0,0.1),rgba(0,0,0,0.15)),url(\'{backdrop}\');">'
            f'<div class="carousel-rating">&#9733; {rating}</div>'
            f'<div class="carousel-overlay">'
            f'<div class="carousel-title">{title}</div>'
            f'<div class="carousel-overview">{overview}</div>'
            f'<div class="carousel-fav-visual">Add to Favorites &#9829;</div>'
            f'</div></div>'
        )
    st.markdown('<div class="hero-carousel">' + ''.join(cards) + '</div>', unsafe_allow_html=True)

    fav_cols = st.columns(min(5, max(1, len(movies[:5]))))
    for col, movie in zip(fav_cols, movies[:5]):
        with col:
            render_favorite_button(movie, f"hero_{movie.get('id') or movie.get('title')}")


def render_watch_history():
    render_section_heading("&#128338; RECENTLY SEARCHED")
    history = st.session_state.get("watch_history", [])[:5]
    if history:
        pills = "".join(f'<span class="history-pill">{escape(item)}</span>' for item in history)
        st.markdown(f'<div class="history-row">{pills}</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="empty-state">No recent searches yet</div>', unsafe_allow_html=True)


def render_favorites():
    render_section_heading("&#9829; MY FAVORITES")
    favorites = st.session_state.get("favorites", [])
    if not favorites:
        st.markdown('<div class="empty-state">No favorites yet - click \u2665 on any movie</div>', unsafe_allow_html=True)
        return

    cols = st.columns(min(5, len(favorites)))
    for col, movie in zip(cols, favorites):
        with col:
            if st.button("X", key=f"remove_{movie.get('id') or movie.get('title')}"):
                remove_favorite(movie["title"])
                rerun_app()
            render_collection_card(movie, f"favorites_{movie.get('id') or movie.get('title')}")
# ─── PREMIUM CSS ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Inter:wght@300;400;500;600&display=swap');

* { box-sizing: border-box; margin: 0; padding: 0; }

html, body, [data-testid="stAppViewContainer"] {
    background: #0a0a0a !important;
    color: #e8e8e8 !important;
    font-family: 'Inter', sans-serif;
}

[data-testid="stSidebar"] {
    background: #111111 !important;
    border-right: 1px solid #1f1f1f;
}
[data-testid="stSidebar"] * { color: #ccc !important; }

.hero {
    background: linear-gradient(135deg, #0a0a0a 0%, #1a0000 50%, #0a0a0a 100%);
    border-bottom: 1px solid #1f1f1f;
    padding: 48px 0 36px;
    text-align: center;
    position: relative;
    overflow: hidden;
}
.hero::before {
    content: '';
    position: absolute;
    top: -40px; left: 50%; transform: translateX(-50%);
    width: 600px; height: 200px;
    background: radial-gradient(ellipse, rgba(229,9,20,0.18) 0%, transparent 70%);
    pointer-events: none;
}
.hero-title {
    font-family: 'Bebas Neue', sans-serif;
    font-size: clamp(48px, 8vw, 96px);
    letter-spacing: 6px;
    color: #fff;
    line-height: 1;
    text-shadow: 0 0 60px rgba(229,9,20,0.4);
}
.hero-title span { color: #e50914; }
.hero-sub {
    margin-top: 10px;
    font-size: 14px;
    letter-spacing: 3px;
    text-transform: uppercase;
    color: #666;
    font-weight: 300;
}
            


.stButton > button {
    background: #e50914 !important;
    color: #fff !important;
    border: none !important;
    border-radius: 6px !important;
    font-family: 'Inter', sans-serif !important;
    font-weight: 600 !important;
    font-size: 14px !important;
    letter-spacing: 1.5px !important;
    text-transform: uppercase !important;
    padding: 14px 0 !important;
    width: 100% !important;
    transition: background 0.2s, transform 0.1s, box-shadow 0.2s !important;
    box-shadow: 0 4px 20px rgba(229,9,20,0.3) !important;
}
.stButton > button:hover {
    background: #ff1a1a !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 6px 28px rgba(229,9,20,0.45) !important;
}
.stButton > button:active {
    transform: translateY(0) !important;
}

.section-heading {
    font-family: 'Inter', sans-serif;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 3px;
    text-transform: uppercase;
    color: #e50914;
    margin: 36px 0 20px;
    display: flex;
    align-items: center;
    gap: 12px;
}
.section-heading::after {
    content: '';
    flex: 1;
    height: 1px;
    background: linear-gradient(90deg, #2a0000, transparent);
}

.sidebar-label {
    font-size: 10px;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: #444 !important;
    font-weight: 600;
    margin-bottom: 4px;
}

/* Poster full width fix */
[data-testid="stImage"] {
    overflow: hidden;
    border-radius: 10px 10px 0 0;
    width: 100% !important;
    height: 220px !important;
    padding: 0 !important;
    margin: 0 !important;
}
[data-testid="stImage"] img {
    width: 100% !important;
    height: 220px !important;
    object-fit: cover !important;
    object-position: center top !important;
    display: block !important;
    border-radius: 10px 10px 0 0 !important;
    margin: 0 !important;
    padding: 0 !important;
}

[data-testid="stImageContainer"] {
    width: 100% !important;
    padding: 0 !important;
    margin: 0 !important;
}
[data-testid="column"] {
    padding-left: 3px !important;
    padding-right: 3px !important;
}

.stTextInput input {
    background: #1a1a1a !important;
    color: #fff !important;
    border: 1px solid #333 !important;
    border-radius: 6px !important;
    caret-color: #e50914 !important;
}
.stTextInput input:focus {
    border-color: #e50914 !important;
    box-shadow: 0 0 0 1px #e50914 !important;
}
.stTextInput input::placeholder { color: #777 !important; }

[data-testid="column"]:has(.movie-card) {
    transition: transform 0.25s ease, box-shadow 0.25s ease;
    border-radius: 10px;
}
[data-testid="column"]:has(.movie-card) {
    transition: transform 0.25s ease, box-shadow 0.25s ease;
    border-radius: 10px;
    cursor: pointer;
}
[data-testid="column"]:has(.movie-card):hover {
    transform: translateY(-6px) !important;
    box-shadow: 0 8px 30px rgba(229,9,20,0.45) !important;
    z-index: 10 !important;
}
[data-testid="column"]:has(.movie-card):hover [data-testid="stImage"] img {
    transform: scale(1.04);
}
[data-testid="stImage"] {
    height: 300px;
    background: #141414;
}
[data-testid="stImage"] img {
    height: 300px !important;
    width: 100% !important;
    object-fit: cover !important;
}
.movie-card {
    min-height: 430px;
}
.movie-info-card {
    min-height: 130px;
}
.no-poster-art {
    height: 300px !important;
    min-height: 300px !important;
}
.no-poster-title {
    color: #fff !important;
    font-weight: 700 !important;
}

/* Sidebar collapsed toggle button */
[data-testid="collapsedControl"] {
    display: flex !important;
    visibility: visible !important;
    opacity: 1 !important;
    background: #e50914 !important;
    border-radius: 0 8px 8px 0 !important;
    color: #fff !important;
    border: none !important;
    padding: 12px 6px !important;
    transition: background 0.2s ease !important;
}
[data-testid="collapsedControl"]:hover {
    background: #ff1a1a !important;
    box-shadow: 2px 0 15px rgba(229,9,20,0.5) !important;
}
[data-testid="collapsedControl"] svg {
    fill: #fff !important;
    color: #fff !important;
}

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: #0a0a0a; }
::-webkit-scrollbar-thumb { background: #2a2a2a; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #e50914; }

#MainMenu, footer, header { visibility: hidden; }
[data-testid="stToolbar"] { display: none; }
.block-container { padding: 0 2rem 3rem !important; max-width: 100% !important; }
[data-testid="stImage"] {
    width: 100% !important;
    display: block !important;
    padding: 0 !important;
    margin: 0 !important;
}
[data-testid="stImage"] img {
    width: 100% !important;
    min-width: 100% !important;
    display: block !important;
    object-fit: cover !important;
    margin: 0 !important;
    padding: 0 !important;
    border-radius: 10px 10px 0 0 !important;
}
[data-testid="stImageContainer"] {
    width: 100% !important;
    padding: 0 !important;
    margin: 0 !important;
}
[data-testid="column"] {
    padding-left: 4px !important;
    padding-right: 4px !important;
}
button[title="View fullscreen"] {
    display: none !important;
    visibility: hidden !important;
    opacity: 0 !important;
}
[data-testid="stImageContainer"] button {
    display: none !important;
    visibility: hidden !important;
}
[data-testid="stImage"] button {
    display: none !important;
}
[data-testid="stSpinner"] {
    color: #e50914 !important;
}
[data-testid="stSpinner"] p {
    color: #aaa !important;
    font-size: 14px !important;
    letter-spacing: 1px !important;
}
/* Hide Streamlit bottom status bar */
[data-testid="stStatusWidget"] {
    display: none !important;
    visibility: hidden !important;
    opacity: 0 !important;
}
.stStatusWidget {
    display: none !important;
}
iframe[title="streamlit_status_widget"] {
    display: none !important;
}

footer[class*="status"] {
    display: none !important;
}.hero-carousel {
    display: flex;
    overflow-x: auto;
    gap: 16px;
    padding: 16px 0;
    scrollbar-width: none;
}
.hero-carousel::-webkit-scrollbar { display: none; }
.carousel-card {
    min-width: 340px;
    height: 200px;
    border-radius: 12px;
    position: relative;
    overflow: hidden;
    flex-shrink: 0;
    cursor: pointer;
    transition: transform 0.25s ease;
    background-size: cover;
    background-position: center;
}
.carousel-card:hover { transform: scale(1.03); }
.carousel-overlay {
    position: absolute;
    bottom: 0; left: 0; right: 0;
    background: linear-gradient(transparent, rgba(0,0,0,0.9));
    padding: 16px;
}
.carousel-title {
    color: #fff;
    font-size: 20px;
    font-weight: 700;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.carousel-overview {
    color: #aaa;
    font-size: 12px;
    line-height: 1.4;
    margin-top: 6px;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
}
.carousel-rating {
    position: absolute;
    top: 10px;
    right: 10px;
    color: #f5c518;
    background: rgba(0,0,0,0.75);
    border: 1px solid rgba(245,197,24,0.35);
    border-radius: 999px;
    padding: 4px 8px;
    font-size: 11px;
    font-weight: 700;
}
.carousel-fav-visual {
    display: inline-block;
    margin-top: 10px;
    background: #e50914;
    color: #fff;
    border-radius: 5px;
    padding: 6px 10px;
    font-size: 11px;
    font-weight: 700;
}
.history-row {
    display: flex;
    gap: 10px;
    overflow-x: auto;
    padding: 2px 0 18px;
}
.history-pill {
    color: #ddd;
    border: 1px solid #2a2a2a;
    background: #111;
    border-radius: 999px;
    padding: 8px 12px;
    font-size: 12px;
    white-space: nowrap;
}
.empty-state {
    color: #777;
    font-size: 13px;
    padding: 4px 0 18px;
}
</style>
""", unsafe_allow_html=True)


# ─── SIDEBAR ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style='padding: 20px 0 24px; text-align: center; border-bottom: 1px solid #1f1f1f; margin-bottom: 24px;'>
        <div style='font-family: Bebas Neue, sans-serif; font-size: 28px; letter-spacing: 4px; color: #e50914;'>CINE<span style="color:#fff">MATCH</span></div>
        <div style='font-size: 10px; letter-spacing: 2px; color: #333; margin-top: 4px; text-transform: uppercase;'>AI Recommendation Engine</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="sidebar-label">Results</div>', unsafe_allow_html=True)
    num_results = st.slider("", min_value=5, max_value=20, value=10, step=5, label_visibility="collapsed")

    st.markdown('<div class="sidebar-label" style="margin-top:20px;">Columns</div>', unsafe_allow_html=True)
    num_cols = st.select_slider("", options=[3, 4, 5], value=5, label_visibility="collapsed")

    st.markdown("""
    <div style='margin-top: 40px; padding: 16px; background: #0d0d0d; border-radius: 8px; border: 1px solid #1a1a1a;'>
        <div style='font-size: 10px; letter-spacing: 2px; text-transform: uppercase; color: #333; margin-bottom: 8px;'>About</div>
        <div style='font-size: 12px; color: #444; line-height: 1.6;'>Content-based filtering using TF-IDF & cosine similarity on 45,000+ movies.</div>
    </div>
    """, unsafe_allow_html=True)


# ─── HERO BANNER ─────────────────────────────────────────────────────────────
st.markdown("""
<div class="hero">
    <div class="hero-title">CINE<span>MATCH</span></div>
    <div class="hero-sub">AI · Powered · Movie · Discovery</div>
</div>
""", unsafe_allow_html=True)


trending_movies = fetch_trending_movies()
top_rated_movies = fetch_top_rated_movies()

if trending_movies and len(trending_movies) > 0:
    render_hero_carousel(trending_movies)
else:
    st.markdown("""
    <div style="
        height:220px;
        border-radius:12px;
        background:linear-gradient(135deg,#111,#1a0000);
        display:flex;
        align-items:center;
        justify-content:center;
        margin-top:20px;
        margin-bottom:20px;
        border:1px solid #1f1f1f;
        color:#777;
        font-size:18px;
        letter-spacing:2px;
    ">
        🎬 Trending Movies Unavailable
    </div>
    """, unsafe_allow_html=True)
# ─── MAIN CONTENT ────────────────────────────────────────────────────────────
st.markdown("<div style='height:32px'></div>", unsafe_allow_html=True)

movie_list = sorted(recommender.df["title"].tolist())

col_search, col_btn = st.columns([5, 1])
with col_search:
    selected_movie = st.text_input(
        "CHOOSE A MOVIE",
        placeholder="Type a movie name... e.g. Jumanji, Avatar, Inception",
        key="movie_input"
    )
with col_btn:
    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
    search_clicked = st.button("▶  Find", use_container_width=True)



typed = st.session_state.get("movie_input", "")
if typed and len(typed) >= 2:
    suggestions = list(dict.fromkeys([
    movie for movie in movie_list
    if typed.lower() in movie.lower()
]))[:5]

    for idx, suggestion in enumerate(suggestions):
        st.button(
            suggestion,
            key=f"sug_{idx}_{suggestion}",
            on_click=set_movie_input,
            args=(suggestion,),
        )
# ─── RESULTS ─────────────────────────────────────────────────────────────────
if search_clicked:
    if not selected_movie:
        st.warning("Please type a movie name first!")
        st.stop()

    # Exact match pehle
    matched = [m for m in movie_list if selected_movie.lower() == m.lower()]

    if not matched:
        matched = [m for m in movie_list if selected_movie.lower() in m.lower()]

    if not matched:
        st.error(f"'{selected_movie}' not found. Please check the spelling!")
        st.stop()

    selected_movie = matched[0]
    remember_search(selected_movie)
    recommendations = recommender.recommend(selected_movie)[:num_results]

    if not recommendations:
        st.error("Movie not found in database.")
        st.stop()

    st.markdown(f"""
    <div class="section-heading">
        Recommended because you liked &nbsp;<em style="color:#fff">{selected_movie}</em>
    </div>
    """, unsafe_allow_html=True)

    # ── Fetch data (cached) ──
    if (
        "last_movie" in st.session_state
        and "last_results" in st.session_state
        and st.session_state["last_movie"] == selected_movie
    ):
        movie_data = st.session_state["last_results"]
    else:
        movie_data = []
        with st.spinner("\U0001F3AC Finding the best matches for you..."):
            results = fetch_all_movies(recommendations)
            for movie, (poster, overview, rating, year, genre_ids) in zip(recommendations, results):
                movie_data.append({
                    "title":    movie,
                    "poster":   poster,
                    "overview": overview,
                    "rating":   rating,
                    "year":     year,
                })
        st.session_state["last_movie"] = selected_movie
        st.session_state["last_results"] = movie_data

    
    # ── Render grid ──
    rows = [movie_data[i:i + num_cols] for i in range(0, len(movie_data), num_cols)]

    for row in rows:
        cols = st.columns(num_cols)
        for col, m in zip(cols, row):
            with col:
                rating_html  = f'&#9733; {m["rating"]:.1f}' if m["rating"] else "&#9733; N/A"
                year_html    = m["year"] if m["year"] else "Year N/A"
                overview_html = m["overview"] if m["overview"] else "No description available."

                if m["poster"] is not None:
                    st.markdown(f"""
                    <div style="
                        background:#141414;
                        border-radius:10px;
                        border:1px solid #1f1f1f;
                        margin-bottom:16px;
                        overflow:hidden;
                    ">
                        <div style="width:100%;aspect-ratio:2/3;overflow:hidden;">
                            <img src="{m['poster']}" 
                                style="
                                    width:100%;
                                    height:100%;
                                    object-fit:cover;
                                    object-position:center top;
                                    display:block;
                                "
                            />
                        </div>
                        <div style="padding:12px 14px 14px;">
                            <div style="font-size:13px;font-weight:700;color:#fff;
                                        white-space:nowrap;overflow:hidden;
                                        text-overflow:ellipsis;margin-bottom:5px;"
                                title="{m['title']}">{m['title']}</div>
                            <div style="display:flex;gap:8px;align-items:center;margin-bottom:6px;">
                                <span style="color:#777;font-size:11px;">{year_html}</span>
                                <span style="color:#f5c518;font-weight:600;font-size:11px;">{rating_html}</span>
                            </div>
                            <p style="font-size:11px;color:#aaa;line-height:1.5;margin:0;
                                    display:-webkit-box;-webkit-line-clamp:3;
                                    -webkit-box-orient:vertical;overflow:hidden;">{overview_html}</p>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                else:
                    st.markdown(f"""
                    <div style="
                        background:#141414;
                        border-radius:10px;
                        border:1px solid #1f1f1f;
                        margin-bottom:16px;
                        overflow:hidden;
                    ">
                        <div style="width:100%;aspect-ratio:2/3;
                                    background:linear-gradient(160deg,#1a0000,#0d0d0d);
                                    display:flex;flex-direction:column;
                                    align-items:center;justify-content:center;gap:8px;">
                            <span style="font-size:40px;">🎬</span>
                            <span style="font-size:10px;letter-spacing:2px;color:#555;
                                        text-transform:uppercase;font-weight:600;">No Poster</span>
                        </div>
                        <div style="padding:12px 14px 14px;">
                            <div style="font-size:13px;font-weight:700;color:#fff;
                                        white-space:nowrap;overflow:hidden;
                                        text-overflow:ellipsis;margin-bottom:5px;"
                                title="{m['title']}">{m['title']}</div>
                            <div style="display:flex;gap:8px;align-items:center;margin-bottom:6px;">
                                <span style="color:#777;font-size:11px;">{year_html}</span>
                                <span style="color:#f5c518;font-weight:600;font-size:11px;">{rating_html}</span>
                            </div>
                            <p style="font-size:11px;color:#aaa;line-height:1.5;margin:0;
                                    display:-webkit-box;-webkit-line-clamp:3;
                                    -webkit-box-orient:vertical;overflow:hidden;">{overview_html}</p>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

render_watch_history()
if trending_movies:
    render_movie_grid("&#128293; TRENDING THIS WEEK", trending_movies, limit=14, columns=7)

if top_rated_movies:
    render_movie_grid("&#11088; TOP RATED ALL TIME", top_rated_movies, limit=14, columns=7)
render_favorites()