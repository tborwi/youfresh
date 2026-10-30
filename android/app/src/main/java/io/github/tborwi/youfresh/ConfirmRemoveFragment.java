package io.github.tborwi.youfresh;

import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.widget.Toast;
import androidx.annotation.NonNull;
import androidx.core.content.ContextCompat;
import androidx.leanback.app.GuidedStepSupportFragment;
import androidx.leanback.widget.GuidanceStylist;
import androidx.leanback.widget.GuidedAction;
import java.util.List;

/** Confirms removing one channel from YouFresh. */
public class ConfirmRemoveFragment extends GuidedStepSupportFragment {
    private static final long ID_REMOVE = 1, ID_CANCEL = 2;

    static ConfirmRemoveFragment newInstance(String channelId, String title) {
        ConfirmRemoveFragment f = new ConfirmRemoveFragment();
        Bundle b = new Bundle();
        b.putString("id", channelId);
        b.putString("title", title);
        f.setArguments(b);
        return f;
    }

    private String title() {
        return requireArguments().getString("title", "this channel");
    }

    @NonNull
    @Override
    public GuidanceStylist.Guidance onCreateGuidance(Bundle savedInstanceState) {
        return new GuidanceStylist.Guidance("Remove " + title() + "?",
                "Its row disappears from YouFresh on every TV. You can add it back from the channel page on your server.",
                "Settings", null);
    }

    @Override
    public void onCreateActions(@NonNull List<GuidedAction> actions, Bundle savedInstanceState) {
        actions.add(new GuidedAction.Builder(requireContext()).id(ID_REMOVE).title("Remove")
                .icon(ContextCompat.getDrawable(requireContext(), R.drawable.ic_remove)).build());
        actions.add(new GuidedAction.Builder(requireContext()).id(ID_CANCEL).title("Cancel").build());
    }

    @Override
    public void onGuidedActionClicked(GuidedAction action) {
        if (action.getId() != ID_REMOVE) {
            getParentFragmentManager().popBackStack();
            return;
        }
        String id = requireArguments().getString("id");
        String name = title();
        android.content.Context app = requireContext().getApplicationContext();
        Handler main = new Handler(Looper.getMainLooper());
        new Thread(() -> {
            String msg;
            try {
                Api.post("/api/channels/" + id + "/delete", "{}");
                Api.dirty = true;
                msg = "Removed " + name;
            } catch (Exception e) {
                msg = "Couldn't remove " + name + ": server unreachable";
            }
            String m = msg;
            main.post(() -> {
                Toast.makeText(app, m, Toast.LENGTH_SHORT).show();
                if (isAdded()) getParentFragmentManager().popBackStack();
            });
        }).start();
    }
}
