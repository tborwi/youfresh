package io.github.tborwi.youfresh;

import android.content.Context;
import android.graphics.drawable.GradientDrawable;
import android.view.Gravity;
import android.view.ViewGroup;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;
import androidx.leanback.widget.Presenter;

/** Small gear card that opens Settings. */
public class SettingsCardPresenter extends Presenter {
    public static final Object ITEM = new Object();

    @Override
    public ViewHolder onCreateViewHolder(ViewGroup parent) {
        Context ctx = parent.getContext();
        float d = ctx.getResources().getDisplayMetrics().density;
        LinearLayout card = new LinearLayout(ctx);
        card.setOrientation(LinearLayout.HORIZONTAL);
        card.setGravity(Gravity.CENTER);
        card.setFocusable(true);
        card.setFocusableInTouchMode(true);
        card.setLayoutParams(new ViewGroup.LayoutParams((int) (170 * d), (int) (56 * d)));
        GradientDrawable bg = new GradientDrawable();
        bg.setCornerRadius(8 * d);
        bg.setColor(0xFF222222);
        card.setBackground(bg);
        card.setOnFocusChangeListener((v, has) -> bg.setColor(has ? 0xFF3A3A3A : 0xFF222222));

        ImageView icon = new ImageView(ctx);
        icon.setImageResource(R.drawable.ic_settings);
        LinearLayout.LayoutParams ip = new LinearLayout.LayoutParams((int) (24 * d), (int) (24 * d));
        ip.rightMargin = (int) (10 * d);
        card.addView(icon, ip);

        TextView label = new TextView(ctx);
        label.setText("Settings");
        label.setTextColor(0xFFEEEEEE);
        label.setTextSize(16);
        card.addView(label);
        return new ViewHolder(card);
    }

    @Override
    public void onBindViewHolder(ViewHolder vh, Object item) {}

    @Override
    public void onUnbindViewHolder(ViewHolder vh) {}
}
