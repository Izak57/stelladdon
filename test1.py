from secrets import token_urlsafe
from fastapi import FastAPI
from stelladdon import StellaMongo, StellAppMaster, FromDB, APIObject, Service, Context
from pydantic import BaseModel, Field
from typing import Annotated, Optional, List
import requests
import json



client = StellaMongo("mongodb://localhost:27017")
db = client.get_database("stelladdon-test")



class User(APIObject):
    id: str = Field(default_factory=lambda: token_urlsafe(16))
    username: str
    email: str
    level: int = 1

    def get_api_data(self, mode):
        if mode == "public":
            return {
                "id": self.id,
                "username": self.username,
                "level": self.level
            }
        
        elif mode == "personal":
            return {
                "id": self.id,
                "username": self.username,
                "email": self.email,
                "level": self.level
            }

UserTable = db.create_table(User, "users", primary_key="id")


class Movie(APIObject):
    id: str = Field(default_factory=lambda: token_urlsafe(16))
    tmdb_id: int
    title: str
    overview: str
    release_date: Optional[str] = None
    poster_path: Optional[str] = None
    backdrop_path: Optional[str] = None
    vote_average: float = 0.0
    vote_count: int = 0
    runtime: Optional[int] = None
    genres: List[str] = []

    def get_api_data(self, mode):
        return {
            "id": self.id,
            "tmdb_id": self.tmdb_id,
            "title": self.title,
            "overview": self.overview,
            "release_date": self.release_date,
            "poster_path": self.poster_path,
            "backdrop_path": self.backdrop_path,
            "vote_average": self.vote_average,
            "vote_count": self.vote_count,
            "runtime": self.runtime,
            "genres": self.genres
        }


class Series(APIObject):
    id: str = Field(default_factory=lambda: token_urlsafe(16))
    tmdb_id: int
    name: str
    overview: str
    first_air_date: Optional[str] = None
    poster_path: Optional[str] = None
    backdrop_path: Optional[str] = None
    vote_average: float = 0.0
    vote_count: int = 0
    number_of_seasons: Optional[int] = None
    number_of_episodes: Optional[int] = None
    genres: List[str] = []

    def get_api_data(self, mode):
        return {
            "id": self.id,
            "tmdb_id": self.tmdb_id,
            "name": self.name,
            "overview": self.overview,
            "first_air_date": self.first_air_date,
            "poster_path": self.poster_path,
            "backdrop_path": self.backdrop_path,
            "vote_average": self.vote_average,
            "vote_count": self.vote_count,
            "number_of_seasons": self.number_of_seasons,
            "number_of_episodes": self.number_of_episodes,
            "genres": self.genres
        }


MovieTable = db.create_table(Movie, "movies", primary_key="id")
SeriesTable = db.create_table(Series, "series", primary_key="id")


class TMDBService:
    def __init__(self, api_key: str = "demo_key"):
        self.api_key = api_key
        self.base_url = "https://api.themoviedb.org/3"
    
    def search_movies(self, query: str, page: int = 1) -> dict:
        """Search for movies on TMDB"""
        url = f"{self.base_url}/search/movie"
        params = {
            "api_key": self.api_key,
            "query": query,
            "page": page
        }
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {"error": str(e), "results": []}
    
    def search_tv(self, query: str, page: int = 1) -> dict:
        """Search for TV series on TMDB"""
        url = f"{self.base_url}/search/tv"
        params = {
            "api_key": self.api_key,
            "query": query,
            "page": page
        }
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {"error": str(e), "results": []}
    
    def get_movie_details(self, movie_id: int) -> dict:
        """Get detailed movie information from TMDB"""
        url = f"{self.base_url}/movie/{movie_id}"
        params = {"api_key": self.api_key}
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {"error": str(e)}
    
    def get_tv_details(self, tv_id: int) -> dict:
        """Get detailed TV series information from TMDB"""
        url = f"{self.base_url}/tv/{tv_id}"
        params = {"api_key": self.api_key}
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {"error": str(e)}


tmdb_service = TMDBService()



fapp = FastAPI()
app = StellAppMaster(fapp)



CheckAdmin = Service("CheckAdmin")

@CheckAdmin.before
async def check_admin(stella: Context, token: str):
    is_admin = token == "admin"
    stella.states["is_admin"] = is_admin

    if not is_admin:
        # raise StellaAPIError("You are not an admin!", status_code=403)
        print("You are not an admin!")


@CheckAdmin.after
async def check_admin_after(stella: Context, response):
    if stella.states.get("is_admin", False):
        print(f"Admin check passed")
    else:
        print(f"Admin check failed")

    print("ADMIN RESP:", response)
    return response



@app.route("GET", "/admin/test/", [CheckAdmin])
async def admlin_test(stella: Context, name: str):
    negation = "not " if not stella.states.get("is_admin", False) else ""
    return f"you are {negation}an admin, {name}!"


@app.route("GET", "/admin/tmdb/search/movies", [CheckAdmin])
async def search_tmdb_movies(stella: Context, query: str, page: int = 1):
    """Search for movies on TMDB"""
    results = tmdb_service.search_movies(query, page)
    return results


@app.route("GET", "/admin/tmdb/search/series", [CheckAdmin])
async def search_tmdb_series(stella: Context, query: str, page: int = 1):
    """Search for TV series on TMDB"""
    results = tmdb_service.search_tv(query, page)
    return results


@app.route("POST", "/admin/movies", [CheckAdmin])
async def add_movie_to_db(stella: Context, tmdb_id: int):
    """Add a movie from TMDB to the local database"""
    # Check if movie already exists
    existing = MovieTable.find_one({"tmdb_id": tmdb_id})
    if existing:
        return {"error": "Movie already exists in database", "movie": existing}
    
    # Get detailed movie info from TMDB
    movie_data = tmdb_service.get_movie_details(tmdb_id)
    if "error" in movie_data:
        return {"error": "Failed to fetch movie details from TMDB"}
    
    # Create movie object
    genres = [genre["name"] for genre in movie_data.get("genres", [])]
    movie = Movie(
        tmdb_id=movie_data["id"],
        title=movie_data.get("title", ""),
        overview=movie_data.get("overview", ""),
        release_date=movie_data.get("release_date"),
        poster_path=movie_data.get("poster_path"),
        backdrop_path=movie_data.get("backdrop_path"),
        vote_average=movie_data.get("vote_average", 0.0),
        vote_count=movie_data.get("vote_count", 0),
        runtime=movie_data.get("runtime"),
        genres=genres
    )
    
    # Insert into database
    MovieTable.insert(movie)
    return {"success": True, "movie": movie}


@app.route("POST", "/admin/series", [CheckAdmin])
async def add_series_to_db(stella: Context, tmdb_id: int):
    """Add a TV series from TMDB to the local database"""
    # Check if series already exists
    existing = SeriesTable.find_one({"tmdb_id": tmdb_id})
    if existing:
        return {"error": "Series already exists in database", "series": existing}
    
    # Get detailed series info from TMDB
    series_data = tmdb_service.get_tv_details(tmdb_id)
    if "error" in series_data:
        return {"error": "Failed to fetch series details from TMDB"}
    
    # Create series object
    genres = [genre["name"] for genre in series_data.get("genres", [])]
    series = Series(
        tmdb_id=series_data["id"],
        name=series_data.get("name", ""),
        overview=series_data.get("overview", ""),
        first_air_date=series_data.get("first_air_date"),
        poster_path=series_data.get("poster_path"),
        backdrop_path=series_data.get("backdrop_path"),
        vote_average=series_data.get("vote_average", 0.0),
        vote_count=series_data.get("vote_count", 0),
        number_of_seasons=series_data.get("number_of_seasons"),
        number_of_episodes=series_data.get("number_of_episodes"),
        genres=genres
    )
    
    # Insert into database
    SeriesTable.insert(series)
    return {"success": True, "series": series}


@app.route("GET", "/admin/movies/search", [CheckAdmin])
async def search_local_movies(stella: Context, query: str):
    """Search for movies in the local database"""
    # Search by title (case-insensitive)
    import re
    pattern = re.compile(query, re.IGNORECASE)
    movies = MovieTable.find({"title": {"$regex": pattern}})
    return {"results": movies}


@app.route("GET", "/admin/series/search", [CheckAdmin])
async def search_local_series(stella: Context, query: str):
    """Search for series in the local database"""
    # Search by name (case-insensitive)
    import re
    pattern = re.compile(query, re.IGNORECASE)
    series = SeriesTable.find({"name": {"$regex": pattern}})
    return {"results": series}


@app.route("GET", "/admin/movies", [CheckAdmin])
async def list_all_movies(stella: Context):
    """List all movies in the local database"""
    movies = MovieTable.find({})
    return {"results": movies}


@app.route("GET", "/admin/series", [CheckAdmin])
async def list_all_series(stella: Context):
    """List all series in the local database"""
    series = SeriesTable.find({})
    return {"results": series}



@app.route("GET", "/users/post/{name}")
async def post_user(name: str):
    user = User(username=name, email=f"{name}@example.com")
    UserTable.insert(user)
    return user


@app.route("GET", "/users/{id}")
async def get_user(id: Annotated[User, FromDB(UserTable)]):
    print(id)
    return id


@app.route("GET", "/users/byname/{username}")
async def get_user_by_name(username: Annotated[User, FromDB(UserTable, multiple=True)]):
    print(username)
    return username


@app.route("GET", "/users")
async def get_user():
    return UserTable.find({})



from uvicorn import run

if __name__ == "__main__":
    run("test1:fapp", host="0.0.0.0", port=5000, reload=True)
