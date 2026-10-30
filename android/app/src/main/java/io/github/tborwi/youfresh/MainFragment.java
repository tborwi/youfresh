package io.github.tborwi.youfresh;

import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.widget.Toast;
import androidx.annotation.Nullable;
import androidx.leanback.app.BackgroundManager;
import androidx.leanback.app.BrowseSupportFragment;
import androidx.leanback.widget.ArrayObjectAdapter;
import androidx.leanback.widget.FocusHighlight;
import androidx.leanback.widget.HeaderItem;
import androidx.leanback.widget.ListRow;
import androidx.leanback.widget.ListRowPresenter;
import androidx.leanback.widget.OnItemViewClickedListener;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.json.JSONArray;
import org.json.JSONObject;

/** One row per channel, newest video on the left; rows ordered by latest upload. Settings row on top. */
public class MainFragment extends BrowseSupportFragment {
    private static final long STALE_MS = 15 * 60 * 1000;
    private static final int BLACK = 0xFF000000;
    private final ExecutorService io = Executors.newSingleThreadExecutor();
    private final Handler main = new Handler(Looper.getMainLooper());
    private ArrayObjectAdapter rows;
    private long loadedAt = 0;
    private final Map<String, ArrayObjectAdapter> rowOf = new HashMap<>();
    private static final long NEW_WINDOW_MS = 48L * 60 * 60 * 1000;
    private ArrayObjectAdapter newRow; // unwatched videos from the last 48 hours

    @Override
    public void onCreate(@Nullable Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setHeadersState(HEADERS_DISABLED);
        setHeadersTransitionOnBackEnabled(false);
        setBrandColor(BLACK);

        ListRowPresenter rp = new ListRowPresenter(FocusHighlight.ZOOM_FACTOR_MEDIUM, false);
        rp.setShadowEnabled(true);
        rp.setSelectEffectEnabled(false);
        rows = new ArrayObjectAdapter(rp);
        setAdapter(rows);

        setOnItemViewClickedListener((OnItemViewClickedListener) (ivh, item, rvh, row) -> {
            if (item instanceof Video) {
                setWatched((Video) item, true);
                play((Video) item);
            }
            else if (item == SettingsCardPresenter.ITEM)
                startActivity(new Intent(requireContext(), SettingsActivity.class));
        });
    }

    @Override
    public void onStart() {
        super.onStart();
        BackgroundManager bg = BackgroundManager.getInstance(requireActivity());
        if (!bg.isAttached()) bg.attach(requireActivity().getWindow());
        bg.setColor(BLACK);
    }

    @Override
    public void onResume() {
        super.onResume();
        if (!Api.configured()) {
            startActivity(new Intent(requireContext(), SetupActivity.class));
            return;
        }
        if (Api.dirty || System.currentTimeMillis() - loadedAt > STALE_MS) {
            Api.dirty = false;
            load();
        }
    }

    @Override
    public void onDestroy() {
        main.removeCallbacksAndMessages(null);
        io.shutdownNow();
        super.onDestroy();
    }

    private void load() {
        io.execute(() -> {
            try {
                JSONObject feed = new JSONObject(Api.get("/feed.json", 20000));
                JSONArray chans = feed.getJSONArray("channels");
                main.post(() -> render(chans));
            } catch (Exception e) {
                main.post(() -> {
                    if (!isAdded()) return;
                    if (rows.size() == 0) renderSettingsOnly();
                    Toast.makeText(requireContext(),
                            "Couldn't reach your YouFresh server at " + Api.server() + ". Change it in Settings.",
                            Toast.LENGTH_LONG).show();
                });
            }
        });
    }

    private ListRow settingsRow() {
        ArrayObjectAdapter s = new ArrayObjectAdapter(new SettingsCardPresenter());
        s.add(SettingsCardPresenter.ITEM);
        return new ListRow(new HeaderItem(-1, ""), s);
    }

    private void renderSettingsOnly() {
        rows.clear();
        rows.add(settingsRow());
    }

    private void render(JSONArray chans) {
        if (!isAdded()) return;
        rows.clear();
        rows.add(settingsRow());
        rowOf.clear();
        VideoCardPresenter.OnLongPress toggle = v -> {
            setWatched(v, !v.watched);
            Toast.makeText(requireContext(), v.watched ? "Marked watched" : "Marked unwatched", Toast.LENGTH_SHORT).show();
        };
        VideoCardPresenter cp = new VideoCardPresenter(toggle);
        long cutoff = System.currentTimeMillis() - NEW_WINDOW_MS;
        List<Video> fresh = new ArrayList<>();
        for (int i = 0; i < chans.length(); i++) {
            JSONObject c = chans.optJSONObject(i);
            if (c == null) continue;
            JSONArray vids = c.optJSONArray("videos");
            if (vids == null || vids.length() == 0) continue;
            String name = c.optString("title");
            ArrayObjectAdapter items = new ArrayObjectAdapter(cp);
            for (int j = 0; j < vids.length(); j++) {
                JSONObject o = vids.optJSONObject(j);
                if (o == null) continue;
                Video v = new Video();
                v.id = o.optString("id");
                v.title = o.optString("title");
                v.published = o.optString("published");
                v.thumb = o.optString("thumb");
                v.thumbFallback = o.optString("thumbFallback");
                v.url = o.optString("url");
                v.channel = name;
                v.duration = o.optInt("duration", 0);
                v.watched = o.optBoolean("watched", false);
                items.add(v);
                rowOf.put(v.id, items);
                if (!v.watched && publishedMs(v.published) >= cutoff) fresh.add(v);
            }
            String age = VideoCardPresenter.age(c.optString("latest"));
            rows.add(new ListRow(new HeaderItem(i, name + "  ·  " + age), items));
        }
        newRow = null;
        if (!fresh.isEmpty()) {
            fresh.sort((a, b) -> b.published.compareTo(a.published));
            newRow = new ArrayObjectAdapter(new VideoCardPresenter(toggle, true));
            newRow.addAll(0, fresh);
            rows.add(1, new ListRow(new HeaderItem(-2, "New  ·  last 48 hours  ·  " + fresh.size() + " unwatched"), newRow));
        }
        loadedAt = System.currentTimeMillis();
        if (chans.length() == 0) {
            Toast.makeText(requireContext(), "No channels yet. Open " + Api.server()
                    + " in a web browser to add them, or drop your Google Takeout zip in the server's takeout folder.",
                    Toast.LENGTH_LONG).show();
        }
        if (rows.size() > 1) setSelectedPosition(1, false); // land on New (or the newest channel), Settings just above
    }

    /** Update the card right away, then tell the server so other TVs see it too. */
    private void setWatched(Video v, boolean on) {
        v.watched = on;
        ArrayObjectAdapter a = rowOf.get(v.id);
        if (a != null) {
            int i = a.indexOf(v);
            if (i >= 0) a.notifyArrayItemRangeChanged(i, 1);
        }
        if (on && newRow != null) {
            int j = newRow.indexOf(v);
            if (j >= 0) newRow.removeItems(j, 1); // watched videos leave the New row
        }
        String id = v.id;
        io.execute(() -> {
            try {
                Api.post("/api/watched/" + id, "{\"watched\":" + on + "}");
            } catch (Exception ignored) {
                // stays marked on this TV until the next reload
            }
        });
    }

    private static long publishedMs(String iso) {
        try {
            return OffsetDateTime.parse(iso).toInstant().toEpochMilli();
        } catch (Exception e) {
            return 0;
        }
    }

    private void play(Video v) {
        Uri uri = Uri.parse("https://www.youtube.com/watch?v=" + v.id);
        Intent yt = new Intent(Intent.ACTION_VIEW, uri).setPackage("com.google.android.youtube.tv");
        try {
            startActivity(yt);
        } catch (ActivityNotFoundException e) {
            try {
                startActivity(new Intent(Intent.ACTION_VIEW, uri));
            } catch (ActivityNotFoundException e2) {
                Toast.makeText(requireContext(), "YouTube app not found", Toast.LENGTH_LONG).show();
            }
        }
    }
}
