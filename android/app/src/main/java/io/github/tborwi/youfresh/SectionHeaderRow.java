package io.github.tborwi.youfresh;

import androidx.leanback.widget.Row;

/** A small, unfocusable title between groups of rows, e.g. "All Subscriptions". */
public class SectionHeaderRow extends Row {
    public final String title;

    public SectionHeaderRow(String title) {
        this.title = title;
    }
}
