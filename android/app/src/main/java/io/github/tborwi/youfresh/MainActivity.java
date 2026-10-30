package io.github.tborwi.youfresh;

import android.content.Intent;
import android.os.Bundle;
import androidx.fragment.app.FragmentActivity;

public class MainActivity extends FragmentActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        Api.init(this);
        applyServerExtra(getIntent());
        if (savedInstanceState == null) {
            getSupportFragmentManager().beginTransaction()
                    .replace(android.R.id.content, new MainFragment())
                    .commit();
        }
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        applyServerExtra(intent);
    }

    /** Lets setup scripts set the server: adb shell am start -n <pkg>/.MainActivity --es server http://host:8099 */
    private void applyServerExtra(Intent intent) {
        String s = intent == null ? null : intent.getStringExtra("server");
        if (s != null && !s.trim().isEmpty()) Api.setServer(this, Api.normalize(s));
    }
}
