# CPU Model Tests - 20 October 2026

## Decision

Keep `gemma3:12b` for automatic bulletins for now. Smaller models were faster
in some tests, but none passed both the existing automated checks and a manual
comparison against the supplied articles. Do not trade factual accuracy for a
lower parameter count.

The retained CPU profile uses three inference threads, a compact French prompt
and one drafting pass per hourly slot. A rejected draft does not trigger a
second automatic writing pass; the previous valid audio remains available.
Manual topic drafting can still request revisions.
The hourly flash targets 350-450 words but accepts a compact script from 240
words; the other topics keep their 280-word floor. A word-count target alone
should not cause a second expensive pass or encourage padding.

## Measurements

The laptop has an Intel Core Ultra 7 155H with 22 logical CPUs. These are
wall-clock drafting times on the Ubuntu CPU-only laptop, not model
leaderboard scores. All calls used an 8,192-token context, a 1,200-token output
limit, temperature 0.2, thinking disabled, JSON-format mode disabled and unload
after each response. Models ran sequentially. Word counts include the final
source credits added by the application.

| Model | Pack / prompt | Threads | Drafting Time | Words | Result |
| --- | --- | ---: | ---: | ---: | --- |
| Gemma 3 12B, previous production run | A / original | 4 | About 20-21 min, two passes | 241 then 320 | First draft too short; revision accepted |
| Qwen 3 4B | A / original | 4 | 5 min 01 s, first pass | 216 | Too short; factual wording also weak |
| Llama 3.2 3B | A / original | 4 | 5 min 33 s, two passes | 87 on both | Too short |
| Mistral 7B Instruct | A / original | 4 | 7 min 09 s | 115 | Only one developed story; too short |
| Qwen 3 4B | B / clean RSS fallback | 2 | 9 min 33 s | 201 | Too short; factual wording also weak |
| Llama 3.2 3B | B / compact | 2 | 4 min 11 s | 90 | Too short |
| Gemma 3 4B Q4_K_M | B / compact | 2 | 5 min 30 s | 282 | Automated check passed; manual factual review failed |
| Gemma 3 12B, retained profile | B / compact | 3 | 9 min 57 s | 243 | Too short under the old 280-word check; fits the revised hourly compact floor |

Pack A replays the articles associated with the 14:00 bulletin. Pack B freezes
a newer selection of five Swiss and international articles. Comparisons across
packs, prompt versions or thread counts are not controlled speedup estimates.
The old production timing is approximate; the benchmark-script timings are
measured with a monotonic clock.
The first published flash after this investigation was manually reviewed,
corrected and developed from the 12B draft, not an unedited benchmark output.
The 12B also introduced unsupported wording. Keeping the existing model is a
conservative compatibility choice, not proof of error-free factual reporting.

The compact prompt on pack B is 6,647 characters versus 8,344 previously, a
20.3% reduction without removing article facts. Long URLs are kept in SQLite
and the website, but no longer sent to the model. When HTML contains navigation
or advertising text, the model gets the RSS summary instead.

The most promising smaller candidate was
[Gemma 3 4B Q4_K_M from LM Studio Community](https://huggingface.co/lmstudio-community/gemma-3-4b-it-GGUF).
It produced readable French, but inverted an economic comparison and presented
political candidacies as certain successions. The automatic length and formatting
checks cannot detect these semantic errors, which is why human review matters.
The weights are downloaded separately and retain their upstream license.

## Thermal Observations

The ACPI thermal sensor (`thermal_zone0`, `acpitz`) showed readings above 80 C
in four-thread trials. Two-thread trials showed
readings around 70-71 C and approximately 200% CPU for the model runner.
These are spot observations, not controlled peak-temperature or energy tests.
The retained three-thread 12B run showed a 77 C ACPI reading during drafting;
a separate CPU package sensor sample was 74 C.
The Ubuntu App Center was also using approximately 76% of one CPU core during
a two-second sample; it was left untouched.

## Reproduce A Trial

Pause automatic generation and let any current pipeline run finish first.
Restart the timer after testing. Do not run models concurrently.

Freeze `Article` and `StyleSlot` dataclasses with `dataclasses.asdict` in a JSON
file containing `articles`, `style` and the ISO `slot_start`. Reuse exactly the
same file for each model comparison:

```bash
uv run --python 3.10 python scripts/benchmark_llm.py \
  --pack data/model-benchmarks/pack.json \
  --model gemma3:12b --threads 3 \
  --output data/model-benchmarks/gemma12b.json
```

Add `--revise` only to measure the cost of a second pass after a rejection.
The report stores the raw draft, normalized transcript, word count, rejection
reason and wall time. It does not change articles, create audio or publish
anything. Source snapshots and detailed reports stay under ignored `data/`;
the model weights and article contents are not committed to Git.

## Runtime Limitation

The laptop currently runs Ollama 0.24.0. The newer Qwen 3.5 4B GGUF was
downloaded but could not be evaluated: that runtime reports an unknown
`qwen35` architecture. Native registry pulls also request a newer Ollama.
Updating the system runtime needs an interactive `sudo` authentication on this
laptop; it was not bypassed by installing a second inference service.
Follow the [official Linux update instructions](https://docs.ollama.com/linux)
before testing that candidate. No claim about its speed or quality is made.

Also fixed during the investigation: a misplaced source-credit line could
discard all later paragraphs. Regression tests now preserve later news in both
French and English while still moving credits to the end.
