package io.github.tborwi.youfresh;

import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import androidx.annotation.NonNull;
import androidx.leanback.app.GuidedStepSupportFragment;
import androidx.leanback.widget.GuidanceStylist;
import androidx.leanback.widget.GuidedAction;
import java.util.List;

/** Asks for the YouFresh server address and checks that it answers. */
public class SetupFragment extends GuidedStepSupportFragment {
    private static final long ID_ADDRESS = 1, ID_CONNECT = 2;
    private String address = "";

    @NonNull
    @Override
    public GuidanceStylist.Guidance onCreateGuidance(Bundle savedInstanceState) {
        return new GuidanceStylist.Guidance("Connect to your YouFresh server",
                "Enter the address of the computer running the YouFresh server, for example 192.168.1.20 "
                        + "(port 8099 is added for you). Open that address in a web browser to manage your channels.",
                getString(R.string.app_name), null);
    }

    @Override
    public void onCreateActions(@NonNull List<GuidedAction> actions, Bundle savedInstanceState) {
        address = Api.configured() ? Api.server() : "";
        actions.add(new GuidedAction.Builder(requireContext()).id(ID_ADDRESS)
                .title(address.isEmpty() ? "Server address" : address)
                .description("Select to type the address")
                .editTitle(address)
                .editInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI)
                .editable(true).build());
        actions.add(new GuidedAction.Builder(requireContext()).id(ID_CONNECT)
                .title("Connect").description("Check the address and save it").build());
    }

    @Override
    public long onGuidedActionEditedAndProceed(GuidedAction action) {
        if (action.getId() == ID_ADDRESS) {
            address = String.valueOf(action.getEditTitle()).trim();
            action.setTitle(address.isEmpty() ? "Server address" : address);
            action.setDescription("Select to change");
            notifyActionChanged(findActionPositionById(ID_ADDRESS));
            return ID_CONNECT;
        }
        return GuidedAction.ACTION_ID_CURRENT;
    }

    @Override
    public void onGuidedActionClicked(GuidedAction action) {
        if (action.getId() != ID_CONNECT) return;
        String url = Api.normalize(address);
        GuidedAction connect = findActionById(ID_CONNECT);
        if (url.isEmpty()) {
            status(connect, "Type the server address first");
            return;
        }
        status(connect, "Checking " + url + "…");
        Handler main = new Handler(Looper.getMainLooper());
        new Thread(() -> {
            boolean ok = Api.ping(url);
            main.post(() -> {
                if (!isAdded()) return;
                if (ok) {
                    Api.setServer(requireContext(), url);
                    requireActivity().finish();
                } else {
                    status(connect, "No YouFresh server answered at " + url
                            + ". Check the address and that the server is running.");
                }
            });
        }).start();
    }

    private void status(GuidedAction a, String text) {
        a.setDescription(text);
        notifyActionChanged(findActionPositionById(a.getId()));
    }
}
