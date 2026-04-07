# notebooks/playground/test_reus.py
import requests
from bs4 import BeautifulSoup
import time

url = "https://fbref.com/en/comps/12/2022-2023/passing/2022-2023-La-Liga-Stats"

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/122.0.0.0 Safari/537.36"
}

print(f"Fetching {url}...")
response = requests.get(url, headers=headers)
print(f"Status code: {response.status_code}")

if response.status_code == 200:
    soup = BeautifulSoup(response.text, "html.parser")

    # Find all tables on the page
    tables = soup.find_all("table")
    print(f"\nFound {len(tables)} tables on the page")
    for t in tables:
        print(f"  Table id='{t.get('id')}' class='{t.get('class')}'")

    # Check if content is behind JavaScript
    if len(tables) == 0:
        print("\nNo tables found — page likely requires JavaScript to render")
        print("First 2000 chars of response:")
        print(response.text[:2000])
else:
    print(f"Failed with status: {response.status_code}")
    print(response.text[:500])