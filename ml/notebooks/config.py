from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_DIR / "data"

DATA_AMAZON_BOOKS = DATA_DIR / "AmazonBooks"

AMAZON_BOOKS_TABLE_PATHS = {
    "books":  DATA_AMAZON_BOOKS / "books_data.csv",
    "ratings":  DATA_AMAZON_BOOKS / "books_rating.csv",
#    "users":  DATA_AMAZON_BOOKS / "users.csv",
}