package li.fragniere.cursornews;

import android.content.SharedPreferences;
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
import android.os.SystemClock;
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
    private static final String PREF_LAST_MEDIA_ID = "audio-last-media-id";
    private static final String PREF_LAST_TITLE = "audio-last-title";
    private static final String PREF_LAST_SUBTITLE = "audio-last-subtitle";
    private static final String PREF_LAST_URL = "audio-last-url";
    private static final String PREF_LAST_LOOP = "audio-last-loop";
    private static final String PREF_LAST_POSITION_MS = "audio-last-position-ms";
    private static final String PREF_LAST_DURATION_MS = "audio-last-duration-ms";
    private static final String ROOT_ID = "cursor-news-root";
    private static final String LATEST_ID = "cursor-news-latest";
    private static final String RESUME_ID = "cursor-news-resume";
    private static final String LIVE_ID = "cursor-news-live";
    private static final long RESUME_REWIND_MS = 3000L;
    private static final long PROGRESS_SAVE_INTERVAL_MS = 5000L;

    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final Handler main = new Handler(Looper.getMainLooper());
    private final Map<String, AudioItem> catalog = new LinkedHashMap<>();
    private final Runnable progressSaver = new Runnable() {
        @Override
        public void run() {
            savePlaybackProgress();
            if (mediaPlayer != null) {
                main.postDelayed(this, PROGRESS_SAVE_INTERVAL_MS);
            }
        }
    };

    private MediaSession mediaSession;
    private MediaPlayer mediaPlayer;
    private AudioManager audioManager;
    private AudioFocusRequest audioFocusRequest;
    private AudioItem currentItem;
    private int playbackGeneration = 0;

    @Override
    public void onCreate() {
        super.onCreate();
        audioManager = (AudioManager) getSystemService(AUDIO_SERVICE);
        mediaSession = new MediaSession(this, "CursorNewsMediaService");
        mediaSession.setFlags(MediaSession.FLAG_HANDLES_MEDIA_BUTTONS | MediaSession.FLAG_HANDLES_TRANSPORT_CONTROLS);
        mediaSession.setCallback(new MediaSession.Callback() {
            @Override
            public void onPlay() {
                AudioItem item = currentItem != null ? currentItem : savedItem();
                playItem(item != null ? item : liveItem());
            }

            @Override
            public void onPlayFromMediaId(String mediaId, Bundle extras) {
                executor.execute(() -> {
                    refreshCatalog();
                    AudioItem item = RESUME_ID.equals(mediaId) ? savedItem() : null;
                    synchronized (catalog) {
                        if (item == null) item = catalog.get(mediaId);
                    }
                    if (item == null) {
                        AudioItem saved = savedItem();
                        if (saved != null && saved.id.equals(mediaId)) item = saved;
                    }
                    AudioItem selected = item != null && !item.browsable ? item : liveItem();
                    main.post(() -> playItem(selected));
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

            @Override
            public void onSeekTo(long pos) {
                seekTo(pos);
            }
        });
        setSessionToken(mediaSession.getSessionToken());
        catalog.put(LIVE_ID, liveItem());
        currentItem = savedItem();
        if (currentItem != null) updateMetadata(currentItem);
        setPlaybackState(currentItem != null ? PlaybackState.STATE_PAUSED : PlaybackState.STATE_NONE);
    }

    @Override
    public BrowserRoot onGetRoot(String clientPackageName, int clientUid, Bundle rootHints) {
        return new BrowserRoot(ROOT_ID, null);
    }

    @Override
    public void onLoadChildren(String parentId, Result<List<MediaBrowser.MediaItem>> result) {
        result.detach();
        executor.execute(() -> {
            List<AudioItem> refreshed = refreshCatalog();
            List<MediaBrowser.MediaItem> mediaItems = new ArrayList<>();
            if (ROOT_ID.equals(parentId)) {
                AudioItem resume = resumeItem();
                if (resume != null) mediaItems.add(toMediaItem(resume));
                AudioItem live;
                synchronized (catalog) {
                    live = catalog.get(LIVE_ID);
                }
                mediaItems.add(toMediaItem(live != null ? live : liveItem()));
                mediaItems.add(toMediaItem(folderItem()));
            } else if (LATEST_ID.equals(parentId)) {
                for (AudioItem item : refreshed) {
                    if (!item.browsable && !LIVE_ID.equals(item.id)) {
                        mediaItems.add(toMediaItem(item));
                    }
                }
            }
            main.post(() -> result.sendResult(mediaItems));
        });
    }

    @Override
    public void onDestroy() {
        savePlaybackProgress();
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
                    true,
                    false
                ));
            }
            JSONArray bulletins = manifest.optJSONArray("bulletins_by_topic");
            if (bulletins == null) {
                bulletins = manifest.optJSONArray("bulletins_by_style");
            }
            if (bulletins != null) {
                boolean includeEnglish = includeEnglishEnabled();
                for (int index = 0; index < bulletins.length(); index++) {
                    JSONObject item = bulletins.optJSONObject(index);
                    if (item == null) continue;
                    String styleKey = item.optString("style_key", "");
                    if (!includeEnglish && isEnglishBulletin(styleKey)) continue;
                    String id = item.optString("id", "bulletin-" + index);
                    String style = item.optString("style", "Bulletin");
                    String title = cleanTitle(item.optString("title", "Cursor News"));
                    String audio = item.optString("archive_audio_url", item.optString("audio_url", ""));
                    if (audio.isEmpty()) continue;
                    next.put("bulletin:" + id, new AudioItem(
                        "bulletin:" + id,
                        style,
                        title,
                        absoluteAudioUrl(audio),
                        false,
                        false
                    ));
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
        connection.setRequestProperty("User-Agent", "CursorNewsAndroidAuto/0.9");
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
        MediaDescription.Builder builder = new MediaDescription.Builder()
            .setMediaId(item.id)
            .setTitle(item.title)
            .setSubtitle(item.subtitle)
            .setIconUri(Uri.parse("android.resource://" + getPackageName() + "/" + R.drawable.ic_launcher));
        if (!item.audioUrl.isEmpty()) builder.setMediaUri(Uri.parse(item.audioUrl));
        int flags = item.browsable ? MediaBrowser.MediaItem.FLAG_BROWSABLE : MediaBrowser.MediaItem.FLAG_PLAYABLE;
        return new MediaBrowser.MediaItem(builder.build(), flags);
    }

    private void playItem(AudioItem item) {
        if (item == null) item = liveItem();
        if (item.browsable) return;
        final AudioItem playbackItem = item;
        stopPlayerOnly(true);
        if (!requestAudioFocus()) {
            mediaSession.setActive(false);
            setPlaybackState(PlaybackState.STATE_ERROR);
            return;
        }
        int generation = ++playbackGeneration;
        currentItem = playbackItem;
        long resumePositionMs = resumePositionFor(playbackItem);
        updateMetadata(playbackItem);
        setPlaybackState(PlaybackState.STATE_BUFFERING);
        try {
            MediaPlayer nextPlayer = new MediaPlayer();
            mediaPlayer = nextPlayer;
            nextPlayer.setAudioAttributes(new AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_MEDIA)
                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                .build());
            nextPlayer.setDataSource(this, Uri.parse(playbackItem.audioUrl));
            nextPlayer.setLooping(playbackItem.loop);
            nextPlayer.setOnPreparedListener(player -> {
                if (generation != playbackGeneration || player != mediaPlayer) {
                    releaseQuietly(player);
                    return;
                }
                mediaSession.setActive(true);
                seekPreparedPlayer(player, resumePositionMs);
                updateMetadata(playbackItem);
                player.start();
                savePlaybackProgress();
                startProgressUpdates();
                setPlaybackState(PlaybackState.STATE_PLAYING);
            });
            nextPlayer.setOnCompletionListener(player -> {
                if (generation == playbackGeneration && player == mediaPlayer) {
                    completePlayback();
                }
            });
            nextPlayer.setOnErrorListener((player, what, extra) -> {
                if (generation == playbackGeneration && player == mediaPlayer) {
                    handlePlaybackError();
                } else {
                    releaseQuietly(player);
                }
                return true;
            });
            nextPlayer.prepareAsync();
        } catch (Exception error) {
            stopPlayerOnly(false);
            abandonAudioFocus();
            setPlaybackState(PlaybackState.STATE_ERROR);
        }
    }

    private void pausePlayback() {
        savePlaybackProgress();
        stopPlayerOnly(false);
        mediaSession.setActive(false);
        abandonAudioFocus();
        setPlaybackState(PlaybackState.STATE_PAUSED);
    }

    private void stopPlayback() {
        savePlaybackProgress();
        stopPlayerOnly(false);
        mediaSession.setActive(false);
        abandonAudioFocus();
        setPlaybackState(PlaybackState.STATE_STOPPED);
    }

    private void completePlayback() {
        clearResumePositionForCurrent();
        stopPlayerOnly(false);
        mediaSession.setActive(false);
        abandonAudioFocus();
        setPlaybackState(PlaybackState.STATE_STOPPED);
    }

    private void stopPlayerOnly(boolean saveProgress) {
        if (saveProgress) savePlaybackProgress();
        stopProgressUpdates();
        playbackGeneration++;
        MediaPlayer player = mediaPlayer;
        mediaPlayer = null;
        releaseQuietly(player);
    }

    private boolean requestAudioFocus() {
        if (audioManager == null) return true;
        abandonAudioFocus();
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

    private void handlePlaybackError() {
        savePlaybackProgress();
        stopPlayerOnly(false);
        mediaSession.setActive(false);
        abandonAudioFocus();
        setPlaybackState(PlaybackState.STATE_ERROR);
    }

    private void releaseQuietly(MediaPlayer player) {
        if (player == null) return;
        try {
            player.reset();
        } catch (Exception ignored) {
        }
        try {
            player.release();
        } catch (Exception ignored) {
        }
    }

    private void updateMetadata(AudioItem item) {
        mediaSession.setMetadata(new MediaMetadata.Builder()
            .putString(MediaMetadata.METADATA_KEY_TITLE, item.title)
            .putString(MediaMetadata.METADATA_KEY_ARTIST, "Cursor News")
            .putString(MediaMetadata.METADATA_KEY_ALBUM, item.subtitle)
            .putLong(MediaMetadata.METADATA_KEY_DURATION, savedDurationMs())
            .build());
    }

    private void setPlaybackState(int state) {
        long actions = PlaybackState.ACTION_PLAY
            | PlaybackState.ACTION_PLAY_FROM_MEDIA_ID
            | PlaybackState.ACTION_PLAY_FROM_SEARCH
            | PlaybackState.ACTION_PAUSE
            | PlaybackState.ACTION_SEEK_TO
            | PlaybackState.ACTION_STOP;
        mediaSession.setPlaybackState(new PlaybackState.Builder()
            .setActions(actions)
            .setState(state, playbackPositionMs(), state == PlaybackState.STATE_PLAYING ? 1f : 0f, SystemClock.elapsedRealtime())
            .build());
    }

    private void seekTo(long positionMs) {
        if (mediaPlayer == null) {
            savePosition(positionMs, savedDurationMs());
            setPlaybackState(PlaybackState.STATE_PAUSED);
            return;
        }
        try {
            mediaPlayer.seekTo((int) Math.max(0L, positionMs));
            savePlaybackProgress();
            setPlaybackState(mediaPlayer.isPlaying() ? PlaybackState.STATE_PLAYING : PlaybackState.STATE_PAUSED);
        } catch (Exception ignored) {
        }
    }

    private void seekPreparedPlayer(MediaPlayer player, long positionMs) {
        if (positionMs <= 0) return;
        try {
            int duration = player.getDuration();
            int target = (int) Math.max(0L, positionMs);
            if (duration > 0) target = Math.min(target, Math.max(0, duration - 1000));
            player.seekTo(target);
        } catch (Exception ignored) {
        }
    }

    private void savePlaybackProgress() {
        if (currentItem == null) return;
        long position = playbackPositionMs();
        long duration = savedDurationMs();
        if (mediaPlayer != null) {
            try {
                duration = Math.max(0, mediaPlayer.getDuration());
            } catch (Exception ignored) {
            }
        }
        savePosition(position, duration);
    }

    private void savePosition(long positionMs, long durationMs) {
        if (currentItem == null) return;
        getSharedPreferences(PREFS, MODE_PRIVATE).edit()
            .putString(PREF_LAST_MEDIA_ID, currentItem.id)
            .putString(PREF_LAST_TITLE, currentItem.title)
            .putString(PREF_LAST_SUBTITLE, currentItem.subtitle)
            .putString(PREF_LAST_URL, currentItem.audioUrl)
            .putBoolean(PREF_LAST_LOOP, currentItem.loop)
            .putLong(PREF_LAST_POSITION_MS, Math.max(0L, positionMs))
            .putLong(PREF_LAST_DURATION_MS, Math.max(0L, durationMs))
            .apply();
    }

    private void clearResumePositionForCurrent() {
        if (currentItem == null) return;
        getSharedPreferences(PREFS, MODE_PRIVATE).edit()
            .putString(PREF_LAST_MEDIA_ID, currentItem.id)
            .putString(PREF_LAST_TITLE, currentItem.title)
            .putString(PREF_LAST_SUBTITLE, currentItem.subtitle)
            .putString(PREF_LAST_URL, currentItem.audioUrl)
            .putBoolean(PREF_LAST_LOOP, currentItem.loop)
            .putLong(PREF_LAST_POSITION_MS, 0L)
            .putLong(PREF_LAST_DURATION_MS, savedDurationMs())
            .apply();
    }

    private long playbackPositionMs() {
        if (mediaPlayer != null) {
            try {
                return Math.max(0, mediaPlayer.getCurrentPosition());
            } catch (Exception ignored) {
            }
        }
        return getSharedPreferences(PREFS, MODE_PRIVATE).getLong(PREF_LAST_POSITION_MS, 0L);
    }

    private long savedDurationMs() {
        return getSharedPreferences(PREFS, MODE_PRIVATE).getLong(PREF_LAST_DURATION_MS, 0L);
    }

    private long resumePositionFor(AudioItem item) {
        SharedPreferences prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        String savedId = prefs.getString(PREF_LAST_MEDIA_ID, "");
        String savedUrl = prefs.getString(PREF_LAST_URL, "");
        String savedTitle = prefs.getString(PREF_LAST_TITLE, "");
        long savedPosition = prefs.getLong(PREF_LAST_POSITION_MS, 0L);
        long savedDuration = prefs.getLong(PREF_LAST_DURATION_MS, 0L);
        if (!item.id.equals(savedId) || !item.audioUrl.equals(savedUrl)) return 0L;
        if (LIVE_ID.equals(item.id) && !item.title.equals(savedTitle)) return 0L;
        if (savedDuration > 0L && savedPosition > savedDuration - 8000L) return 0L;
        return Math.max(0L, savedPosition - RESUME_REWIND_MS);
    }

    private AudioItem savedItem() {
        SharedPreferences prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        String id = prefs.getString(PREF_LAST_MEDIA_ID, "");
        String url = prefs.getString(PREF_LAST_URL, "");
        if (id.isEmpty() || url.isEmpty()) return null;
        return new AudioItem(
            id,
            prefs.getString(PREF_LAST_TITLE, "Cursor News"),
            prefs.getString(PREF_LAST_SUBTITLE, "Dernier flash"),
            url,
            prefs.getBoolean(PREF_LAST_LOOP, false),
            false
        );
    }

    private AudioItem resumeItem() {
        AudioItem saved = savedItem();
        long position = playbackPositionMs();
        if (saved == null || position < 5000L) return null;
        return new AudioItem(
            RESUME_ID,
            "Reprendre - " + saved.title,
            saved.subtitle + " - " + formatTime(position),
            saved.audioUrl,
            saved.loop,
            false
        );
    }

    private void startProgressUpdates() {
        stopProgressUpdates();
        main.postDelayed(progressSaver, PROGRESS_SAVE_INTERVAL_MS);
    }

    private void stopProgressUpdates() {
        main.removeCallbacks(progressSaver);
    }

    private AudioItem firstMatch(List<AudioItem> items, String query) {
        String normalized = normalize(query);
        if (normalized.isEmpty()) return items.isEmpty() ? liveItem() : firstPlayable(items);
        for (AudioItem item : items) {
            if (!item.browsable && normalize(item.title + " " + item.subtitle).contains(normalized)) return item;
        }
        return items.isEmpty() ? liveItem() : firstPlayable(items);
    }

    private AudioItem firstPlayable(List<AudioItem> items) {
        for (AudioItem item : items) {
            if (!item.browsable) return item;
        }
        return liveItem();
    }

    private AudioItem liveItem() {
        return new AudioItem(LIVE_ID, "Flash en cours", mediaSubtitle("Cursor News"), LIVE_AUDIO_URL, true, false);
    }

    private AudioItem folderItem() {
        return new AudioItem(LATEST_ID, "Derniers flashs", "Choisir un sujet", "", false, true);
    }

    private String absoluteAudioUrl(String url) {
        if (url == null || url.isEmpty()) return LIVE_AUDIO_URL;
        if (url.startsWith("http://") || url.startsWith("https://")) return url;
        return DATA_BASE + "/" + url.replaceFirst("^/+", "");
    }

    private boolean includeEnglishEnabled() {
        return getSharedPreferences(PREFS, MODE_PRIVATE).getBoolean(PREF_INCLUDE_ENGLISH, false);
    }

    private boolean isEnglishBulletin(String styleKey) {
        return "international_english".equals(styleKey) || "un_relevant".equals(styleKey);
    }

    private String cleanTitle(String title) {
        String clean = title == null ? "" : title.replace("Cursor News - ", "").trim();
        return clean.isEmpty() ? "Cursor News" : clean;
    }

    private String mediaSubtitle(String value) {
        if (!includeEnglishEnabled()) return value;
        return value + " - English / UN actif";
    }

    private String normalize(String value) {
        return value == null ? "" : value.toLowerCase(Locale.ROOT).trim();
    }

    private String formatTime(long milliseconds) {
        long seconds = Math.max(0L, milliseconds / 1000L);
        return String.format(Locale.FRANCE, "%d:%02d", seconds / 60L, seconds % 60L);
    }

    private static final class AudioItem {
        final String id;
        final String title;
        final String subtitle;
        final String audioUrl;
        final boolean loop;
        final boolean browsable;

        AudioItem(String id, String title, String subtitle, String audioUrl, boolean loop, boolean browsable) {
            this.id = id;
            this.title = title;
            this.subtitle = subtitle;
            this.audioUrl = audioUrl;
            this.loop = loop;
            this.browsable = browsable;
        }
    }
}
