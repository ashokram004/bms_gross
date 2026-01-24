from urllib.parse import urlparse

def parse_bms_url(url):
    parts = urlparse(url).path.strip("/").split("/")

    city = parts[1].capitalize()
    movie = parts[2].replace("-", " ").title()
    date = parts[-1]

    return {
        "city": city,
        "movie": movie,
        "date": date
    }
