package li.fragniere.cursornews;

import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.res.ColorStateList;
import android.content.res.Configuration;
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
import android.view.Window;
import android.view.WindowInsets;
import android.widget.AdapterView;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.SeekBar;
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
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

@SuppressWarnings("deprecation")
public class MainActivity extends Activity {
    private static final String DATA_BASE = "https://storage.googleapis.com/cursor-news-radio-20260517-audio/current";
    private static final String PREFS = "cursor-news";
    private static final String READ_IDS = "read-ids";

    private boolean darkMode;
    private int bgColor;
    private int panelColor;
    private int inkColor;
    private int mutedColor;
    private int lineColor;
    private int accentColor;
    private int accentAltColor;
    private int softColor;
    private int summaryColor;
    private int primaryButtonTextColor;

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
    private TextView tensionValue;
    private TextView priorityValue;
    private LinearLayout advancedFilters;
    private Button playButton;
    private Button advancedButton;
    private EditText search;
    private Spinner period;
    private Spinner region;
    private Spinner source;
    private Spinner sort;
    private CheckBox hideRead;
    private CheckBox hideSports;
    private CheckBox childOnly;
    private SeekBar tension;
    private SeekBar priority;

    private String query = "";
    private String periodFilter = "24h";
    private String regionFilter = "all";
    private String sourceFilter = "all";
    private String sortFilter = "newest";
    private int maxTension = 10;
    private int minPriority = 0;
    private boolean advancedOpen = false;
    private String audioUrl = DATA_BASE + "/live.mp3";
    private MediaPlayer mediaPlayer;
    private boolean audioPreparing = false;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        applyThemeColors();
        configureSystemBars();
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

    private void configureSystemBars() {
        Window window = getWindow();
        window.setStatusBarColor(bgColor);
        window.setNavigationBarColor(bgColor);
        window.getDecorView().setSystemUiVisibility(darkMode ? 0 :
            View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR
        );
    }

    private void applyThemeColors() {
        int nightMode = getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK;
        darkMode = nightMode == Configuration.UI_MODE_NIGHT_YES;
        if (darkMode) {
            bgColor = Color.rgb(18, 22, 24);
            panelColor = Color.rgb(26, 31, 34);
            inkColor = Color.rgb(240, 243, 244);
            mutedColor = Color.rgb(170, 178, 184);
            lineColor = Color.rgb(61, 68, 72);
            accentColor = Color.rgb(76, 196, 184);
            accentAltColor = Color.rgb(255, 146, 95);
            softColor = Color.rgb(28, 50, 49);
            summaryColor = Color.rgb(208, 214, 218);
            primaryButtonTextColor = Color.rgb(5, 35, 33);
        } else {
            bgColor = Color.rgb(246, 245, 242);
            panelColor = Color.WHITE;
            inkColor = Color.rgb(23, 26, 29);
            mutedColor = Color.rgb(104, 112, 122);
            lineColor = Color.rgb(217, 214, 207);
            accentColor = Color.rgb(15, 118, 110);
            accentAltColor = Color.rgb(161, 52, 24);
            softColor = Color.rgb(238, 247, 245);
            summaryColor = Color.rgb(70, 76, 84);
            primaryButtonTextColor = Color.WHITE;
        }
    }

    private void buildUi() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(bgColor);
        root.setOnApplyWindowInsetsListener((view, insets) -> {
            view.setPadding(0, insets.getSystemWindowInsetTop(), 0, insets.getSystemWindowInsetBottom());
            return insets;
        });

        root.addView(buildHeader());

        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(false);
        LinearLayout body = new LinearLayout(this);
        body.setOrientation(LinearLayout.VERTICAL);
        body.setPadding(dp(14), dp(12), dp(14), dp(32));
        scroll.addView(body);

        body.addView(buildFilters());

        resultTitle = label("Actualités", 22, Typeface.BOLD, inkColor);
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
        header.setPadding(dp(14), dp(12), dp(14), dp(12));
        header.setBackgroundColor(panelColor);
        header.setElevation(dp(2));

        LinearLayout top = new LinearLayout(this);
        top.setGravity(Gravity.CENTER_VERTICAL);
        top.setOrientation(LinearLayout.HORIZONTAL);

        ImageView logo = new ImageView(this);
        logo.setImageResource(R.drawable.logo);
        logo.setAdjustViewBounds(true);
        logo.setScaleType(ImageView.ScaleType.FIT_CENTER);
        LinearLayout.LayoutParams logoParams = new LinearLayout.LayoutParams(dp(96), dp(64));
        logoParams.setMargins(0, 0, dp(12), 0);
        top.addView(logo, logoParams);

        LinearLayout titleBlock = new LinearLayout(this);
        titleBlock.setOrientation(LinearLayout.VERTICAL);
        titleBlock.addView(label("Suisse romande", 12, Typeface.BOLD, accentAltColor));
        titleBlock.addView(label("Cursor News", 28, Typeface.BOLD, inkColor));
        top.addView(titleBlock, new LinearLayout.LayoutParams(0, wrap(), 1));

        Button refresh = actionButton("Actualiser", false);
        refresh.setOnClickListener(v -> loadData());
        top.addView(refresh);
        header.addView(top);

        status = label("Chargement...", 13, Typeface.BOLD, accentColor);
        LinearLayout.LayoutParams statusParams = new LinearLayout.LayoutParams(match(), wrap());
        statusParams.setMargins(0, dp(6), 0, dp(8));
        header.addView(status, statusParams);

        LinearLayout player = roundedPanel(softColor, lineColor);
        player.setGravity(Gravity.CENTER_VERTICAL);
        player.setOrientation(LinearLayout.HORIZONTAL);
        player.setPadding(dp(12), dp(8), dp(10), dp(8));

        currentFlash = label("Flash en cours", 14, Typeface.BOLD, inkColor);
        player.addView(currentFlash, new LinearLayout.LayoutParams(0, wrap(), 1));

        playButton = actionButton("Lire", true);
        playButton.setOnClickListener(v -> toggleAudio());
        player.addView(playButton);

        header.addView(player, new LinearLayout.LayoutParams(match(), wrap()));
        return header;
    }

    private View buildFilters() {
        LinearLayout filters = roundedPanel(panelColor, lineColor);
        filters.setOrientation(LinearLayout.VERTICAL);
        filters.setPadding(dp(14), dp(12), dp(14), dp(12));

        advancedButton = actionButton("Filtres et recherche", false);
        advancedButton.setOnClickListener(v -> toggleAdvancedFilters());
        filters.addView(advancedButton, new LinearLayout.LayoutParams(match(), wrap()));

        advancedFilters = new LinearLayout(this);
        advancedFilters.setOrientation(LinearLayout.VERTICAL);
        advancedFilters.setVisibility(View.GONE);
        filters.addView(advancedFilters);

        search = new EditText(this);
        search.setSingleLine(true);
        search.setHint("Recherche: sujet, lieu, source...");
        search.setTextColor(inkColor);
        search.setHintTextColor(mutedColor);
        search.addTextChangedListener(new TextWatcher() {
            @Override public void beforeTextChanged(CharSequence s, int start, int count, int after) {}
            @Override public void onTextChanged(CharSequence s, int start, int before, int count) {
                query = s.toString();
                renderArticles();
            }
            @Override public void afterTextChanged(Editable s) {}
        });
        LinearLayout.LayoutParams searchParams = new LinearLayout.LayoutParams(match(), wrap());
        searchParams.setMargins(0, dp(10), 0, 0);
        advancedFilters.addView(search, searchParams);

        period = spinner();
        region = spinner();
        source = spinner();
        sort = spinner();
        fillSpinner(period, "24 dernières heures", "Aujourd'hui", "7 derniers jours", "Tout");
        fillSpinner(region, "Toutes les régions");
        fillSpinner(source, "Toutes les sources");
        fillSpinner(sort, "Plus récent", "Focus romand", "Plus calme", "Plus tendu");

        hideRead = checkbox("Masquer lus", true);
        LinearLayout quickRow = new LinearLayout(this);
        quickRow.setGravity(Gravity.CENTER_VERTICAL);
        quickRow.setOrientation(LinearLayout.HORIZONTAL);
        LinearLayout.LayoutParams quickParams = new LinearLayout.LayoutParams(match(), wrap());
        quickParams.setMargins(0, dp(10), 0, 0);
        quickRow.setLayoutParams(quickParams);
        quickRow.addView(field("Période", period), new LinearLayout.LayoutParams(0, wrap(), 1));
        LinearLayout.LayoutParams hideReadParams = new LinearLayout.LayoutParams(0, wrap(), 1);
        hideReadParams.setMargins(dp(12), dp(18), 0, 0);
        quickRow.addView(hideRead, hideReadParams);
        advancedFilters.addView(quickRow);

        advancedFilters.addView(twoColumnRow(field("Région", region), field("Source", source)));
        advancedFilters.addView(twoColumnRow(field("Tri", sort), label("Les curseurs affinent la sélection publiée.", 12, Typeface.BOLD, mutedColor)));

        period.setOnItemSelectedListener(listener(position -> {
            periodFilter = position == 1 ? "today" : position == 2 ? "7d" : position == 3 ? "all" : "24h";
            renderArticles();
        }));
        region.setOnItemSelectedListener(listener(position -> {
            regionFilter = position <= 0 ? "all" : String.valueOf(region.getSelectedItem());
            renderArticles();
        }));
        source.setOnItemSelectedListener(listener(position -> {
            sourceFilter = position <= 0 ? "all" : String.valueOf(source.getSelectedItem());
            renderArticles();
        }));
        sort.setOnItemSelectedListener(listener(position -> {
            sortFilter = position == 1 ? "romand" : position == 2 ? "calm" : position == 3 ? "alert" : "newest";
            renderArticles();
        }));

        tensionValue = label("10", 13, Typeface.BOLD, accentColor);
        tension = new SeekBar(this);
        tension.setMax(10);
        tension.setProgress(10);
        tension.setProgressTintList(ColorStateList.valueOf(accentColor));
        tension.setThumbTintList(ColorStateList.valueOf(accentColor));
        tension.setOnSeekBarChangeListener(seekListener(value -> {
            maxTension = value;
            tensionValue.setText(String.valueOf(value));
            renderArticles();
        }));

        priorityValue = label("0", 13, Typeface.BOLD, accentColor);
        priority = new SeekBar(this);
        priority.setMax(14);
        priority.setProgress(0);
        priority.setProgressTintList(ColorStateList.valueOf(accentColor));
        priority.setThumbTintList(ColorStateList.valueOf(accentColor));
        priority.setOnSeekBarChangeListener(seekListener(value -> {
            minPriority = value * 10;
            priorityValue.setText(String.valueOf(minPriority));
            renderArticles();
        }));

        advancedFilters.addView(sliderField("Tension max", tensionValue, tension));
        advancedFilters.addView(sliderField("Focus romand min.", priorityValue, priority));

        LinearLayout toggles = new LinearLayout(this);
        toggles.setOrientation(LinearLayout.VERTICAL);
        toggles.setPadding(0, dp(4), 0, 0);
        childOnly = checkbox("Adapté enfants", false);
        hideSports = checkbox("Masquer sport", true);
        toggles.addView(childOnly);
        toggles.addView(hideSports);
        advancedFilters.addView(toggles);

        return filters;
    }

    private void toggleAdvancedFilters() {
        advancedOpen = !advancedOpen;
        advancedFilters.setVisibility(advancedOpen ? View.VISIBLE : View.GONE);
        advancedButton.setText(advancedOpen ? "Masquer les filtres" : "Filtres et recherche");
    }

    private void loadData() {
        status.setText("Chargement...");
        executor.execute(() -> {
            try {
                JSONObject manifest = fetchJson(DATA_BASE + "/manifest.json");
                JSONObject news = fetchJson(DATA_BASE + "/news.json");
                List<NewsArticle> loaded = parseArticles(news.optJSONArray("articles"));
                List<String> regions = valuesFromPayload(news.optJSONArray("regions"), loaded, true);
                List<String> sources = valuesFromPayload(news.optJSONArray("sources"), loaded, false);
                main.post(() -> {
                    applyManifest(manifest);
                    articles.clear();
                    articles.addAll(loaded);
                    updateDynamicSpinners(regions, sources);
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

    private void updateDynamicSpinners(List<String> regions, List<String> sources) {
        fillSpinner(region, "Toutes les régions", regions.toArray(new String[0]));
        fillSpinner(source, "Toutes les sources", sources.toArray(new String[0]));
        regionFilter = "all";
        sourceFilter = "all";
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
            article.calm = item.optInt("calm", 0);
            article.priority = item.optInt("priority", 0);
            article.childFriendly = item.optBoolean("child_friendly", false);
            article.isSports = item.optBoolean("is_sports", false);
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
            TextView empty = label("Aucune actualité ne correspond aux filtres.", 15, Typeface.NORMAL, mutedColor);
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
            if (hideRead != null && hideRead.isChecked() && readIds.contains(article.id)) continue;
            if (hideSports != null && hideSports.isChecked() && article.isSports) continue;
            if (childOnly != null && childOnly.isChecked() && !article.childFriendly) continue;
            if (!"all".equals(regionFilter) && !article.region.equals(regionFilter)) continue;
            if (!"all".equals(sourceFilter) && !article.source.equals(sourceFilter)) continue;
            if (article.tension > maxTension) continue;
            if (article.priority < minPriority) continue;
            if (!matchesPeriod(article, now)) continue;
            if (!normalizedQuery.isEmpty()) {
                String haystack = normalize(article.title + " " + article.summary + " " + article.source + " " + article.region);
                if (!haystack.contains(normalizedQuery)) continue;
            }
            filtered.add(article);
        }
        sortArticles(filtered);
        return filtered;
    }

    private void sortArticles(List<NewsArticle> items) {
        if ("romand".equals(sortFilter)) {
            Collections.sort(items, (a, b) -> b.priority != a.priority ? b.priority - a.priority : Long.compare(b.timestamp, a.timestamp));
        } else if ("calm".equals(sortFilter)) {
            Collections.sort(items, (a, b) -> a.tension != b.tension ? a.tension - b.tension : b.calm - a.calm);
        } else if ("alert".equals(sortFilter)) {
            Collections.sort(items, (a, b) -> b.tension != a.tension ? b.tension - a.tension : Long.compare(b.timestamp, a.timestamp));
        } else {
            Collections.sort(items, (a, b) -> Long.compare(b.timestamp, a.timestamp));
        }
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
        LinearLayout card = roundedPanel(panelColor, lineColor);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(dp(14), dp(12), dp(14), dp(12));
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(match(), wrap());
        params.setMargins(0, 0, 0, dp(10));
        card.setLayoutParams(params);
        if (readIds.contains(article.id)) card.setAlpha(0.72f);

        TextView title = label(article.title, 18, Typeface.BOLD, inkColor);
        title.setOnClickListener(v -> {
            setRead(article.id, true);
            if (!article.url.isEmpty()) startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(article.url)));
        });
        card.addView(title);

        String meta = article.source + " - " + dateFormat.format(Instant.ofEpochMilli(Math.max(0, article.timestamp)));
        TextView metaView = label(meta, 12, Typeface.BOLD, mutedColor);
        LinearLayout.LayoutParams metaParams = new LinearLayout.LayoutParams(match(), wrap());
        metaParams.setMargins(0, dp(2), 0, 0);
        card.addView(metaView, metaParams);

        TextView summary = label(article.summary, 14, Typeface.NORMAL, summaryColor);
        LinearLayout.LayoutParams summaryParams = new LinearLayout.LayoutParams(match(), wrap());
        summaryParams.setMargins(0, dp(8), 0, dp(8));
        card.addView(summary, summaryParams);

        TextView tags = label(
            article.region + "  tension " + article.tension + "/10  focus " + article.priority
                + (article.childFriendly ? "  enfants" : "") + (article.isSports ? "  sport" : ""),
            12,
            Typeface.BOLD,
            accentColor
        );
        card.addView(tags);

        CheckBox read = checkbox("Lu", readIds.contains(article.id));
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
        connection.setRequestProperty("User-Agent", "CursorNewsAndroid/0.2");
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(connection.getInputStream()))) {
            StringBuilder builder = new StringBuilder();
            String line;
            while ((line = reader.readLine()) != null) builder.append(line);
            return new JSONObject(builder.toString());
        } finally {
            connection.disconnect();
        }
    }

    private List<String> valuesFromPayload(JSONArray array, List<NewsArticle> fallback, boolean regions) {
        Set<String> values = new HashSet<>();
        if (array != null) {
            for (int index = 0; index < array.length(); index++) {
                String value = array.optString(index, "");
                if (!value.isEmpty()) values.add(value);
            }
        }
        if (values.isEmpty()) {
            for (NewsArticle article : fallback) values.add(regions ? article.region : article.source);
        }
        List<String> sorted = new ArrayList<>(values);
        Collections.sort(sorted);
        return sorted;
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

    private LinearLayout field(String label, View input) {
        LinearLayout field = new LinearLayout(this);
        field.setOrientation(LinearLayout.VERTICAL);
        field.addView(label(label, 12, Typeface.BOLD, mutedColor));
        field.addView(input, new LinearLayout.LayoutParams(match(), wrap()));
        return field;
    }

    private LinearLayout twoColumnRow(View left, View right) {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        LinearLayout.LayoutParams rowParams = new LinearLayout.LayoutParams(match(), wrap());
        rowParams.setMargins(0, dp(10), 0, 0);
        row.setLayoutParams(rowParams);
        LinearLayout.LayoutParams childParams = new LinearLayout.LayoutParams(0, wrap(), 1);
        childParams.setMargins(0, 0, dp(8), 0);
        row.addView(left, childParams);
        LinearLayout.LayoutParams rightParams = new LinearLayout.LayoutParams(0, wrap(), 1);
        rightParams.setMargins(dp(8), 0, 0, 0);
        row.addView(right, rightParams);
        return row;
    }

    private LinearLayout sliderField(String title, TextView value, SeekBar seekBar) {
        LinearLayout wrap = new LinearLayout(this);
        wrap.setOrientation(LinearLayout.VERTICAL);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(match(), wrap());
        params.setMargins(0, dp(10), 0, 0);
        wrap.setLayoutParams(params);
        LinearLayout row = new LinearLayout(this);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.addView(label(title, 12, Typeface.BOLD, mutedColor), new LinearLayout.LayoutParams(0, wrap(), 1));
        row.addView(value);
        wrap.addView(row);
        wrap.addView(seekBar, new LinearLayout.LayoutParams(match(), wrap()));
        return wrap;
    }

    private Spinner spinner() {
        Spinner view = new Spinner(this);
        view.setMinimumHeight(dp(42));
        return view;
    }

    private void fillSpinner(Spinner spinner, String first, String... rest) {
        List<String> values = new ArrayList<>();
        values.add(first);
        Collections.addAll(values, rest);
        ArrayAdapter<String> adapter = new ArrayAdapter<String>(this, android.R.layout.simple_spinner_item, values) {
            @Override
            public View getView(int position, View convertView, ViewGroup parent) {
                return styleSpinnerText(super.getView(position, convertView, parent), false);
            }

            @Override
            public View getDropDownView(int position, View convertView, ViewGroup parent) {
                return styleSpinnerText(super.getDropDownView(position, convertView, parent), true);
            }
        };
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        spinner.setAdapter(adapter);
    }

    private View styleSpinnerText(View view, boolean dropdown) {
        if (view instanceof TextView) {
            TextView text = (TextView) view;
            text.setTextColor(inkColor);
            text.setTextSize(14);
            text.setBackgroundColor(panelColor);
            text.setPadding(dp(8), dropdown ? dp(12) : dp(8), dp(8), dropdown ? dp(12) : dp(8));
        }
        return view;
    }

    private AdapterView.OnItemSelectedListener listener(PositionCallback callback) {
        return new AdapterView.OnItemSelectedListener() {
            @Override public void onItemSelected(AdapterView<?> parent, View view, int position, long id) {
                callback.onPosition(position);
            }
            @Override public void onNothingSelected(AdapterView<?> parent) {}
        };
    }

    private SeekBar.OnSeekBarChangeListener seekListener(PositionCallback callback) {
        return new SeekBar.OnSeekBarChangeListener() {
            @Override public void onProgressChanged(SeekBar seekBar, int progress, boolean fromUser) {
                callback.onPosition(progress);
            }
            @Override public void onStartTrackingTouch(SeekBar seekBar) {}
            @Override public void onStopTrackingTouch(SeekBar seekBar) {}
        };
    }

    private CheckBox checkbox(String text, boolean checked) {
        CheckBox box = new CheckBox(this);
        box.setText(text);
        box.setTextColor(inkColor);
        box.setTextSize(14);
        box.setChecked(checked);
        box.setButtonTintList(ColorStateList.valueOf(accentColor));
        box.setOnCheckedChangeListener((buttonView, isChecked) -> renderArticles());
        return box;
    }

    private Button actionButton(String text, boolean primary) {
        Button button = new Button(this);
        button.setAllCaps(false);
        button.setText(text);
        button.setTextSize(14);
        button.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        button.setTextColor(primary ? primaryButtonTextColor : inkColor);
        button.setMinHeight(dp(38));
        button.setMinimumHeight(dp(38));
        button.setPadding(dp(12), 0, dp(12), 0);
        GradientDrawable bg = new GradientDrawable();
        bg.setColor(primary ? accentColor : softColor);
        bg.setCornerRadius(dp(8));
        bg.setStroke(dp(1), primary ? accentColor : lineColor);
        button.setBackground(bg);
        return button;
    }

    private LinearLayout roundedPanel(int color, int stroke) {
        LinearLayout view = new LinearLayout(this);
        GradientDrawable bg = new GradientDrawable();
        bg.setColor(color);
        bg.setCornerRadius(dp(8));
        bg.setStroke(dp(1), stroke);
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

    private interface PositionCallback {
        void onPosition(int position);
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
        int calm = 0;
        int priority = 0;
        boolean childFriendly = false;
        boolean isSports = false;
    }
}
