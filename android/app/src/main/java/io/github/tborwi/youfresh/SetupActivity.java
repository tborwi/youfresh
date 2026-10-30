package io.github.tborwi.youfresh;

import android.os.Bundle;
import androidx.fragment.app.FragmentActivity;
import androidx.leanback.app.GuidedStepSupportFragment;

public class SetupActivity extends FragmentActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        Api.init(this);
        if (savedInstanceState == null) {
            GuidedStepSupportFragment.addAsRoot(this, new SetupFragment(), android.R.id.content);
        }
    }
}
