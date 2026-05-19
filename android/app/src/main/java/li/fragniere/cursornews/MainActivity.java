package li.fragniere.cursornews;

import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.media.MediaPlayer;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.Editable;
import android.text.TextWatcher;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.AdapterView;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Spinner;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.text.Normalizer;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MainActivity extends Activity {
    private static final String DATA_BASE = "https://storage.googleapis.com/cursor-news-radio-20260517-audio/current";
    private static final String PREFS = "cursor-news";
    private static final String READ_IDS = "read-ids";

    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final Handler main = new Handler(Looper.getMainLooper());
    private final List<NewsArticle> articles = new ArrayList<>();
    private final Set<String> readIds = new HashSet<>();
    private final DateTimeFormatter dateFormat = DateTimeFormatter.ofPattern("d MMM HH:mm", Locale.FRANCE)
        .withZone(ZoneId.of("Europe/Zurich"));

    private LinearLayout list;
    private TextView status;
    private TextView resultTitle;
    private TextView currentFlash;
    private Button playButton;
    private EditText search;
    private Spinner period;
    private CheckBox hideRead;

    private String query = "";
    private String periodFilter = "24h";
    private String audioUrl = DATA_BASE + "/live.mp3";
    private MediaPlayer mediaPlayer;
    private boolean audioPreparing = false;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        readIds.addAll(getSharedPreferences(PREFS, MODE_PRIVATE).getStringSet(READ_IDS, new HashSet<>()));
        buildUi();
        loadData();
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        executor.shutdownNow();
        if (mediaPlayer != null) {
            mediaPlayer.release();
            mediaPlayer = null;
        }
    }

    private void buildUi() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Color.rgb(246, 245, 242));

        root.addView(buildHeader());

        ScrollView scroll = new ScrollView(this);
        LinearLayout body = new LinearLayout(this);
        body.setOrientation(LinearLayout.VERTICAL);
        body.setPadding(dp(14), dp(12), dp(14), dp(24));
        scroll.addView(body);

        body.addView(buildFilters());

        resultTitle = label("Actualités", 22, Typeface.BOLD, Color.rgb(23, 26, 29));
        LinearLayout.LayoutParams titleParams = new LinearLayout.LayoutParams(match(), wrap());
        titleParams.setMargins(0, dp(18), 0, dp(8));
        body.addView(resultTitle, titleParams);

        list = new LinearLayout(this);
        list.setOrientation(LinearLayout.VERTICAL);
        body.addView(list, new LinearLayout.LayoutParams(match(), wrap()));

        root.addView(scroll, new LinearLayout.LayoutParams(match(), 0, 1));
        setContentView(root);
    }

    private View buildHeader() {
        LinearLayout header = new LinearLayout(this);
        header.setOrientation(LinearLayout.VERTICAL);
        header.setPadding(dp(16), dp(14), dp(16), dp(12));
        header.setBackgroundColor(Color.WHITE);

        LinearLayout top = new LinearLayout(this);
        top.setGravity(Gravity.CENTER_VERTICAL);
        top.setOrientation(LinearLayout.HORIZONTAL);

        LinearLayout titleBlock = new LinearLayout(this);
        titleBlock.setOrientation(LinearLayout.VERTICAL);
        titleBlock.addView(label("Suisse romande", 12, Typeface.BOLD, Color.rgb(161, 52, 24)));
        titleBlock.addView(label("Cursor News", 30, Typeface.BOLD, Color.rgb(23, 26, 29)));
        top.addView(titleBlock, new LinearLayout.LayoutParams(0, wrap(), 1));

        Button refresh = new Button(this);
        refresh.setText("Actualiser");
        refresh.setOnClickListener(v -> loadData());
        top.addView(refresh);
        header.addView(top);

        status = label("Chargement...", 13, Typeface.BOLD, Color.rgb(15, 118, 110));
        header.addView(status);

        LinearLayout player = new LinearLayout(this);
        player.setGravity(Gravity.CENTER_VERTICAL);
        player.setOrientation(LinearLayout.HORIZONTAL);
        player.setPadding(0, dp(8), 0, 0);

        currentFlash = label("Flash en cours", 14, Typeface.BOLD, Color.rgb(23, 26, 29));
        player.addView(currentFlash, new LinearLayout.LayoutParams(0, wrap(), 1));

        playButton = new Button(this);
        playButton.setText("Lire");
        playButton.setOnClickListener(v -> toggleAudio());
        player.addView(playButton);

        header.addView(player);
        return header;
    }

    private View buildFilters() {
        LinearLayout filters = panel();
        filters.setOrientation(LinearLayout.VERTICAL);

        search = new EditText(this);
        search.setSingleLine(true);
        search.setHint("Recherche: sujet, lieu, source...");
        search.addTextChangedListener(new TextWatcher() {
            @Override public void beforeTextChanged(CharSequence s, int start, int count, int after) {}
            @Override public void onTextChanged(CharSequence s, int start, int before, int count) {
                query = s.toString();
                renderArticles();
            }
            @Override public void afterTextChanged(Editable s) {}
        });
        filters.addView(search, new LinearLayout.LayoutParams(match(), wrap()));

        LinearLayout row = new LinearLayout(this);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setPadding(0, dp(10), 0, 0);

        period = new Spinner(this);
        ArrayAdapter<String> adapter = new ArrayAdapter<>(this, android.R.layout.simple_spinner_item, new String[] {
            "24 dernières heures", "Aujourd'hui", "7 derniers jours", "Tout"
        });
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        period.setAdapter(adapter);
        period.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
            @Override public void onItemSelected(AdapterView<?> parent, View view, int position, long id) {
                periodFilter = position == 1 ? "today" : position == 2 ? "7d" : position == 3 ? "all" : "24h";
                renderArticles();
            }
            @Override public void onNothingSelected(AdapterView<?> parent) {}
        });
        row.addView(period, new LinearLayout.LayoutParams(0, wrap(), 1));

        hideRead = new CheckBox(this);
        hideRead.setText("Masquer lus");
        hideRead.setChecked(true);
        hideRead.setOnCheckedChangeListener((buttonView, isChecked) -> renderArticles());
        row.addView(hideRead);
        filters.addView(row);

        return filters;
    }

    private void loadData() {
        status.setText("Chargement...");
        executor.execute(() -> {
            try {
                JSONObject manifest = fetchJson(DATA_BASE + "/manifest.json");
                JSONObject news = fetchJson(DATA_BASE + "/news.json");
                List<NewsArticle> loaded = parseArticles(news.optJSONArray("articles"));
                main.post(() -> {
                    applyManifest(manifest);
                    articles.clear();
                    articles.addAll(loaded);
                    status.setText(articles.size() + " news chargées");
                    renderArticles();
                });
            } catch (Exception error) {
                main.post(() -> {
                    status.setText("News indisponibles");
                    Toast.makeText(this, "Impossible de charger Cursor News", Toast.LENGTH_LONG).show();
                });
            }
        });
    }

    private void applyManifest(JSONObject manifest) {
        JSONObject current = manifest.optJSONObject("current");
        if (current == null) {
            currentFlash.setText("Aucun flash audio");
            return;
        }
        String nextAudioUrl = current.optString("audio_url", DATA_BASE + "/live.mp3");
        if (!nextAudioUrl.equals(audioUrl) && mediaPlayer != null) {
            mediaPlayer.release();
            mediaPlayer = null;
            playButton.setText("Lire");
        }
        audioUrl = nextAudioUrl;
        String style = current.optString("style", "Bulletin");
        String title = current.optString("title", "Cursor News");
        String cleanTitle = title.replace("Cursor News - ", "").trim();
        currentFlash.setText(cleanTitle.equalsIgnoreCase(style) ? "Flash en cours - " + style : style + " - " + cleanTitle);
    }

    private List<NewsArticle> parseArticles(JSONArray array) {
        List<NewsArticle> parsed = new ArrayList<>();
        if (array == null) return parsed;
        for (int index = 0; index < array.length(); index++) {
            JSONObject item = array.optJSONObject(index);
            if (item == null) continue;
            NewsArticle article = new NewsArticle();
            article.id = item.optString("id");
            article.title = item.optString("title");
            article.source = item.optString("source_name");
            article.region = item.optString("region");
            article.url = item.optString("url");
            article.summary = item.optString("summary");
            article.publishedAt = item.optString("published_at", item.optString("scraped_at"));
            article.timestamp = parseDate(article.publishedAt);
            article.tension = item.optInt("tension", 0);
            article.priority = item.optInt("priority", 0);
            article.childFriendly = item.optBoolean("child_friendly", false);
            parsed.add(article);
        }
        return parsed;
    }

    private void renderArticles() {
        if (list == null) return;
        list.removeAllViews();
        List<NewsArticle> filtered = filteredArticles();
        resultTitle.setText(filtered.size() + " actualité" + (filtered.size() > 1 ? "s" : ""));
        if (filtered.isEmpty()) {
            TextView empty = label("Aucune actualité ne correspond aux filtres.", 15, Typeface.NORMAL, Color.rgb(104, 112, 122));
            empty.setPadding(dp(14), dp(18), dp(14), dp(18));
            list.addView(empty);
            return;
        }
        int count = Math.min(filtered.size(), 80);
        for (int index = 0; index < count; index++) {
            list.addView(articleView(filtered.get(index)));
        }
    }

    private List<NewsArticle> filteredArticles() {
        long now = System.currentTimeMillis();
        String normalizedQuery = normalize(query);
        List<NewsArticle> filtered = new ArrayList<>();
        for (NewsArticle article : articles) {
            if (hideRead.isChecked() && readIds.contains(article.id)) continue;
            if (!matchesPeriod(article, now)) continue;
            if (!normalizedQuery.isEmpty()) {
                String haystack = normalize(article.title + " " + article.summary + " " + article.source + " " + article.region);
                if (!haystack.contains(normalizedQuery)) continue;
            }
            filtered.add(article);
        }
        return filtered;
    }

    private boolean matchesPeriod(NewsArticle article, long now) {
        if ("all".equals(periodFilter)) return true;
        if (article.timestamp <= 0) return false;
        if ("24h".equals(periodFilter)) return article.timestamp >= now - 24L * 60L * 60L * 1000L;
        if ("7d".equals(periodFilter)) return article.timestamp >= now - 7L * 24L * 60L * 60L * 1000L;
        if ("today".equals(periodFilter)) {
            ZoneId zurich = ZoneId.of("Europe/Zurich");
            return Instant.ofEpochMilli(article.timestamp).atZone(zurich).toLocalDate()
                .equals(Instant.ofEpochMilli(now).atZone(zurich).toLocalDate());
        }
        return true;
    }

    private View articleView(NewsArticle article) {
        LinearLayout card = panel();
        card.setOrientation(LinearLayout.VERTICAL);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(match(), wrap());
        params.setMargins(0, 0, 0, dp(10));
        card.setLayoutParams(params);
        if (readIds.contains(article.id)) card.setAlpha(0.72f);

        TextView title = label(article.title, 18, Typeface.BOLD, Color.rgb(23, 26, 29));
        title.setOnClickListener(v -> {
            setRead(article.id, true);
            if (!article.url.isEmpty()) startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(article.url)));
        });
        card.addView(title);

        String meta = article.source + " - " + dateFormat.format(Instant.ofEpochMilli(Math.max(0, article.timestamp)));
        TextView metaView = label(meta, 12, Typeface.BOLD, Color.rgb(104, 112, 122));
        card.addView(metaView);

        TextView summary = label(article.summary, 14, Typeface.NORMAL, Color.rgb(70, 76, 84));
        summary.setPadding(0, dp(6), 0, dp(8));
        card.addView(summary);

        TextView tags = label(article.region + "  tension " + article.tension + "/10  focus " + article.priority + (article.childFriendly ? "  enfants" : ""), 12, Typeface.BOLD, Color.rgb(15, 118, 110));
        card.addView(tags);

        CheckBox read = new CheckBox(this);
        read.setText("Lu");
        read.setChecked(readIds.contains(article.id));
        read.setOnCheckedChangeListener((buttonView, isChecked) -> setRead(article.id, isChecked));
        card.addView(read);
        return card;
    }

    private void setRead(String id, boolean read) {
        if (id == null || id.isEmpty()) return;
        if (read) readIds.add(id);
        else readIds.remove(id);
        SharedPreferences.Editor editor = getSharedPreferences(PREFS, MODE_PRIVATE).edit();
        editor.putStringSet(READ_IDS, new HashSet<>(readIds));
        editor.apply();
        renderArticles();
    }

    private void toggleAudio() {
        try {
            if (mediaPlayer != null && mediaPlayer.isPlaying()) {
                mediaPlayer.pause();
                playButton.setText("Lire");
                return;
            }
            if (mediaPlayer != null && !audioPreparing) {
                mediaPlayer.start();
                playButton.setText("Pause");
                return;
            }
            audioPreparing = true;
            playButton.setText("...");
            mediaPlayer = new MediaPlayer();
            mediaPlayer.setDataSource(this, Uri.parse(audioUrl));
            mediaPlayer.setOnPreparedListener(player -> {
                audioPreparing = false;
                player.start();
                playButton.setText("Pause");
            });
            mediaPlayer.setOnErrorListener((player, what, extra) -> {
                audioPreparing = false;
                playButton.setText("Lire");
                Toast.makeText(this, "Audio indisponible", Toast.LENGTH_SHORT).show();
                return true;
            });
            mediaPlayer.prepareAsync();
        } catch (Exception error) {
            audioPreparing = false;
            playButton.setText("Lire");
            Toast.makeText(this, "Audio indisponible", Toast.LENGTH_SHORT).show();
        }
    }

    private JSONObject fetchJson(String url) throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL(url + "?v=" + System.currentTimeMillis()).openConnection();
        connection.setConnectTimeout(12000);
        connection.setReadTimeout(12000);
        connection.setRequestProperty("User-Agent", "CursorNewsAndroid/0.1");
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(connection.getInputStream()))) {
            StringBuilder builder = new StringBuilder();
            String line;
            while ((line = reader.readLine()) != null) builder.append(line);
            return new JSONObject(builder.toString());
        } finally {
            connection.disconnect();
        }
    }

    private long parseDate(String value) {
        if (value == null || value.isEmpty() || "null".equals(value)) return 0;
        try {
            return OffsetDateTime.parse(value).toInstant().toEpochMilli();
        } catch (Exception ignored) {
            try {
                return Instant.parse(value).toEpochMilli();
            } catch (Exception ignoredAgain) {
                return 0;
            }
        }
    }

    private String normalize(String value) {
        String normalized = Normalizer.normalize(value == null ? "" : value, Normalizer.Form.NFD);
        return normalized.replaceAll("\\p{InCombiningDiacriticalMarks}+", "").toLowerCase(Locale.FRANCE).trim();
    }

    private LinearLayout panel() {
        LinearLayout view = new LinearLayout(this);
        view.setPadding(dp(14), dp(12), dp(14), dp(12));
        GradientDrawable bg = new GradientDrawable();
        bg.setColor(Color.WHITE);
        bg.setCornerRadius(dp(8));
        bg.setStroke(dp(1), Color.rgb(217, 214, 207));
        view.setBackground(bg);
        return view;
    }

    private TextView label(String value, int sp, int style, int color) {
        TextView text = new TextView(this);
        text.setText(value);
        text.setTextSize(sp);
        text.setTextColor(color);
        text.setTypeface(Typeface.DEFAULT, style);
        text.setLineSpacing(0, 1.08f);
        return text;
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private int match() {
        return ViewGroup.LayoutParams.MATCH_PARENT;
    }

    private int wrap() {
        return ViewGroup.LayoutParams.WRAP_CONTENT;
    }

    private static class NewsArticle {
        String id = "";
        String title = "";
        String source = "";
        String region = "";
        String url = "";
        String summary = "";
        String publishedAt = "";
        long timestamp = 0;
        int tension = 0;
        int priority = 0;
        boolean childFriendly = false;
    }
}
