#!/usr/bin/env python3
"""YouFresh server: a long-form-only feed of your YouTube subscriptions for the YouFresh TV app.

Folders (under YOUFRESH_DIR, default /youfresh):
  takeout/  drop a Google Takeout .zip (or subscriptions.csv) here to import your subscriptions
  cookies/  drop a logged-in youtube.com cookies.txt here to sync your YouTube watch history
  data/     YouFresh's own state (channels, watched list, cache)

HTTP (default port 8099):
  /                 channel manager web page
  /feed.json        channels sorted by latest upload, newest videos first (used by the TV app)
  /api/channels     list/add/edit/remove channels
  /api/status       takeout imports, watch-history and subscriptions sync status
  /api/subscriptions  nightly YouTube subscriptions sync state (?sync=1 runs it now)
  /refresh          re-pull all feeds now (?wait=1 to block until done)
  /health
"""
import json, os, threading, time, logging
import urllib.request, urllib.error
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

BASE_DIR = os.environ.get("YOUFRESH_DIR", "/youfresh")
DATA = os.environ.get("DATA_DIR", os.path.join(BASE_DIR, "data"))
TAKEOUT = os.environ.get("TAKEOUT_DIR", os.path.join(BASE_DIR, "takeout"))
COOKIES = os.environ.get("COOKIES_DIR", os.path.join(BASE_DIR, "cookies"))
for _d in (DATA, TAKEOUT, COOKIES):
    try:
        os.makedirs(_d, exist_ok=True)
    except OSError:
        pass  # read-only mounts are fine
ROSTER = os.path.join(DATA, "roster.json")
CACHE = os.path.join(DATA, "feed.json")
PORT = int(os.environ.get("PORT", "8099"))
INTERVAL = int(os.environ.get("REFRESH_MINUTES", "30")) * 60
PER_CHANNEL = int(os.environ.get("VIDEOS_PER_CHANNEL", "15"))
# Videos kept per channel across refreshes (older ones roll off once there are more than this)
KEEP_PER_CHANNEL = int(os.environ.get("KEEP_PER_CHANNEL", "30"))
NS = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015",
      "m": "http://search.yahoo.com/mrss/"}

DURS = os.path.join(DATA, "durations.json")   # {videoId: seconds}, filled in the background
WATCHED = os.path.join(DATA, "watched.json")  # {videoId: iso time}, set from the TV app
import re as _re
LEN_RE = _re.compile(r'"lengthSeconds":"(\d+)"')

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("youfresh")
state = {"feed": None, "roster_mtime": 0, "lock": threading.Lock()}
META_LOCK = threading.Lock()


def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def _save(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f)
    os.replace(tmp, path)


durations = _load(DURS)
watched = _load(WATCHED)


def fetch_duration(vid):
    req = urllib.request.Request("https://www.youtube.com/watch?v=" + vid,
                                 headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "en-US"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            m = LEN_RE.search(r.read().decode("utf-8", "replace"))
        return vid, int(m.group(1)) if m else None
    except Exception:
        return vid, None


def duration_worker():
    """Fill in video lengths for any feed videos we haven't measured yet, a few at a time."""
    while True:
        try:
            feed = state["feed"] or {}
            todo = [v["id"] for c in feed.get("channels", []) for v in c.get("videos", [])
                    if v["id"] not in durations][:40]
            if todo:
                with ThreadPoolExecutor(max_workers=4) as ex:
                    got = list(ex.map(fetch_duration, todo))
                with META_LOCK:
                    for vid, secs in got:
                        if secs is not None:
                            durations[vid] = secs
                    _save(DURS, durations)
                if not any(s is not None for _, s in got):
                    time.sleep(300)  # YouTube refusing; back off
                continue
            if fill_channel_names():
                continue
        except Exception:
            log.exception("duration worker")
        time.sleep(60)


def enriched_feed():
    feed = state["feed"]
    if feed is None:
        return None
    out = dict(feed)
    out["channels"] = [{**c, "videos": [{**v, "duration": durations.get(v["id"], 0),
                                         "watched": v["id"] in watched} for v in c["videos"]]}
                       for c in feed["channels"]]
    out["lists"] = account_lists(feed)
    return out


def account_lists(feed):
    """History and Watch Later rows for each cookies account, as feed-style videos."""
    known = {v["id"]: (c["title"], v) for c in feed.get("channels", []) for v in c["videos"]}
    accounts = sorted(n for n in lists if os.path.exists(os.path.join(COOKIES, n + ".txt"))
                      or os.path.exists(os.path.join(COOKIES, "youtube-" + n + ".txt")))
    out = []
    for name in accounts:
        suffix = f"  ·  {name}" if len(accounts) > 1 else ""
        for key, title in (("history", "History"), ("watchLater", "Watch Later")):
            items = lists[name].get(key)
            if not items:
                continue
            vids = []
            for it in items:
                vid = it["id"]
                chan, fv = known.get(vid, (None, {}))
                vids.append({"id": vid, "title": it["title"] or fv.get("title", ""),
                             "channel": it.get("channel") or chan or vchannels.get(vid, ""),
                             "published": fv.get("published", ""),
                             "thumb": f"https://i.ytimg.com/vi/{vid}/hq720.jpg",
                             "thumbFallback": f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg",
                             "url": f"https://www.youtube.com/watch?v={vid}",
                             "duration": durations.get(vid, 0), "watched": vid in watched})
            out.append({"key": key, "account": name, "title": title + suffix,
                        "updated": lists[name].get(key + "At"), "videos": vids})
    return out


def fetch_channel_name(vid):
    url = "https://www.youtube.com/oembed?format=json&url=https://www.youtube.com/watch?v=" + vid
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "YouFresh/1.0"}),
                                    timeout=15) as r:
            return vid, json.load(r).get("author_name") or ""
    except urllib.error.HTTPError as e:
        return vid, "" if e.code in (401, 403, 404) else None  # private/removed: don't retry forever
    except Exception:
        return vid, None


def fill_channel_names():
    """History entries from yt-dlp have no channel name; look them up once each (oEmbed)."""
    feed_ids = {v["id"] for c in (state["feed"] or {}).get("channels", []) for v in c["videos"]}
    todo = [it["id"] for a in list(lists.values()) for it in a.get("history", [])
            if not it.get("channel") and it["id"] not in vchannels and it["id"] not in feed_ids][:30]
    if not todo:
        return False
    with ThreadPoolExecutor(max_workers=4) as ex:
        got = list(ex.map(fetch_channel_name, todo))
    with META_LOCK:
        for vid, name in got:
            if name is not None:
                vchannels[vid] = name
        _save(VCHANNELS, vchannels)
    return any(n is not None for _, n in got)


def set_watched(vid, on):
    if not _re.fullmatch(r"[0-9A-Za-z_-]{11}", vid or ""):
        return 400, {"error": "bad video id"}
    with META_LOCK:
        if on:
            watched[vid] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            overrides.pop(vid, None)
        else:
            watched.pop(vid, None)
            overrides[vid] = "unwatched"  # don't let the YouTube history sync re-mark it
        _save(WATCHED, watched)
        _save(OVERRIDES, overrides)
    return 200, {"ok": True, "watched": on}


# --- YouTube watch history sync ---------------------------------------------------------
# One Netscape-format cookies.txt per YouTube account in the cookies/ folder (any name ending
# in .txt; the file name labels the account). yt-dlp reads each account's watch history and
# those videos are marked watched in the feed.
OVERRIDES = os.path.join(DATA, "watched_overrides.json")
HISTORY_HOURS = float(os.environ.get("HISTORY_HOURS", "2"))
HISTORY_DEPTH = int(os.environ.get("HISTORY_DEPTH", "300"))
# Videos shown in the History and Watch Later rows
LIST_ROW_SIZE = int(os.environ.get("LIST_ROW_SIZE", "60"))
# Local hour (TZ) of the nightly YouTube subscriptions sync; -1 turns it off
SUBS_SYNC_HOUR = int(os.environ.get("SUBS_SYNC_HOUR", "3"))
LISTS = os.path.join(DATA, "lists.json")          # {account: {history: [...], watchLater: [...]}}
VCHANNELS = os.path.join(DATA, "video_channels.json")  # {videoId: channel name} for History cards
SUBS = os.path.join(DATA, "subs_sync.json")       # nightly subscriptions sync state
overrides = _load(OVERRIDES)
lists = _load(LISTS)
vchannels = _load(VCHANNELS)
subs_state = _load(SUBS)
history_status = {}


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def account_name(path):
    return os.path.basename(path).removesuffix(".txt").removeprefix("youtube-") or "account"


def ytdlp_flat(cookie_path, url, end=None, timeout=240):
    """Run yt-dlp --flat-playlist as the account in cookie_path. Returns (entries, error)."""
    import subprocess, shutil, tempfile
    tmp = tempfile.mkdtemp()
    cj = os.path.join(tmp, "cookies.txt")
    shutil.copy(cookie_path, cj)  # yt-dlp rewrites its cookie file; keep the original untouched
    try:
        cmd = ["yt-dlp", "--cookies", cj, "--flat-playlist", "-J", "--no-warnings"]
        if end:
            cmd += ["--playlist-end", str(end)]
        r = subprocess.run(cmd + [url], capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0:
            err = (r.stderr.strip().splitlines() or ["yt-dlp failed"])[-1][:200]
            if "sign in" in err.lower() or "cookies" in err.lower() or "login" in err.lower():
                err += " (the cookies may have expired; export a fresh cookies.txt)"
            return None, err
        return [e for e in (json.loads(r.stdout).get("entries") or []) if e and e.get("id")], None
    except FileNotFoundError:
        return None, "yt-dlp not installed"
    except Exception as e:
        return None, str(e)[:200]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def list_items(entries):
    """Trim yt-dlp playlist entries to what a History / Watch Later card needs (long-form only)."""
    out = []
    for e in entries:
        if "/shorts/" in (e.get("url") or "") or not _re.fullmatch(r"[0-9A-Za-z_-]{11}", e["id"]):
            continue
        if e.get("duration"):
            durations.setdefault(e["id"], int(e["duration"]))
        out.append({"id": e["id"], "title": e.get("title") or "",
                    "channel": e.get("channel") or e.get("uploader") or ""})
        if len(out) >= LIST_ROW_SIZE:
            break
    return out


def sync_history_account(path):
    name = account_name(path)
    try:
        entries, err = ytdlp_flat(path, ":ythistory", HISTORY_DEPTH)
        if err:
            history_status[name] = {"ok": False, "at": _now(), "error": err}
            log.warning("history sync %s failed: %s", name, err)
            return
        ids = [e["id"] for e in entries]
        now = _now()
        acct = {**lists.get(name, {}), "history": list_items(entries), "historyAt": now}
        wl, wl_err = ytdlp_flat(path, "https://www.youtube.com/playlist?list=WL", LIST_ROW_SIZE * 2)
        if wl_err:
            log.warning("watch later sync %s failed: %s", name, wl_err)  # keep the previous row
        else:
            acct["watchLater"] = list_items(wl)
            acct["watchLaterAt"] = now
        with META_LOCK:
            lists[name] = acct
            _save(LISTS, lists)
            _save(DURS, durations)
        added = 0
        with META_LOCK:
            for vid in ids:
                if vid not in watched and vid not in overrides:
                    watched[vid] = now
                    added += 1
            if added:
                _save(WATCHED, watched)
        history_status[name] = {"ok": True, "at": now, "seen": len(ids), "newlyWatched": added,
                                "watchLater": len(acct.get("watchLater", [])),
                                **({"watchLaterError": wl_err} if wl_err else {})}
        log.info("history sync %s: %d videos in history, %d newly marked watched, %s", name, len(ids), added,
                 f"watch later failed ({wl_err})" if wl_err else f"{len(acct['watchLater'])} in watch later row")
    except Exception as e:
        history_status[name] = {"ok": False, "error": str(e)[:200]}
        log.exception("history sync %s", name)


HISTORY_LOCK = threading.Lock()


def sync_history():
    if not HISTORY_LOCK.acquire(blocking=False):
        return
    try:
        import glob
        for path in sorted(glob.glob(os.path.join(COOKIES, "*.txt"))):
            sync_history_account(path)
    finally:
        HISTORY_LOCK.release()


def _cookie_files():
    import glob
    sig = {}
    for path in glob.glob(os.path.join(COOKIES, "*.txt")):
        try:
            st = os.stat(path)
            sig[path] = (st.st_size, int(st.st_mtime))
        except OSError:
            pass
    return sig


def history_worker():
    """Sync every HISTORY_HOURS, and soon after a cookies file is added or replaced."""
    time.sleep(15)
    last_sync, seen = 0.0, None
    while True:
        files = _cookie_files()
        if files and (files != seen or time.time() - last_sync >= HISTORY_HOURS * 3600):
            sync_history()
            last_sync = time.time()
        seen = files
        time.sleep(15)


# --- Nightly YouTube subscriptions sync (one way: YouTube -> YouFresh) -------------------
# Reads each cookies account's subscriptions. New subscriptions are added; channels that came
# from YouTube or a Takeout import and are no longer subscribed are removed. Channels added by
# hand are never removed, pausing is kept, and nothing is ever written back to YouTube.
# A channel you remove in YouFresh is remembered in "excluded" so the sync doesn't re-add it.
SUBS_LOCK = threading.Lock()
SYNCED_SOURCES = ("youtube", "takeout")


def _save_subs():
    with META_LOCK:
        _save(SUBS, subs_state)


def sync_subscriptions():
    import glob
    if not SUBS_LOCK.acquire(blocking=False):
        return {"status": "busy"}
    try:
        paths = sorted(glob.glob(os.path.join(COOKIES, "*.txt")))
        if not paths:
            return {"status": "no cookies"}
        subs, errors = {}, []
        for path in paths:
            entries, err = ytdlp_flat(path, "https://www.youtube.com/feed/channels", timeout=300)
            if err:
                errors.append(f"{account_name(path)}: {err}")
                continue
            for e in entries:
                if ID_RE.fullmatch(e["id"]):
                    subs.setdefault(e["id"], e.get("title") or e.get("channel") or e["id"])
        result = {"at": _now(), "ok": not errors, "subscribed": len(subs), "added": [], "removed": []}
        if errors:
            result["error"] = "; ".join(errors)[:300]
        excluded = subs_state.get("excluded", {})
        with ROSTER_LOCK:
            items = read_all()
            have = {c.get("channelId") for c in items}
            for cid, title in subs.items():
                if cid not in have and cid not in excluded:
                    items.append({"channelId": cid, "title": title, "tags": [], "enabled": True,
                                  "addedAt": _now(), "source": "youtube"})
                    result["added"].append(title)
            # Only remove when every account answered and the list looks complete, so an
            # expired cookie or a YouTube hiccup can never wipe the roster.
            synced = [c for c in items if c.get("source") in SYNCED_SOURCES]
            if not errors and subs and len(subs) >= len(synced) // 2:
                keep = []
                for c in items:
                    if c.get("source") in SYNCED_SOURCES and c.get("channelId") not in subs:
                        result["removed"].append(c.get("title") or c.get("channelId"))
                    else:
                        keep.append(c)
                items = keep
            elif not errors:
                result["note"] = "subscription list looked incomplete; nothing removed"
            if result["added"] or result["removed"]:
                write_all(items)
        subs_state["last"] = result
        _save_subs()
        log.info("subscriptions sync: %d subscribed, +%d, -%d%s", len(subs), len(result["added"]),
                 len(result["removed"]), f" (errors: {result['error']})" if errors else "")
        return result
    except Exception as e:
        log.exception("subscriptions sync")
        subs_state["last"] = {"at": _now(), "ok": False, "error": str(e)[:200]}
        _save_subs()
        return subs_state["last"]
    finally:
        SUBS_LOCK.release()


def subs_worker():
    """Run the subscriptions sync once a night at SUBS_SYNC_HOUR (local time), and once soon
    after startup if it has never run."""
    if SUBS_SYNC_HOUR < 0:
        return
    time.sleep(90)
    while True:
        try:
            lt = time.localtime()
            today = time.strftime("%Y-%m-%d", lt)
            if _cookie_files() and (not subs_state.get("last") or
                                    (lt.tm_hour == SUBS_SYNC_HOUR and subs_state.get("ranOn") != today)):
                subs_state["ranOn"] = today
                sync_subscriptions()
        except Exception:
            log.exception("subscriptions worker")
        time.sleep(300)


def load_roster():
    try:
        with open(ROSTER, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return []
    if isinstance(data, dict):
        data = data.get("channels", [])
    out = []
    for c in data:
        cid = (c.get("channelId") or "").strip()
        if cid.startswith("UC") and len(cid) == 24 and c.get("enabled", True) is not False:
            out.append({"channelId": cid, "title": c.get("title") or cid, "tags": c.get("tags") or []})
    return out


ROSTER_LOCK = threading.Lock()
ID_RE = __import__("re").compile(r"UC[0-9A-Za-z_-]{22}")


def read_all():
    try:
        with open(ROSTER, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return []
    return data.get("channels", []) if isinstance(data, dict) else data


def write_all(items):
    items.sort(key=lambda c: (c.get("title") or "").lower())
    tmp = ROSTER + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
    os.replace(tmp, ROSTER)
    threading.Thread(target=refresh, daemon=True).start()


def clean_tags(t):
    if isinstance(t, str):
        t = t.split(",")
    return sorted({s.strip().lower() for s in (t or []) if str(s).strip()})


def roster_add(body):
    m = ID_RE.search(str(body.get("channelId", "")))
    title = str(body.get("title", "")).strip()
    if not m:
        return 400, {"error": "Paste a channel ID starting with UC, or a youtube.com/channel/UC... link."}
    if not title:
        return 400, {"error": "Add the channel name."}
    with ROSTER_LOCK:
        items = read_all()
        if any(c.get("channelId") == m.group(0) for c in items):
            return 409, {"error": "That channel is already in the roster."}
        if subs_state.get("excluded", {}).pop(m.group(0), None):
            _save_subs()  # added back by hand: the nightly sync may keep it again
        items.append({"channelId": m.group(0), "title": title, "tags": clean_tags(body.get("tags")),
                      "enabled": True, "addedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                      "source": "manual"})
        write_all(items)
    return 200, {"ok": True}


def roster_update(cid, body):
    with ROSTER_LOCK:
        items = read_all()
        for c in items:
            if c.get("channelId") == cid:
                if "title" in body and str(body["title"]).strip():
                    c["title"] = str(body["title"]).strip()
                if "tags" in body:
                    c["tags"] = clean_tags(body["tags"])
                if "enabled" in body:
                    c["enabled"] = bool(body["enabled"])
                write_all(items)
                return 200, {"ok": True}
    return 404, {"error": "Channel not found."}


def roster_delete(cid):
    with ROSTER_LOCK:
        items = read_all()
        keep = [c for c in items if c.get("channelId") != cid]
        if len(keep) == len(items):
            return 404, {"error": "Channel not found."}
        gone = next(c for c in items if c.get("channelId") == cid)
        subs_state.setdefault("excluded", {})[cid] = gone.get("title") or cid
        _save_subs()  # the nightly subscriptions sync won't add it back
        write_all(keep)
    return 200, {"ok": True}


def roster_import(text):
    import csv, io
    found = []
    for row in csv.reader(io.StringIO(text)):
        m = ID_RE.search(" ".join(row))
        if m:
            found.append((m.group(0), (row[2] if len(row) > 2 else row[-1]).strip() or m.group(0)))
    if not found:
        return 400, {"error": "No channel IDs found. Use subscriptions.csv from Google Takeout."}
    with ROSTER_LOCK:
        items = read_all()
        have = {c.get("channelId") for c in items}
        added = 0
        for cid, title in found:
            if cid not in have:
                have.add(cid); added += 1
                items.append({"channelId": cid, "title": title, "tags": [], "enabled": True,
                              "addedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "source": "takeout"})
        if added:
            write_all(items)
    return 200, {"added": added, "skipped": len(found) - added}


# --- Google Takeout drop folder ---------------------------------------------------------
IMPORTED = os.path.join(DATA, "takeout_imported.json")
imported = _load(IMPORTED)
takeout_status = {}


def _subscriptions_from_zip(path):
    import zipfile
    texts = []
    with zipfile.ZipFile(path) as z:
        for n in z.namelist():
            low = n.lower()
            # Takeout path: Takeout/YouTube and YouTube Music/subscriptions/subscriptions.csv
            # (folder names are translated in other languages, so match loosely)
            if low.endswith(".csv") and ("subscription" in low or "/abonnement" in low or "/suscrip" in low):
                texts.append(z.read(n).decode("utf-8-sig", "replace"))
    return texts


def scan_takeout():
    """Import subscriptions from any new or changed file in the takeout folder. Each file is
    imported once (re-import by touching or replacing it). Imports only add channels."""
    try:
        names = sorted(os.listdir(TAKEOUT))
    except OSError:
        return
    for n in names:
        path = os.path.join(TAKEOUT, n)
        if not os.path.isfile(path) or not n.lower().endswith((".zip", ".csv")):
            continue
        st = os.stat(path)
        key = f"{st.st_size}:{int(st.st_mtime)}"
        if imported.get(n) == key or time.time() - st.st_mtime < 20:  # done, or still copying
            continue
        try:
            texts = _subscriptions_from_zip(path) if n.lower().endswith(".zip") else \
                [open(path, encoding="utf-8-sig", errors="replace").read()]
            if not texts:
                result = {"ok": False, "error": "no subscriptions.csv found in this file"}
            else:
                added = skipped = 0
                for t in texts:
                    code, r = roster_import(t)
                    if code == 200:
                        added += r["added"]; skipped += r["skipped"]
                result = {"ok": True, "added": added, "alreadyListed": skipped}
        except Exception as e:
            result = {"ok": False, "error": str(e)[:200]}
        result["at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        takeout_status[n] = result
        imported[n] = key
        _save(IMPORTED, imported)
        log.info("takeout %s: %s", n, result)


def fetch_channel_tab(ch):
    """Backup source: the channel's Videos tab (long-form only) via yt-dlp. Upload times are
    approximate (rounded to the day); the RSS feed's exact times replace them once it's back."""
    import subprocess
    from datetime import datetime, timezone
    try:
        r = subprocess.run(["yt-dlp", "--flat-playlist", "-J", "--no-warnings",
                            "--playlist-end", str(PER_CHANNEL),
                            "--extractor-args", "youtubetab:approximate_date",
                            f"https://www.youtube.com/channel/{ch['channelId']}/videos"],
                           capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            return {**ch, "videos": [], "error": "tab: " + ((r.stderr.strip().splitlines() or ["failed"])[-1][:100])}
        vids = []
        for e in json.loads(r.stdout).get("entries") or []:
            vid = (e or {}).get("id")
            if not vid or not e.get("timestamp"):
                continue
            if e.get("duration"):
                durations.setdefault(vid, int(e["duration"]))
            vids.append({
                "id": vid,
                "title": e.get("title") or "",
                "published": datetime.fromtimestamp(e["timestamp"], timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                "approx": True,
                "thumb": f"https://i.ytimg.com/vi/{vid}/hq720.jpg",
                "thumbFallback": f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg",
                "url": f"https://www.youtube.com/watch?v={vid}",
                "description": (e.get("description") or "")[:400],
            })
        return {**ch, "videos": vids, "via": "tab"}
    except FileNotFoundError:
        return {**ch, "videos": [], "error": "tab: yt-dlp missing"}
    except Exception as e:
        return {**ch, "videos": [], "error": "tab: " + str(e)[:100]}


def fetch_channel(ch):
    r = fetch_channel_rss(ch)
    if r.get("error"):
        t = fetch_channel_tab(ch)
        return t if not t.get("error") else {**r, "error": r["error"] + " / " + t["error"]}
    return r


def fetch_channel_rss(ch):
    url = "https://www.youtube.com/feeds/videos.xml?playlist_id=UULF" + ch["channelId"][2:]
    req = urllib.request.Request(url, headers={"User-Agent": "YouFresh/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            root = ET.fromstring(r.read())
    except urllib.error.HTTPError as e:
        return {**ch, "videos": [], "error": f"HTTP {e.code}"}
    except Exception as e:  # network/parse
        return {**ch, "videos": [], "error": str(e)[:120]}
    vids = []
    for e in root.findall("a:entry", NS):
        vid = e.findtext("yt:videoId", namespaces=NS)
        if not vid:
            continue
        g = e.find("m:group", NS)
        desc = g.findtext("m:description", default="", namespaces=NS) if g is not None else ""
        vids.append({
            "id": vid,
            "title": e.findtext("a:title", default="", namespaces=NS),
            "published": e.findtext("a:published", default="", namespaces=NS),
            "thumb": f"https://i.ytimg.com/vi/{vid}/hq720.jpg",
            "thumbFallback": f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg",
            "url": f"https://www.youtube.com/watch?v={vid}",
            "description": desc[:400],
        })
    vids.sort(key=lambda v: v["published"], reverse=True)
    return {**ch, "videos": vids[:PER_CHANNEL]}


def refresh():
    if not state["lock"].acquire(blocking=False):
        return False
    try:
        roster = load_roster()
        state["roster_mtime"] = os.path.getmtime(ROSTER) if os.path.exists(ROSTER) else 0
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=12) as ex:
            chans = list(ex.map(fetch_channel, roster))
        # Retry stragglers once, gently. Skip it when most channels failed: that's a YouTube-wide
        # outage, retrying just makes the refresh slow, and the existing videos are kept anyway.
        failed = [i for i, c in enumerate(chans) if c.get("error")]
        if failed and len(failed) <= len(chans) // 2:
            time.sleep(5)
            with ThreadPoolExecutor(max_workers=3) as ex:
                for i, c in zip(failed, ex.map(fetch_channel, [roster[i] for i in failed])):
                    chans[i] = c

        # Additive merge: a refresh only ever adds videos. A channel whose fetch fails keeps
        # everything it had, so a YouTube outage can't empty the feed.
        prev = {c["channelId"]: c for c in (state["feed"] or {}).get("channels", [])}
        errors, kept = [], 0
        for c in chans:
            old = prev.get(c["channelId"], {}).get("videos", [])
            if c.get("error"):
                errors.append({"title": c["title"], "error": c["error"]})
                if old:
                    kept += 1
            merged = {v["id"]: v for v in old}
            for v in c["videos"]:  # fresh titles/thumbs win, but never swap an exact time for an approximate one
                o = merged.get(v["id"])
                if o and v.get("approx") and not o.get("approx"):
                    v = {**v, "published": o["published"], "approx": False}
                merged[v["id"]] = v
            c["videos"] = sorted(merged.values(), key=lambda v: v["published"], reverse=True)[:KEEP_PER_CHANNEL]
            c.pop("error", None)
            c["latest"] = c["videos"][0]["published"] if c["videos"] else ""
        chans.sort(key=lambda c: c["latest"], reverse=True)
        feed = {"updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "channelCount": len(chans),
                "errors": errors,
                "channels": [c for c in chans if c["videos"]]}
        if errors:
            kinds = {}
            for e in errors:
                kinds[e["error"]] = kinds.get(e["error"], 0) + 1
            log.warning("%d channels failed (%s); kept previous videos for %d", len(errors),
                        ", ".join(f"{k} x{n}" for k, n in sorted(kinds.items(), key=lambda x: -x[1])[:3]), kept)
        via_tab = sum(1 for c in chans if c.get("via") == "tab")
        for c in chans:
            c.pop("via", None)
        feed["backupSourceChannels"] = via_tab
        tmp = CACHE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(feed, f, ensure_ascii=False)
        os.replace(tmp, CACHE)
        state["feed"] = feed
        log.info("refreshed %d channels (%d with videos, %d errors, %d via Videos tab) in %.1fs",
                 len(chans), len(feed["channels"]), len(feed["errors"]), via_tab, time.time() - t0)
        return True
    except Exception:
        log.exception("refresh failed")
        return False
    finally:
        state["lock"].release()


def loop():
    last = 0
    while True:
        scan_takeout()
        try:
            changed = os.path.exists(ROSTER) and os.path.getmtime(ROSTER) != state["roster_mtime"]
        except OSError:
            changed = False
        if changed or time.time() - last >= INTERVAL:
            if os.path.exists(ROSTER):
                refresh()
            last = time.time()
        time.sleep(15)


class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(b)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        return raw.decode("utf-8", "replace")

    def _json(self, code, obj):
        return self._send(code, json.dumps(obj, ensure_ascii=False))

    def do_POST(self):
        p = self.path.split("?")[0]
        try:
            if p == "/api/import":
                return self._json(*roster_import(self._body()))
            body = json.loads(self._body() or "{}")
            if p == "/api/channels":
                return self._json(*roster_add(body))
            if p.startswith("/api/watched/"):
                return self._json(*set_watched(p.split("/")[3], bool(body.get("watched", True))))
            if p.startswith("/api/channels/") and p.endswith("/delete"):
                return self._json(*roster_delete(p.split("/")[3]))
            if p.startswith("/api/channels/"):
                return self._json(*roster_update(p.split("/")[3], body))
        except json.JSONDecodeError:
            return self._json(400, {"error": "Bad JSON"})
        self._json(404, {"error": "not found"})

    def do_DELETE(self):
        p = self.path.split("?")[0]
        if p.startswith("/api/channels/"):
            return self._json(*roster_delete(p.split("/")[3]))
        self._json(404, {"error": "not found"})

    def do_GET(self):
        p = self.path.split("?")[0]
        if p in ("/", "/index.html"):
            try:
                with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "channels.html"), "rb") as f:
                    return self._send(200, f.read(), "text/html")
            except FileNotFoundError:
                return self._send(404, "channels.html missing", "text/plain")
        if p == "/api/channels":
            items = read_all()
            feed = state["feed"] or {}
            latest = {c["channelId"]: c.get("latest", "") for c in feed.get("channels", [])}
            errs = {e["title"]: e["error"] for e in feed.get("errors", [])}
            out = [{**c, "latest": latest.get(c.get("channelId"), ""),
                    "feedError": errs.get(c.get("title"), "")} for c in items]
            return self._json(200, {"updated": feed.get("updated"), "channels": out})
        if p == "/feed.json":
            feed = enriched_feed()
            if feed is None:  # no channels yet: an empty feed, so the TV app can say what to do
                feed = {"updated": None, "channelCount": 0, "errors": [], "channels": []}
            return self._send(200, json.dumps(feed, ensure_ascii=False))
        if p == "/roster.json":
            try:
                return self._send(200, json.dumps(load_roster(), ensure_ascii=False))
            except Exception as e:
                return self._send(500, json.dumps({"error": str(e)}))
        if p == "/refresh":
            if "wait=1" in self.path:  # block until the feed is rebuilt
                ok = refresh()
                return self._send(200, json.dumps({"status": "refreshed" if ok else "busy-or-failed",
                                                   "updated": (state["feed"] or {}).get("updated")}))
            threading.Thread(target=refresh, daemon=True).start()
            return self._send(202, json.dumps({"status": "refreshing"}))
        if p == "/api/status":
            return self._json(200, {"takeout": takeout_status, "history": history_status,
                                    "historyEveryHours": HISTORY_HOURS,
                                    "subscriptions": {**subs_state.get("last", {}), "nightlyHour": SUBS_SYNC_HOUR,
                                                      "excluded": len(subs_state.get("excluded", {}))},
                                    "channels": len(read_all()),
                                    "feedUpdated": (state["feed"] or {}).get("updated")})
        if p == "/api/history":
            if "sync=1" in self.path:
                threading.Thread(target=sync_history, daemon=True).start()
                return self._json(202, {"status": "syncing"})
            return self._json(200, {"accounts": history_status, "everyHours": HISTORY_HOURS})
        if p == "/api/subscriptions":
            if "sync=1" in self.path:  # ?sync=1 runs the YouTube subscriptions sync now and waits
                return self._json(200, sync_subscriptions())
            return self._json(200, {**subs_state, "nightlyHour": SUBS_SYNC_HOUR})
        if p == "/health":
            return self._send(200, json.dumps({"ok": True, "updated": (state["feed"] or {}).get("updated")}))
        self._send(404, json.dumps({"error": "not found"}))

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    if os.path.exists(CACHE):
        try:
            with open(CACHE, encoding="utf-8") as f:
                state["feed"] = json.load(f)
        except Exception:
            pass
    threading.Thread(target=loop, daemon=True).start()
    threading.Thread(target=duration_worker, daemon=True).start()
    threading.Thread(target=history_worker, daemon=True).start()
    threading.Thread(target=subs_worker, daemon=True).start()
    log.info("YouFresh listening on :%d (data %s, takeout %s, cookies %s)", PORT, DATA, TAKEOUT, COOKIES)
    import socket

    class DualStackServer(ThreadingHTTPServer):
        address_family = socket.AF_INET6
        daemon_threads = True

        def server_bind(self):
            self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)  # IPv4 and IPv6
            super().server_bind()

    try:
        httpd = DualStackServer(("::", PORT), H)
    except OSError:  # no IPv6 in this container
        httpd = ThreadingHTTPServer(("0.0.0.0", PORT), H)
    httpd.serve_forever()
