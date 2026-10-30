package io.github.tborwi.youfresh;

import android.content.Context;
import android.content.SharedPreferences;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

/** Tiny HTTP helper for the YouFresh server. The server address is set on first launch. */
public final class Api {
    private static final String PREFS = "youfresh", KEY_SERVER = "server";
    private static volatile String base = "";
    /** Set when the channel list changed, so the rows reload on return. */
    public static volatile boolean dirty = false;

    private Api() {}

    public static void init(Context ctx) {
        base = prefs(ctx).getString(KEY_SERVER, "");
    }

    public static boolean configured() {
        return !base.isEmpty();
    }

    public static String server() {
        return base;
    }

    /** Accepts "192.168.1.20", "192.168.1.20:8099" or a full URL; returns e.g. http://192.168.1.20:8099 */
    public static String normalize(String input) {
        String s = input == null ? "" : input.trim();
        if (s.isEmpty()) return "";
        if (!s.matches("(?i)^https?://.*")) s = "http://" + s;
        while (s.endsWith("/")) s = s.substring(0, s.length() - 1);
        if (s.endsWith("/feed.json")) s = s.substring(0, s.length() - "/feed.json".length());
        String hostPart = s.replaceFirst("(?i)^https?://", "");
        if (!hostPart.contains(":") && !hostPart.contains("/") && s.toLowerCase().startsWith("http://")) s += ":8099";
        return s;
    }

    public static void setServer(Context ctx, String url) {
        base = url;
        prefs(ctx).edit().putString(KEY_SERVER, url).apply();
        dirty = true;
    }

    /** Checks that a YouFresh server answers at this address. */
    public static boolean ping(String url) {
        try {
            String r = call("GET", url, "/health", null, 6000);
            return r.contains("\"ok\"");
        } catch (Exception e) {
            return false;
        }
    }

    private static SharedPreferences prefs(Context ctx) {
        return ctx.getApplicationContext().getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    public static String get(String path, int readTimeoutMs) throws Exception {
        return call("GET", base, path, null, readTimeoutMs);
    }

    public static String post(String path, String body) throws Exception {
        return call("POST", base, path, body, 20000);
    }

    private static String call(String method, String root, String path, String body, int readTimeoutMs) throws Exception {
        if (root == null || root.isEmpty()) throw new Exception("No server address set");
        HttpURLConnection c = (HttpURLConnection) new URL(root + path).openConnection();
        c.setRequestMethod(method);
        c.setConnectTimeout(8000);
        c.setReadTimeout(readTimeoutMs);
        if (body != null) {
            c.setDoOutput(true);
            c.setRequestProperty("Content-Type", "application/json");
            try (OutputStream o = c.getOutputStream()) {
                o.write(body.getBytes(StandardCharsets.UTF_8));
            }
        }
        try {
            int code = c.getResponseCode();
            InputStream in = code >= 400 ? c.getErrorStream() : c.getInputStream();
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            if (in != null) {
                try (InputStream i = in) {
                    byte[] buf = new byte[16384];
                    int n;
                    while ((n = i.read(buf)) > 0) out.write(buf, 0, n);
                }
            }
            String s = out.toString(StandardCharsets.UTF_8.name());
            if (code >= 400) throw new Exception("HTTP " + code + " " + s);
            return s;
        } finally {
            c.disconnect();
        }
    }
}
