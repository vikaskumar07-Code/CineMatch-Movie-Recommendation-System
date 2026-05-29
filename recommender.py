from sklearn.metrics.pairwise import cosine_similarity
from utils import load_pickle


class MovieRecommender:
    def __init__(self):
        self.df = load_pickle("df.pkl")
        self.indices = load_pickle("indices.pkl")
        self.tfidf = load_pickle("tfidf.pkl")
        self.tfidf_matrix = load_pickle("tfidf_matrix.pkl")

    def recommend(self, title, top_n=10):
        # normalize
        title = title.strip().lower()

        # create fresh lookup from dataframe
        movie_lookup = {
            movie.lower(): idx
            for idx, movie in enumerate(self.df["title"])
        }

        if title not in movie_lookup:
            return []

        idx = movie_lookup[title]

        cosine_scores = cosine_similarity(
            self.tfidf_matrix[idx],
            self.tfidf_matrix
        ).flatten()

        similar_idx = cosine_scores.argsort()[::-1][1:top_n + 1]

        movies = self.df.iloc[similar_idx]["title"].tolist()

        return movies