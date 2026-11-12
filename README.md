# YouFresh

A calm, long-form-only feed of your YouTube subscriptions for Google TV.

YouFresh shows a **Newest Videos** row with everything from the last 48 hours you haven't watched yet, your YouTube **History** and **Watch Later** rows, and then **All Subscriptions**: one row per channel with the newest video on the left. No Shorts, no live streams, no recommendations, no algorithm. Pick a video and it plays in the YouTube app.

It has two parts:

- **YouFresh server**: a small Docker container on any always-on computer at home (a NAS, a Raspberry Pi, a home server). It keeps your channel list, checks each channel for new long-form videos every 30 minutes, and tracks what you've watched.
- **YouFresh TV app**: an Android TV / Google TV app that shows the feed from your server.

> YouFresh is an independent project. It isn't affiliated with or endorsed by YouTube or Google.

## What you need

- A computer that stays on, with [Docker](https://docs.docker.com/get-docker/) and Docker Compose
- A Google TV or Android TV device (Chromecast with Google TV, Google TV Streamer, onn 4K, Shield, most TVs with Google TV)
- The YouTube app on the TV, for playback

## 1. Start the server

```sh
git clone https://github.com/tborwi/youfresh.git
cd youfresh
docker compose up -d --build
```

Before starting, open `docker-compose.yml` and set:

- `TZ` to your time zone
- `PUID` and `PGID` to your user and group ids (run `id` to see them), so you can copy files into the folders below

On first start the server creates a `youfresh` folder next to `docker-compose.yml`:

```
youfresh/
  takeout/   drop your Google Takeout zip here to load your subscriptions
  cookies/   (optional) drop a YouTube cookies file here to sync your watch history
  data/      YouFresh's own files; leave these alone
```

Open `http://<server-address>:8099` in a browser (for example `http://192.168.1.20:8099`). That's the channel page, where you can add, rename, pause and remove channels.

## 2. Load your subscriptions from Google Takeout

1. Go to [takeout.google.com](https://takeout.google.com) and click **Deselect all**.
2. Scroll to **YouTube and YouTube Music** and check it.
3. Click **All YouTube data included**, click **Deselect all**, then check only **subscriptions**. Click **OK**.
4. Click **Next step**, then **Create export**. Google emails you when the zip is ready (usually a few minutes).
5. Download the zip and copy it, unopened, into `youfresh/takeout/`.

Within a minute YouFresh imports every channel in it. The channel page's **Connections** box shows the result.

- Each file is imported once. To import again, replace the file or drop in a newer export.
- Imports only add channels. Channels you removed earlier come back only if they're in a newer export you drop in.
- A bare `subscriptions.csv` works too, and so does **Import Takeout CSV** on the channel page.
- You can also add channels one at a time on the channel page with their channel ID (`UC…`) or a `youtube.com/channel/UC…` link.

## 3. (Optional) Connect your YouTube account

With a cookies file in place, YouFresh:

- marks videos you watch anywhere (phone, laptop, the YouTube app) as watched, so they drop out of **Newest Videos**
- shows your recent watch **History** and your **Watch Later** playlist as rows on the TV
- syncs your **subscriptions** every night: new subscriptions are added, and channels you unsubscribed from on YouTube are removed. This goes one way only; YouFresh never changes anything on your YouTube account.

Without it, YouFresh still marks a video watched when you open it from YouFresh, and you manage channels with Takeout and the channel page.

YouFresh reads your history with [yt-dlp](https://github.com/yt-dlp/yt-dlp), using the cookies from a browser where you're signed in to YouTube:

1. In Chrome, install the **Get cookies.txt LOCALLY** extension. Then go to `chrome://extensions`, open its **Details**, and turn on **Allow in Incognito**.
2. Open an Incognito window and sign in to [youtube.com](https://www.youtube.com).
3. Click the extension and choose **Export**. Save the file with the account's name, for example `alex.txt`.
4. Close the Incognito window **without signing out** (signing out cancels the cookies).
5. Copy the file into `youfresh/cookies/`.

Add one file per YouTube account if more than one person uses YouFresh. History and Watch Later sync within about a minute of adding or replacing a file, then every 2 hours. Subscriptions sync a couple of minutes after the first file is added, then nightly at 3 am. The **Connections** box on the channel page shows each account's last sync.

How the subscriptions sync treats your channel list:

- Channels you added by hand on the channel page are never removed.
- Channels you remove in YouFresh stay removed, even if you're still subscribed on YouTube. Adding one back by hand undoes that.
- Paused channels stay paused.
- If any account's sync fails, or YouTube returns a list that looks incomplete, nothing is removed that night.

**Please read:**

- A cookies file works like a signed-in session for that Google account. Keep the `cookies` folder private, and don't share or commit it. YouFresh only uses it to read your watch history, Watch Later playlist and subscriptions, and only from your own server.
- Cookies eventually expire, or stop working if you sign out of that session or change your password. When they do, the Connections box shows the error; export a fresh file to fix it.
- This uses YouTube in a way it doesn't officially support. Syncing every couple of hours is gentle, but use it at your own discretion.

## 4. Install the TV app

Download **YouFresh.apk** from the [latest release](https://github.com/tborwi/youfresh/releases/latest), then install it on your TV in one of these ways.

**With the Downloader app (no computer needed)**

1. On the TV, install **Downloader** by AFTVnews from the Play Store.
2. In the TV's settings, allow Downloader to install unknown apps. On Google TV that's *Settings > System > About*: click *Android TV OS build* 7 times to turn on developer options, then *Settings > Apps > Security & restrictions > Unknown sources > Downloader*.
3. In Downloader, enter `https://github.com/tborwi/youfresh/releases/latest/download/YouFresh.apk` and install it.

**With adb from a computer**

Turn on developer options as above, then turn on *Network debugging* or *Wireless debugging* (the name varies by device) under *Developer options*.

```sh
adb connect <tv-address>:5555
adb install -r YouFresh.apk
# optional: set the server address without typing it on the TV
adb shell am start -n io.github.tborwi.youfresh/.MainActivity --es server http://<server-address>:8099
```

On first launch YouFresh asks for your server's address. Type it with the remote (`192.168.1.20` is enough; port 8099 is added for you).

## Using YouFresh

- **Newest Videos** (top row): unwatched videos from the last 48 hours, newest first.
- **History**: what you've watched on YouTube, most recent first (needs a cookies file).
- **Watch Later**: your YouTube Watch Later playlist, in YouTube's order (needs a cookies file).
- **All Subscriptions**: one row per channel, newest video on the left. Channels with the most recent uploads come first.
- **Watched**: opening a video marks it watched. Hold **Select** on a card to switch it between watched and unwatched. Watched cards are dimmed with a red bar.
- **Settings** (press Up from the top row): refresh all feeds now, change the server address, or remove a channel.

The YouTube app may show its "Who's watching?" screen when it opens. That screen is part of the YouTube app; press Back to return to YouFresh after a video.

## Settings

Set these in `docker-compose.yml` under `environment:`.

| Variable | Default | What it does |
|---|---|---|
| `TZ` | `UTC` | Time zone for the logs |
| `PUID` / `PGID` | `1000` | Owner of the `takeout`, `cookies` and `data` folders |
| `REFRESH_MINUTES` | `30` | How often channels are checked for new videos |
| `HISTORY_HOURS` | `2` | How often watch history and Watch Later sync (when cookies are present) |
| `HISTORY_DEPTH` | `300` | How many recent history entries each sync reads |
| `LIST_ROW_SIZE` | `60` | Videos shown in the History and Watch Later rows |
| `SUBS_SYNC_HOUR` | `3` | Local hour (set by `TZ`) of the nightly subscriptions sync; `-1` turns it off |
| `VIDEOS_PER_CHANNEL` | `15` | Videos fetched per channel on each check |
| `KEEP_PER_CHANNEL` | `30` | Videos kept per channel row |
| `YTDLP_AUTO_UPDATE` | `1` | Update yt-dlp each time the container starts |
| `PORT` | `8099` | Port inside the container |

## How it works

- New videos come from each channel's **uploads feed filtered to long-form videos**, so Shorts and live streams never show up.
- When YouTube's feed service has an outage (it happens), YouFresh reads the channel's Videos tab instead, and never removes videos from a row because of a failed check.
- Video lengths are looked up once per video in the background.
- Everything is stored as plain JSON in `youfresh/data/`. Back up that folder to keep your channels and watched list.

The server's API, used by the TV app and the channel page:

| Endpoint | |
|---|---|
| `GET /feed.json` | The feed: channels sorted by latest upload, each with its videos, plus `lists` (History and Watch Later per account) |
| `GET /api/channels` | Your channel list |
| `POST /api/channels` | Add a channel: `{"title": "...", "channelId": "UC..."}` |
| `POST /api/channels/<id>` | Update `title`, `tags` or `enabled` |
| `POST /api/channels/<id>/delete` | Remove a channel |
| `POST /api/import` | Import a Takeout `subscriptions.csv` (request body is the CSV) |
| `POST /api/watched/<videoId>` | `{"watched": true}` or `false` |
| `GET /api/status` | Takeout imports, history and subscriptions sync status |
| `GET /api/subscriptions` | Subscriptions sync state (`?sync=1` runs it now and waits) |
| `GET /refresh` | Check all channels now (`?wait=1` waits until done) |

There's no login. Run it on your home network only, or put it behind a reverse proxy with authentication if you expose it.

## Building the TV app yourself

You only need Docker:

```sh
cd android
./build.sh            # writes android/YouFresh.apk
```

Without a signing key it uses a throwaway debug key. To sign with your own key, create one with `keytool` and describe it in `android/keystore.properties` (see the comment at the top of `android/app/build.gradle`). Keep the key safe: Android only installs updates signed with the same key.

## License

[MIT](LICENSE)
