package io.github.tborwi.youfresh;

import android.graphics.drawable.Drawable;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.widget.Toast;
import androidx.annotation.NonNull;
import androidx.core.content.ContextCompat;
import androidx.leanback.app.GuidedStepSupportFragment;
import androidx.leanback.widget.GuidanceStylist;
import androidx.leanback.widget.GuidedAction;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.json.JSONArray;
import org.json.JSONObject;

/** Settings: refresh all feeds, and the channel list with a remove icon beside each name. */
public class SettingsFragment extends GuidedStepSupportFragment {
    static final long ID_REFRESH = 1, ID_HEADER = 2, ID_LOADING = 3, ID_SERVER = 4, ID_CHANNEL_BASE = 1000;
    private final ExecutorService io = Executors.newSingleThreadExecutor();
    private final Handler main = new Handler(Looper.getMainLooper());
    private final List<String[]> channels = new ArrayList<>(); // {channelId, title}
    private boolean refreshing = false;

    @NonNull
    @Override
    public GuidanceStylist.Guidance onCreateGuidance(Bundle savedInstanceState) {
        return new GuidanceStylist.Guidance("Settings",
                "Refresh every feed now, change the server, or remove a channel.",
                getString(R.string.app_name), null);
    }

    @Override
    public void onCreateActions(@NonNull List<GuidedAction> actions, Bundle savedInstanceState) {
        actions.addAll(build(null));
    }

    @Override
    public void onResume() {
        super.onResume();
        loadChannels();
    }

    @Override
    public void onDestroy() {
        io.shutdownNow();
        super.onDestroy();
    }

    private List<GuidedAction> build(String status) {
        List<GuidedAction> a = new ArrayList<>();
        a.add(new GuidedAction.Builder(requireContext()).id(ID_REFRESH)
                .title(refreshing ? "Refreshing all feeds…" : "Refresh all feeds")
                .description(status != null ? status : "Pull the newest videos for every channel")
                .icon(ContextCompat.getDrawable(requireContext(), R.drawable.ic_refresh))
                .enabled(!refreshing).build());
        a.add(new GuidedAction.Builder(requireContext()).id(ID_SERVER)
                .title("Server address")
                .description(Api.server() + "  ·  channels are managed in a browser at this address")
                .build());
        if (channels.isEmpty()) {
            a.add(new GuidedAction.Builder(requireContext()).id(ID_LOADING)
                    .title("Loading channels…").infoOnly(true).focusable(false).build());
            return a;
        }
        a.add(new GuidedAction.Builder(requireContext()).id(ID_HEADER)
                .title("Channels (" + channels.size() + ")")
                .description("Select a channel to remove it")
                .infoOnly(true).focusable(false).build());
        Drawable remove = ContextCompat.getDrawable(requireContext(), R.drawable.ic_remove);
        for (int i = 0; i < channels.size(); i++) {
            a.add(new GuidedAction.Builder(requireContext()).id(ID_CHANNEL_BASE + i)
                    .title(channels.get(i)[1]).icon(remove).build());
        }
        return a;
    }

    void loadChannels() {
        io.execute(() -> {
            try {
                JSONArray arr = new JSONObject(Api.get("/api/channels", 15000)).getJSONArray("channels");
                List<String[]> list = new ArrayList<>();
                for (int i = 0; i < arr.length(); i++) {
                    JSONObject c = arr.getJSONObject(i);
                    list.add(new String[]{c.getString("channelId"), c.optString("title")});
                }
                list.sort((x, y) -> x[1].compareToIgnoreCase(y[1]));
                main.post(() -> {
                    if (!isAdded()) return;
                    int keep = getSelectedActionPosition();
                    boolean first = channels.isEmpty();
                    channels.clear();
                    channels.addAll(list);
                    setActions(build(null));
                    // first load: stay on Refresh; after a removal: stay near where you were
                    setSelectedActionPosition(first ? 0 : Math.max(0, Math.min(keep, getActions().size() - 1)));
                });
            } catch (Exception e) {
                main.post(() -> toast("Couldn't load channels from " + Api.server()));
            }
        });
    }

    @Override
    public void onGuidedActionClicked(GuidedAction action) {
        long id = action.getId();
        if (id == ID_SERVER) {
            startActivity(new android.content.Intent(requireContext(), SetupActivity.class));
            return;
        }
        if (id == ID_REFRESH) {
            refreshing = true;
            setActions(build("This takes about 20 seconds"));
            io.execute(() -> {
                String status;
                try {
                    Api.get("/refresh?wait=1", 90000);
                    Api.dirty = true;
                    status = "Feeds refreshed just now";
                } catch (Exception e) {
                    status = "Refresh failed: couldn't reach " + Api.server();
                }
                String s = status;
                main.post(() -> {
                    if (!isAdded()) return;
                    refreshing = false;
                    setActions(build(s));
                });
            });
        } else if (id >= ID_CHANNEL_BASE) {
            int i = (int) (id - ID_CHANNEL_BASE);
            if (i < channels.size()) {
                String[] c = channels.get(i);
                GuidedStepSupportFragment.add(getParentFragmentManager(),
                        ConfirmRemoveFragment.newInstance(c[0], c[1]));
            }
        }
    }

    private void toast(String s) {
        if (isAdded()) Toast.makeText(requireContext(), s, Toast.LENGTH_LONG).show();
    }
}
