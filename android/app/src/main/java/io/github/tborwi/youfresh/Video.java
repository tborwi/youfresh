package io.github.tborwi.youfresh;

public class Video {
    public String id, title, published, thumb, thumbFallback, url, channel;
    public int duration;      // seconds, 0 = unknown
    public boolean watched;   // opened from this app on any TV
}
