package io.github.tborwi.youfresh;

import android.content.Context;
import android.graphics.Typeface;
import android.view.ViewGroup;
import android.widget.TextView;
import androidx.leanback.widget.RowPresenter;

/** Draws a {@link SectionHeaderRow}: small accent-colored capitals, never takes focus. */
public class SectionHeaderPresenter extends RowPresenter {
    public SectionHeaderPresenter() {
        setHeaderPresenter(null);
        setSelectEffectEnabled(false);
    }

    @Override
    protected ViewHolder createRowViewHolder(ViewGroup parent) {
        Context ctx = parent.getContext();
        float d = ctx.getResources().getDisplayMetrics().density;
        TextView t = new TextView(ctx);
        t.setLayoutParams(new ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT));
        t.setTextSize(15);
        t.setTypeface(Typeface.DEFAULT_BOLD);
        t.setAllCaps(true);
        t.setLetterSpacing(0.12f);
        t.setTextColor(0xFF3CC29F);
        t.setPadding((int) (56 * d), (int) (22 * d), (int) (56 * d), (int) (2 * d));
        t.setFocusable(false);
        return new ViewHolder(t);
    }

    @Override
    protected void onBindRowViewHolder(ViewHolder vh, Object item) {
        super.onBindRowViewHolder(vh, item);
        ((TextView) vh.view).setText(((SectionHeaderRow) item).title);
    }

    @Override
    public boolean isUsingDefaultSelectEffect() {
        return false;
    }
}
