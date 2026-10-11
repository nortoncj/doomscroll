"""Why are jobs (not) matching? Run from the repo root: python3 scripts/diagnose.py
Keys come from SSM and are never printed."""
import collections, os, subprocess, sys

sys.path.insert(0, "src/fetch_jobs")
import filters, sources

f = filters.load_filters("config/filters.json")
EMAIL = os.environ.get("USAJOBS_EMAIL", "contact@chrisnortonjr.com")


def ssm(name):
    return subprocess.check_output(
        ["aws", "ssm", "get-parameter", "--name", f"/doomscroll/{name}", "--with-decryption",
         "--query", "Parameter.Value", "--output", "text"], text=True).strip()


def diagnose(name, jobs):
    hits = [j for j in jobs if f.include.search(j["title"])]
    level_cut = [j for j in hits if f.exclude.search(j["title"])]
    level_ok = [j for j in hits if not f.exclude.search(j["title"])]
    loc_cut = [j for j in level_ok if j["location"] and not f.locations.search(j["location"])]
    passed = len(level_ok) - len(loc_cut)
    print(f"\n== {name}: {len(jobs)} fetched | {len(hits)} keyword hits | "
          f"{len(level_cut)} cut by level | {len(loc_cut)} cut by location | {passed} pass")
    for loc, n in collections.Counter(j["location"] for j in loc_cut).most_common(8):
        print(f"   location cut {n:>3}  {loc}")
    for j in level_cut[:5]:
        print(f"   level cut         {j['title']}")
    misses = collections.Counter(j["title"] for j in jobs if not f.include.search(j["title"]))
    for title, n in misses.most_common(8):
        print(f"   no keyword   {n:>3}  {title}")


for board in f.greenhouse_boards:
    diagnose(f"greenhouse:{board}", sources.parse_greenhouse(sources.fetch_greenhouse(board), board))
for co in f.lever_companies:
    diagnose(f"lever:{co}", sources.parse_lever(sources.fetch_lever(co), co))
diagnose("usajobs", sources.parse_usajobs(sources.fetch_usajobs(ssm("usajobs/api_key"), EMAIL)))
diagnose("adzuna", sources.parse_adzuna(sources.fetch_adzuna(ssm("adzuna/app_id"), ssm("adzuna/app_key"))))