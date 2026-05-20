package li.fragniere.cursornews;

import android.media.AudioAttributes;
import android.media.AudioFocusRequest;
import android.media.AudioManager;
import android.media.MediaDescription;
import android.media.MediaMetadata;
import android.media.MediaPlayer;
import android.media.browse.MediaBrowser;
import android.media.session.MediaSession;
import android.media.session.PlaybackState;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.service.media.MediaBrowserService;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class CursorNewsMediaService extends MediaBrowserService {
    private static final String DATA_BASE = "https://storage.googleapis.com/cursor-news-radio-20260517-audio/current";
    private static final String MANIFEST_URL = DATA_BASE + "/manifest.json";
    private static final String LIVE_AUDIO_URL = DATA_BASE + "/live.mp3";
    private static final String PREFS = "cursor-news";
    private static final String PREF_INCLUDE_ENGLISH = "filter-include-english";
    private static final String ROOT_ID = "cursor-news-root";
    private static final String LIVE_ID = "cursor-news-live";

    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final Handler main = new Handler(Looper.getMainLooper());
    private final Map<String, AudioItem> catalog = new LinkedHashMap<>();

    private MediaSession mediaSession;
    private MediaPlayer mediaPlayer;
    private AudioManager audioManager;
    private AudioFocusRequest audioFocusRequest;
    private AudioItem currentItem;

    @Override
    public void onCreate() {
        super.onCreate();
        audioManager = (AudioManager) getSystemService(AUDIO_SERVICE);
        mediaSession = new MediaSession(this, "CursorNewsMediaService");
        mediaSession.setFlags(MediaSession.FLAG_HANDLES_MEDIA_BUTTONS | MediaSession.FLAG_HANDLES_TRANSPORT_CONTROLS);
        mediaSession.setCallback(new MediaSession.Callback() {
            @Override
            public void onPlay() {
                playItem(currentItem != null ? currentItem : liveItem());
            }

            @Override
            public void onPlayFromMediaId(String mediaId, Bundle extras) {
                executor.execute(() -> {
                    refreshCatalog();
                    AudioItem item = catalog.get(mediaId);
                    main.post(() -> playItem(item != null ? item : liveItem()));
                });
            }

            @Override
            public void onPlayFromSearch(String query, Bundle extras) {
                executor.execute(() -> {
                    List<AudioItem> items = refreshCatalog();
                    AudioItem match = firstMatch(items, query);
                    main.post(() -> playItem(match != null ? match : liveItem()));
                });
            }

            @Override
            public void onPause() {
                pausePlayback();
            }

            @Override
            public void onStop() {
                stopPlayback();
            }
        });
        setSessionToken(mediaSession.getSessionToken());
        catalog.put(LIVE_ID, liveItem());
        setPlaybackState(PlaybackState.STATE_NONE);
    }

    @Override
    public BrowserRoot onGetRoot(String clientPackageName, int clientUid, Bundle rootHints) {
        return new BrowserRoot(ROOT_ID, null);
    }

    @Override
    public void onLoadChildren(String parentId, Result<List<MediaBrowser.MediaItem>> result) {
        result.detach();
        executor.execute(() -> {
            List<AudioItem> items = ROOT_ID.equals(parentId) ? refreshCatalog() : new ArrayList<>();
            List<MediaBrowser.MediaItem> mediaItems = new ArrayList<>();
            for (AudioItem item : items) {
                mediaItems.add(toMediaItem(item));
            }
            main.post(() -> result.sendResult(mediaItems));
        });
    }

    @Override
    public void onDestroy() {
        stopPlayback();
        executor.shutdownNow();
        mediaSession.release();
        super.onDestroy();
    }

    private List<AudioItem> refreshCatalog() {
        LinkedHashMap<String, AudioItem> next = new LinkedHashMap<>();
        AudioItem live = liveItem();
        next.put(live.id, live);
        try {
            JSONObject manifest = fetchJson(MANIFEST_URL);
            JSONObject current = manifest.optJSONObject("current");
            if (current != null) {
                String style = current.optString("style", "Flash en cours");
                String title = current.optString("title", "Cursor News");
                next.put(LIVE_ID, new AudioItem(
                    LIVE_ID,
                    "Flash en cours - " + style,
                    mediaSubtitle(cleanTitle(title)),
                    absoluteAudioUrl(current.optString("audio_url", LIVE_AUDIO_URL)),
                    true
                ));
            }
            JSONArray bulletins = manifest.optJSONArray("bulletins_by_topic");
            if (bulletins == null) {
                bulletins = manifest.optJSONArray("bulletins_by_style");
            }
            if (bulletins != null) {
                for (int index = 0; index < bulletins.length(); index++) {
                    JSONObject item = bulletins.optJSONObject(index);
                    if (item == null) continue;
                    String id = item.optString("id", "bulletin-" + index);
                    String style = item.optString("style", "Bulletin");
                    String title = cleanTitle(item.optString("title", "Cursor News"));
                    String audio = item.optString("archive_audio_url", item.optString("audio_url", ""));
                    if (audio.isEmpty()) continue;
                    next.put("bulletin:" + id, new AudioItem("bulletin:" + id, style, title, absoluteAudioUrl(audio), false));
                }
            }
        } catch (Exception ignored) {
        }
        synchronized (catalog) {
            catalog.clear();
            catalog.putAll(next);
        }
        return new ArrayList<>(next.values());
    }

    private JSONObject fetchJson(String url) throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL(url + "?v=" + System.currentTimeMillis()).openConnection();
        connection.setConnectTimeout(12000);
        connection.setReadTimeout(12000);
        connection.setRequestProperty("User-Agent", "CursorNewsAndroidAuto/0.5");
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(connection.getInputStream()))) {
            StringBuilder builder = new StringBuilder();
            String line;
            while ((line = reader.readLine()) != null) builder.append(line);
            return new JSONObject(builder.toString());
        } finally {
            connection.disconnect();
        }
    }

    private MediaBrowser.MediaItem toMediaItem(AudioItem item) {
        MediaDescription description = new MediaDescription.Builder()
            .setMediaId(item.id)
            .setTitle(item.title)
            .setSubtitle(item.subtitle)
            .setMediaUri(Uri.parse(item.audioUrl))
            .setIconUri(Uri.parse("android.resource://" + getPackageName() + "/" + R.drawable.ic_launcher))
            .build();
        return new MediaBrowser.MediaItem(description, MediaBrowser.MediaItem.FLAG_PLAYABLE);
    }

    private void playItem(AudioItem item) {
        if (item == null) item = liveItem();
        if (!requestAudioFocus()) {
            setPlaybackState(PlaybackState.STATE_ERROR);
            return;
        }
        stopPlayerOnly();
        currentItem = item;
        updateMetadata(item);
        setPlaybackState(PlaybackState.STATE_BUFFERING);
        try {
            MediaPlayer nextPlayer = new MediaPlayer();
            nextPlayer.setAudioAttributes(new AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_MEDIA)
                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                .build());
            nextPlayer.setDataSource(this, Uri.parse(item.audioUrl));
            nextPlayer.setLooping(item.loop);
            nextPlayer.setOnPreparedListener(player -> {
                mediaPlayer = player;
                mediaSession.setActive(true);
                player.start();
                setPlaybackState(PlaybackState.STATE_PLAYING);
            });
            nextPlayer.setOnCompletionListener(player -> setPlaybackState(PlaybackState.STATE_PAUSED));
            nextPlayer.setOnErrorListener((player, what, extra) -> {
                setPlaybackState(PlaybackState.STATE_ERROR);
                return true;
            });
            nextPlayer.prepareAsync();
        } catch (Exception error) {
            setPlaybackState(PlaybackState.STATE_ERROR);
        }
    }

    private void pausePlayback() {
        if (mediaPlayer != null && mediaPlayer.isPlaying()) {
            mediaPlayer.pause();
        }
        setPlaybackState(PlaybackState.STATE_PAUSED);
    }

    private void stopPlayback() {
        stopPlayerOnly();
        mediaSession.setActive(false);
        abandonAudioFocus();
        setPlaybackState(PlaybackState.STATE_STOPPED);
    }

    private void stopPlayerOnly() {
        if (mediaPlayer != null) {
            mediaPlayer.release();
            mediaPlayer = null;
        }
    }

    private boolean requestAudioFocus() {
        if (audioManager == null) return true;
        audioFocusRequest = new AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN)
            .setAudioAttributes(new AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_MEDIA)
                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                .build())
            .setOnAudioFocusChangeListener(focusChange -> {
                if (focusChange == AudioManager.AUDIOFOCUS_LOSS) stopPlayback();
                if (focusChange == AudioManager.AUDIOFOCUS_LOSS_TRANSIENT) pausePlayback();
            })
            .build();
        return audioManager.requestAudioFocus(audioFocusRequest) == AudioManager.AUDIOFOCUS_REQUEST_GRANTED;
    }

    private void abandonAudioFocus() {
        if (audioManager != null && audioFocusRequest != null) {
            audioManager.abandonAudioFocusRequest(audioFocusRequest);
            audioFocusRequest = null;
        }
    }

    private void updateMetadata(AudioItem item) {
        mediaSession.setMetadata(new MediaMetadata.Builder()
            .putString(MediaMetadata.METADATA_KEY_TITLE, item.title)
            .putString(MediaMetadata.METADATA_KEY_ARTIST, "Cursor News")
            .putString(MediaMetadata.METADATA_KEY_ALBUM, item.subtitle)
            .build());
    }

    private void setPlaybackState(int state) {
        long actions = PlaybackState.ACTION_PLAY
            | PlaybackState.ACTION_PLAY_FROM_MEDIA_ID
            | PlaybackState.ACTION_PLAY_FROM_SEARCH
            | PlaybackState.ACTION_PAUSE
            | PlaybackState.ACTION_STOP;
        mediaSession.setPlaybackState(new PlaybackState.Builder()
            .setActions(actions)
            .setState(state, PlaybackState.PLAYBACK_POSITION_UNKNOWN, state == PlaybackState.STATE_PLAYING ? 1f : 0f)
            .build());
    }

    private AudioItem firstMatch(List<AudioItem> items, String query) {
        String normalized = normalize(query);
        if (normalized.isEmpty()) return items.isEmpty() ? liveItem() : items.get(0);
        for (AudioItem item : items) {
            if (normalize(item.title + " " + item.subtitle).contains(normalized)) return item;
        }
        return items.isEmpty() ? liveItem() : items.get(0);
    }

    private AudioItem liveItem() {
        return new AudioItem(LIVE_ID, "Flash en cours", mediaSubtitle("Cursor News"), LIVE_AUDIO_URL, true);
    }

    private String absoluteAudioUrl(String url) {
        if (url == null || url.isEmpty()) return LIVE_AUDIO_URL;
        if (url.startsWith("http://") || url.startsWith("https://")) return url;
        return DATA_BASE + "/" + url.replaceFirst("^/+", "");
    }

    private String cleanTitle(String title) {
        String clean = title == null ? "" : title.replace("Cursor News - ", "").trim();
        return clean.isEmpty() ? "Cursor News" : clean;
    }

    private String mediaSubtitle(String value) {
        if (!getSharedPreferences(PREFS, MODE_PRIVATE).getBoolean(PREF_INCLUDE_ENGLISH, false)) return value;
        return value + " - English / UN actif";
    }

    private String normalize(String value) {
        return value == null ? "" : value.toLowerCase(Locale.ROOT).trim();
    }

    private static final class AudioItem {
        final String id;
        final String title;
        final String subtitle;
        final String audioUrl;
        final boolean loop;

        AudioItem(String id, String title, String subtitle, String audioUrl, boolean loop) {
            this.id = id;
            this.title = title;
            this.subtitle = subtitle;
            this.audioUrl = audioUrl;
            this.loop = loop;
        }
    }
}
