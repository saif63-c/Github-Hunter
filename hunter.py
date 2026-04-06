import requests
import json
import csv
import os
import time
import sys
from datetime import datetime, timedelta

# ============== CONFIG ==============
GITHUB_API = "https://api.github.com/search/repositories"
CACHE_FILE = "github_cache.json"
JSON_OUTPUT = "trending_repos.json"
CSV_OUTPUT = "trending_repos.csv"
LOG_FILE = "github_hunter.log"
CACHE_EXPIRY = 3600  # 1 hour cache
RATE_LIMIT_WAIT = 60
MAX_RETRIES = 3
PER_PAGE = 100

# ============== COLORS ==============
class C:
    R = '\033[91m'  # Red
    G = '\033[92m'  # Green
    Y = '\033[93m'  # Yellow
    B = '\033[94m'  # Blue
    M = '\033[95m'  # Magenta
    CY = '\033[96m' # Cyan
    W = '\033[97m'  # White
    BOLD = '\033[1m'
    END = '\033[0m'

# ============== LOGGER ==============
class Logger:
    def __init__(self, log_file):
        self.log_file = log_file

    def log(self, msg, level="INFO"):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] [{level}] {msg}"
        try:
            with open(self.log_file, "a") as f:
                f.write(log_msg + "\n")
        except:
            pass

logger = Logger(LOG_FILE)

# ============== CACHE SYSTEM ==============
class Cache:
    def __init__(self, cache_file, expiry):
        self.cache_file = cache_file
        self.expiry = expiry

    def get(self, key):
        try:
            if not os.path.exists(self.cache_file):
                return None
            with open(self.cache_file, "r") as f:
                data = json.load(f)
            if key in data:
                cached = data[key]
                if time.time() - cached["timestamp"] < self.expiry:
                    logger.log(f"Cache HIT for: {key}")
                    return cached["data"]
                else:
                    logger.log(f"Cache EXPIRED for: {key}")
        except:
            pass
        return None

    def set(self, key, value):
        try:
            data = {}
            if os.path.exists(self.cache_file):
                with open(self.cache_file, "r") as f:
                    data = json.load(f)
            data[key] = {"data": value, "timestamp": time.time()}
            with open(self.cache_file, "w") as f:
                json.dump(data, f)
            logger.log(f"Cache SET for: {key}")
        except:
            pass

cache = Cache(CACHE_FILE, CACHE_EXPIRY)

# ============== BANNER ==============
def banner():
    os.system("clear" if os.name != "nt" else "cls")
    print(f"""{C.CY}{C.BOLD}
╔══════════════════════════════════════════════════════╗
║  ██████╗ ██╗████████╗██╗  ██╗██╗   ██╗██████╗      ║
║ ██╔════╝ ██║╚══██╔══╝██║  ██║██║   ██║██╔══██╗     ║
║ ██║  ███╗██║   ██║   ███████║██║   ██║██████╔╝     ║
║ ██║   ██║██║   ██║   ██╔══██║██║   ██║██╔══██╗     ║
║ ╚██████╔╝██║   ██║   ██║  ██║╚██████╔╝██████╔╝     ║
║  ╚═════╝ ╚═╝   ╚═╝   ╚═╝  ╚═╝ ╚═════╝ ╚═════╝     ║
║                                                      ║
║        🔥 TRENDING REPOS HUNTER v2.0 🔥             ║
║              Created by: Zarvish                     ║
╚══════════════════════════════════════════════════════╝
{C.END}""")

# ============== INTERNET CHECK ==============
def check_internet():
    try:
        requests.get("https://github.com", timeout=5)
        return True
    except:
        print(f"{C.R}[✘] No Internet Connection!{C.END}")
        logger.log("No internet connection", "ERROR")
        return False

# ============== GITHUB TOKEN ==============
def get_token():
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        token_file = os.path.expanduser("~/.github_token")
        if os.path.exists(token_file):
            try:
                with open(token_file, "r") as f:
                    token = f.read().strip()
            except:
                pass
    return token

# ============== API REQUEST WITH RETRY ==============
def api_request(url, params, headers, retries=MAX_RETRIES):
    for attempt in range(retries):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=30)

            # Rate limit check
            remaining = int(response.headers.get("X-RateLimit-Remaining", 1))
            if remaining == 0:
                reset_time = int(response.headers.get("X-RateLimit-Reset", 0))
                wait = max(reset_time - int(time.time()), 0) + 5
                print(f"{C.Y}[⏳] Rate limited! Waiting {wait}s...{C.END}")
                logger.log(f"Rate limited, waiting {wait}s", "WARN")
                time.sleep(wait)
                continue

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 403:
                print(f"{C.Y}[⚠] API Forbidden, retrying in {RATE_LIMIT_WAIT}s...{C.END}")
                time.sleep(RATE_LIMIT_WAIT)
                continue
            elif response.status_code == 422:
                print(f"{C.R}[✘] Invalid query!{C.END}")
                return None
            else:
                print(f"{C.Y}[⚠] Status {response.status_code}, retry {attempt+1}/{retries}{C.END}")
                time.sleep(5)

        except requests.exceptions.Timeout:
            print(f"{C.Y}[⚠] Timeout! Retry {attempt+1}/{retries}{C.END}")
            time.sleep(5)
        except requests.exceptions.ConnectionError:
            print(f"{C.R}[✘] Connection Error! Retry {attempt+1}/{retries}{C.END}")
            time.sleep(10)
        except Exception as e:
            print(f"{C.R}[✘] Error: {e}{C.END}")
            logger.log(f"API Error: {e}", "ERROR")
            time.sleep(5)

    return None

# ============== FETCH REPOS ==============
def fetch_repos(language=None, min_stars=20000, days=30, sort_by="stars"):
    date_from = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    query = f"created:>{date_from} stars:>={min_stars}"
    if language and language.lower() != "all":
        query += f" language:{language}"

    cache_key = f"{query}_{sort_by}"
    cached_data = cache.get(cache_key)
    if cached_data:
        print(f"{C.G}[✓] Loaded from cache!{C.END}")
        return cached_data

    headers = {"Accept": "application/vnd.github.v3+json"}
    token = get_token()
    if token:
        headers["Authorization"] = f"token {token}"
        print(f"{C.G}[✓] Using GitHub Token (Higher rate limit){C.END}")
    else:
        print(f"{C.Y}[⚠] No token - Limited to 10 req/min{C.END}")
        print(f"{C.Y}    Set GITHUB_TOKEN env variable for more{C.END}")

    all_repos = []
    page = 1

    while True:
        params = {
            "q": query,
            "sort": sort_by,
            "order": "desc",
            "per_page": PER_PAGE,
            "page": page
        }

        print(f"{C.CY}[🔍] Fetching page {page}...{C.END}")
        logger.log(f"Fetching page {page} | Query: {query}")

        data = api_request(GITHUB_API, params, headers)

        if not data or "items" not in data:
            break

        items = data["items"]
        if not items:
            break

        for repo in items:
            repo_data = {
                "name": repo["full_name"],
                "description": (repo.get("description") or "No description")[:80],
                "stars": repo["stargazers_count"],
                "forks": repo["forks_count"],
                "language": repo.get("language") or "N/A",
                "owner": repo["owner"]["login"],
                "owner_type": repo["owner"]["type"],
                "url": repo["html_url"],
                "created": repo["created_at"][:10],
                "updated": repo["updated_at"][:10],
                "topics": repo.get("topics", []),
                "license": (repo.get("license") or {}).get("name", "N/A"),
                "open_issues": repo["open_issues_count"],
                "watchers": repo["watchers_count"],
                "size": repo["size"]
            }
            all_repos.append(repo_data)

        total = data.get("total_count", 0)
        if page * PER_PAGE >= total or page * PER_PAGE >= 1000:
            break
        page += 1
        time.sleep(2)  # Be nice to API

    # Cache results
    if all_repos:
        cache.set(cache_key, all_repos)

    return all_repos

# ============== DISPLAY TABLE ==============
def display_table(repos, sort_by="stars"):
    if not repos:
        print(f"{C.R}[✘] No repos found!{C.END}")
        return

    # Sort
    if sort_by == "stars":
        repos.sort(key=lambda x: x["stars"], reverse=True)
    elif sort_by == "forks":
        repos.sort(key=lambda x: x["forks"], reverse=True)
    elif sort_by == "date":
        repos.sort(key=lambda x: x["created"], reverse=True)
    elif sort_by == "name":
        repos.sort(key=lambda x: x["name"].lower())

    print(f"\n{C.G}{C.BOLD}{'='*110}")
    print(f" {'#':<4} {'REPO NAME':<35} {'⭐ STARS':<12} {'🍴 FORKS':<10} {'💻 LANG':<12} {'📅 CREATED':<12} {'👤 OWNER':<15}")
    print(f"{'='*110}{C.END}")

    for i, repo in enumerate(repos, 1):
        stars_str = f"{repo['stars']:,}"
        forks_str = f"{repo['forks']:,}"

        # Color based on stars
        if repo['stars'] >= 50000:
            color = C.R
        elif repo['stars'] >= 30000:
            color = C.Y
        else:
            color = C.G

        print(f" {color}{i:<4} {repo['name']:<35} {stars_str:<12} {forks_str:<10} {repo['language']:<12} {repo['created']:<12} {repo['owner']:<15}{C.END}")

    print(f"{C.G}{C.BOLD}{'='*110}{C.END}")
    print(f"{C.CY} Total: {len(repos)} repos found{C.END}\n")

    # Show details
    for i, repo in enumerate(repos, 1):
        print(f"{C.B}[{i}] {repo['name']}{C.END}")
        print(f"    📝 {repo['description']}")
        print(f"    🔗 {repo['url']}")
        print(f"    📜 License: {repo['license']} | Issues: {repo['open_issues']} | Topics: {', '.join(repo['topics'][:5]) if repo['topics'] else 'None'}")
        print()

# ============== EXPORT JSON ==============
def export_json(repos, filename=JSON_OUTPUT):
    try:
        export_data = {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_repos": len(repos),
            "repos": repos
        }
        with open(filename, "w") as f:
            json.dump(export_data, f, indent=4)
        print(f"{C.G}[✓] JSON saved: {filename}{C.END}")
        logger.log(f"JSON exported: {filename}")
    except Exception as e:
        print(f"{C.R}[✘] JSON export failed: {e}{C.END}")

# ============== EXPORT CSV ==============
def export_csv(repos, filename=CSV_OUTPUT):
    try:
        if not repos:
            return
        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=repos[0].keys())
            writer.writeheader()
            for repo in repos:
                row = repo.copy()
                row["topics"] = ", ".join(row["topics"])
                writer.writerow(row)
        print(f"{C.G}[✓] CSV saved: {filename}{C.END}")
        logger.log(f"CSV exported: {filename}")
    except Exception as e:
        print(f"{C.R}[✘] CSV export failed: {e}{C.END}")

# ============== NOTIFICATION ==============
def check_new_repos(old_repos, new_repos):
    old_names = {r["name"] for r in old_repos}
    new_found = [r for r in new_repos if r["name"] not in old_names]
    if new_found:
        print(f"\n{C.R}{C.BOLD}🚨 NEW TRENDING REPOS FOUND! 🚨{C.END}")
        for repo in new_found:
            print(f"{C.Y}  🆕 {repo['name']} ⭐ {repo['stars']:,} | {repo['language']}{C.END}")
        logger.log(f"New repos found: {len(new_found)}")
    return new_found

# ============== MAIN MENU ==============
def main_menu():
    print(f"""
{C.BOLD}{C.CY}╔══════════════════════════════════╗
║         MAIN MENU                ║
╠══════════════════════════════════╣
║ {C.G}[1]{C.CY} 🔍 Search Trending Repos      ║
║ {C.G}[2]{C.CY} 💻 Search by Language          ║
║ {C.G}[3]{C.CY} ⭐ Custom Star Filter          ║
║ {C.G}[4]{C.CY} 📅 Custom Date Range           ║
║ {C.G}[5]{C.CY} 🔄 Sort Results                ║
║ {C.G}[6]{C.CY} 💾 Export JSON                  ║
║ {C.G}[7]{C.CY} 📊 Export CSV                   ║
║ {C.G}[8]{C.CY} 🔔 Watch Mode (Auto Refresh)   ║
║ {C.G}[9]{C.CY} 🗑️  Clear Cache                 ║
║ {C.G}[0]{C.CY} 🚪 Exit                        ║
╚══════════════════════════════════╝{C.END}
""")

# ============== WATCH MODE ==============
def watch_mode(language=None, min_stars=20000, interval=300):
    print(f"{C.CY}[🔔] Watch Mode ON - Checking every {interval}s{C.END}")
    print(f"{C.Y}     Press Ctrl+C to stop{C.END}")

    old_repos = []
    while True:
        try:
            # Clear cache for fresh results
            if os.path.exists(CACHE_FILE):
                os.remove(CACHE_FILE)

            new_repos = fetch_repos(language, min_stars)
            if new_repos:
                if old_repos:
                    check_new_repos(old_repos, new_repos)
                display_table(new_repos)
                export_json(new_repos, f"watch_{datetime.now().strftime('%H%M%S')}.json")
                old_repos = new_repos

            print(f"{C.Y}[⏳] Next check in {interval}s...{C.END}")
            time.sleep(interval)
        except KeyboardInterrupt:
            print(f"\n{C.G}[✓] Watch Mode stopped{C.END}")
            break

# ============== MAIN ==============
def main():
    banner()

    if not check_internet():
        sys.exit(1)

    # Install requests if not available
    try:
        import requests
    except ImportError:
        os.system("pip install requests -q")
        import requests

    repos = []
    current_sort = "stars"
    min_stars = 20000
    days = 30
    language = None

    while True:
        try:
            main_menu()
            choice = input(f"{C.CY}[?] Select option: {C.END}").strip()

            if choice == "1":
                print(f"\n{C.G}[🔍] Searching: 20k+ stars, last 30 days, all languages{C.END}\n")
                repos = fetch_repos(min_stars=min_stars, days=days)
                if repos:
                    display_table(repos, current_sort)
                    export_json(repos)
                    export_csv(repos)

            elif choice == "2":
                print(f"\n{C.Y}Available: Python, JavaScript, TypeScript, Rust, Go, Java, C++, C, Swift, Kotlin, Ruby, PHP, All{C.END}")
                language = input(f"{C.CY}[?] Language: {C.END}").strip()
                repos = fetch_repos(language=language, min_stars=min_stars, days=days)
                if repos:
                    display_table(repos, current_sort)

            elif choice == "3":
                try:
                    min_stars = int(input(f"{C.CY}[?] Minimum stars (default 20000): {C.END}").strip() or "20000")
                except:
                    min_stars = 20000
                repos = fetch_repos(language=language, min_stars=min_stars, days=days)
                if repos:
                    display_table(repos, current_sort)

            elif choice == "4":
                try:
                    days = int(input(f"{C.CY}[?] Days back (default 30): {C.END}").strip() or "30")
                except:
                    days = 30
                repos = fetch_repos(language=language, min_stars=min_stars, days=days)
                if repos:
                    display_table(repos, current_sort)

            elif choice == "5":
                if not repos:
                    print(f"{C.R}[✘] No data! Search first{C.END}")
                    continue
                print(f"{C.Y}[1] Stars [2] Forks [3] Date [4] Name{C.END}")
                sort_choice = input(f"{C.CY}[?] Sort by: {C.END}").strip()
                sort_map = {"1": "stars", "2": "forks", "3": "date", "4": "name"}
                current_sort = sort_map.get(sort_choice, "stars")
                display_table(repos, current_sort)

            elif choice == "6":
                if repos:
                    fname = input(f"{C.CY}[?] Filename (default {JSON_OUTPUT}): {C.END}").strip() or JSON_OUTPUT
                    export_json(repos, fname)
                else:
                    print(f"{C.R}[✘] No data! Search first{C.END}")

            elif choice == "7":
                if repos:
                    fname = input(f"{C.CY}[?] Filename (default {CSV_OUTPUT}): {C.END}").strip() or CSV_OUTPUT
                    export_csv(repos, fname)
                else:
                    print(f"{C.R}[✘] No data! Search first{C.END}")

            elif choice == "8":
                try:
                    interval = int(input(f"{C.CY}[?] Check interval in seconds (default 300): {C.END}").strip() or "300")
                except:
                    interval = 300
                watch_mode(language, min_stars, interval)

            elif choice == "9":
                if os.path.exists(CACHE_FILE):
                    os.remove(CACHE_FILE)
                    print(f"{C.G}[✓] Cache cleared!{C.END}")
                else:
                    print(f"{C.Y}[⚠] No cache found{C.END}")

            elif choice == "0":
                print(f"{C.G}[✓] Goodbye! 👋{C.END}")
                break

            else:
                print(f"{C.R}[✘] Invalid option!{C.END}")

        except KeyboardInterrupt:
            print(f"\n{C.G}[✓] Goodbye! 👋{C.END}")
            break
        except Exception as e:
            print(f"{C.R}[✘] Error: {e}{C.END}")
            logger.log(f"Main Error: {e}", "ERROR")
            continue

if __name__ == "__main__":
    main()
