# notebooks/playground/test_fotmob.py
import requests
import soccerdata as sd
import time
import json

print("="*55)
print("TEST 1 — Direct FotMob API")
print("="*55)

# Correct endpoint for league fixtures
url = "https://www.fotmob.com/api/leagues?id=87&season=2022%2F2023"
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/122.0.0.0 Safari/537.36"
}

print(f"Fetching La Liga 2022/2023 fixtures...")
response = requests.get(url, headers=headers)
print(f"Status: {response.status_code}")

if response.status_code == 200:
    data = response.json()
    print(f"Top level keys: {list(data.keys())}")
    # Try to find matches
    if "matches" in data:
        matches = data["matches"]
        print(f"Matches found: {len(matches)}")
    elif "allMatches" in data:
        print(f"allMatches found")
        print(json.dumps(data["allMatches"][0], indent=2) if data["allMatches"] else "empty")
    else:
        print(f"Keys returned: {list(data.keys())[:10]}")
else:
    print(f"Failed: {response.text[:200]}")

time.sleep(4)

# Also test match details endpoint
print("\nTesting match details endpoint...")
match_url = "https://www.fotmob.com/api/matchDetails?matchId=3609994"
r2 = requests.get(match_url, headers=headers)
print(f"Status: {r2.status_code}")
if r2.status_code == 200:
    d = r2.json()
    print(f"Match detail keys: {list(d.keys())}")
    if "header" in d:
        h = d["header"]
        print(f"Teams: {h.get('teams', [{}])[0].get('name')} vs {h.get('teams', [{}])[1].get('name') if len(h.get('teams',[])) > 1 else 'N/A'}")

time.sleep(4)

print("\n" + "="*55)
print("TEST 2 — soccerdata FotMob")
print("="*55)

try:
    fotmob = sd.FotMob(leagues="ESP-La Liga", seasons="2023")
    print("FotMob initialised")

    matches = fotmob.read_team_match_stats().reset_index()
    print(f"Match stats: {matches.shape}")
    print(f"Columns: {matches.columns.tolist()}")
    print(matches.head(3).to_string())
except Exception as e:
    print(f"soccerdata FotMob failed: {e}")