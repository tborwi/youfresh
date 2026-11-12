package io.github.tborwi.youfresh;

import android.content.Context;
import android.graphics.Typeface;
import android.graphics.drawable.ColorDrawable;
import android.graphics.drawable.GradientDrawable;
import android.text.TextUtils;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;
import androidx.leanback.widget.Presenter;
import com.bumptech.glide.Glide;
import java.time.Duration;
import java.time.Instant;
import java.time.OffsetDateTime;

/**
 * 16:9 thumbnail with the video length in the corner, a two-line title, and its age.
 * Watched videos are dimmed with a red bar along the bottom of the thumbnail.
 */
public class VideoCardPresenter extends Presenter {
    public interface OnLongPress { void onLongPress(Video v); }

    private static final int W = 240, H = 135; // dp
    private static final int INFO = 0xFF1C1C1C, INFO_FOCUSED = 0xFF3A3A3A;
    private final OnLongPress longPress;
    private final boolean showChannel; // mixed-channel rows (New, History, Watch Later) show who posted it
    private final boolean dimWatched;  // the History row is all watched; don't dim every card

    public VideoCardPresenter(OnLongPress longPress) {
        this(longPress, false);
    }

    public VideoCardPresenter(OnLongPress longPress, boolean showChannel) {
        this(longPress, showChannel, true);
    }

    public VideoCardPresenter(OnLongPress longPress, boolean showChannel, boolean dimWatched) {
        this.longPress = longPress;
        this.showChannel = showChannel;
        this.dimWatched = dimWatched;
    }

    static class Holder extends ViewHolder {
        final ImageView thumb;
        final TextView length, badge, title, meta;
        final View bar;
        Video item;

        Holder(View v, ImageView thumb, TextView length, TextView badge, View bar, TextView title, TextView meta) {
            super(v);
            this.thumb = thumb; this.length = length; this.badge = badge; this.bar = bar;
            this.title = title; this.meta = meta;
        }
    }

    @Override
    public ViewHolder onCreateViewHolder(ViewGroup parent) {
        Context ctx = parent.getContext();
        float d = ctx.getResources().getDisplayMetrics().density;
        int w = (int) (W * d), h = (int) (H * d), pad = (int) (8 * d);

        LinearLayout card = new LinearLayout(ctx);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setLayoutParams(new ViewGroup.LayoutParams(w, ViewGroup.LayoutParams.WRAP_CONTENT));
        card.setFocusable(true);
        card.setFocusableInTouchMode(true);
        card.setClipToOutline(true);
        GradientDrawable shape = new GradientDrawable();
        shape.setCornerRadius(6 * d);
        shape.setColor(INFO);
        card.setBackground(shape);

        FrameLayout media = new FrameLayout(ctx);
        ImageView thumb = new ImageView(ctx);
        thumb.setScaleType(ImageView.ScaleType.CENTER_CROP);
        media.addView(thumb, new FrameLayout.LayoutParams(w, h));

        TextView length = badge(ctx, d, 0xD9000000);
        FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(-2, -2, Gravity.BOTTOM | Gravity.END);
        lp.setMargins(0, 0, (int) (6 * d), (int) (9 * d));
        media.addView(length, lp);

        TextView watched = badge(ctx, d, 0xD9000000);
        watched.setText("WATCHED");
        watched.setLetterSpacing(0.08f);
        FrameLayout.LayoutParams wp = new FrameLayout.LayoutParams(-2, -2, Gravity.TOP | Gravity.START);
        wp.setMargins((int) (6 * d), (int) (6 * d), 0, 0);
        media.addView(watched, wp);

        View bar = new View(ctx);
        bar.setBackgroundColor(0xFFE53935);
        media.addView(bar, new FrameLayout.LayoutParams(w, (int) (4 * d), Gravity.BOTTOM));
        card.addView(media, new LinearLayout.LayoutParams(w, h));

        TextView title = new TextView(ctx);
        title.setTextSize(13);
        title.setTextColor(0xFFF2F2F2);
        title.setMaxLines(2);
        title.setMinLines(2);
        title.setEllipsize(TextUtils.TruncateAt.END);
        title.setLineSpacing(0, 1.05f);
        title.setPadding(pad, (int) (6 * d), pad, 0);
        card.addView(title);

        TextView meta = new TextView(ctx);
        meta.setTextSize(11);
        meta.setTextColor(0xFFA8A8A8);
        meta.setSingleLine(true);
        meta.setPadding(pad, (int) (2 * d), pad, (int) (7 * d));
        card.addView(meta);

        Holder holder = new Holder(card, thumb, length, watched, bar, title, meta);
        card.setOnFocusChangeListener((v, has) -> shape.setColor(has ? INFO_FOCUSED : INFO));
        card.setOnLongClickListener(v -> {
            if (holder.item != null && longPress != null) longPress.onLongPress(holder.item);
            return true;
        });
        return holder;
    }

    private static TextView badge(Context ctx, float d, int bg) {
        TextView t = new TextView(ctx);
        t.setTextSize(11);
        t.setTextColor(0xFFFFFFFF);
        t.setTypeface(Typeface.DEFAULT_BOLD);
        t.setPadding((int) (5 * d), (int) (1 * d), (int) (5 * d), (int) (1 * d));
        GradientDrawable b = new GradientDrawable();
        b.setCornerRadius(3 * d);
        b.setColor(bg);
        t.setBackground(b);
        return t;
    }

    @Override
    public void onBindViewHolder(ViewHolder vh, Object item) {
        Holder h = (Holder) vh;
        Video v = (Video) item;
        h.item = v;
        h.title.setText(v.title);
        String when = age(v.published);
        String who = showChannel && v.channel != null ? v.channel : "";
        h.meta.setText(who.isEmpty() ? when : when.isEmpty() ? who : who + "  ·  " + when);
        String len = length(v.duration);
        h.length.setText(len);
        h.length.setVisibility(len.isEmpty() ? View.GONE : View.VISIBLE);
        boolean dim = v.watched && dimWatched;
        h.badge.setVisibility(dim ? View.VISIBLE : View.GONE);
        h.bar.setVisibility(dim ? View.VISIBLE : View.GONE);
        h.thumb.setAlpha(dim ? 0.45f : 1f);
        h.title.setTextColor(dim ? 0xFF9A9A9A : 0xFFF2F2F2);
        Glide.with(h.thumb.getContext())
                .load(v.thumb)
                .placeholder(new ColorDrawable(0xFF2A2A2A))
                .error(Glide.with(h.thumb.getContext()).load(v.thumbFallback))
                .centerCrop()
                .into(h.thumb);
    }

    @Override
    public void onUnbindViewHolder(ViewHolder vh) {
        Holder h = (Holder) vh;
        h.item = null;
        Glide.with(h.thumb.getContext()).clear(h.thumb);
        h.thumb.setImageDrawable(null);
    }

    static String length(int s) {
        if (s <= 0) return "";
        int hh = s / 3600, mm = (s % 3600) / 60, ss = s % 60;
        return hh > 0 ? String.format("%d:%02d:%02d", hh, mm, ss) : String.format("%d:%02d", mm, ss);
    }

    static String age(String iso) {
        try {
            Instant t = OffsetDateTime.parse(iso).toInstant();
            long m = Duration.between(t, Instant.now()).toMinutes();
            if (m < 60) return Math.max(m, 1) + " min ago";
            long h = m / 60;
            if (h < 24) return h + (h == 1 ? " hour ago" : " hours ago");
            long dd = h / 24;
            if (dd < 7) return dd + (dd == 1 ? " day ago" : " days ago");
            if (dd < 60) return (dd / 7) + ((dd / 7) == 1 ? " week ago" : " weeks ago");
            if (dd < 730) return (dd / 30) + " months ago";
            return (dd / 365) + " years ago";
        } catch (Exception e) {
            return "";
        }
    }
}
