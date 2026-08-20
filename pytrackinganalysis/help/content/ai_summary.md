# AI summary

The **AI Summary** is an optional, AI-written narrative (up to one page) of an
experiment's analysis, embedded near the top of the report and clearly labeled
as AI-generated. The AI *summarizes* the pipeline's analysis — it never
performs its own.

## Enabling it

The AI card's action is offered only when a provider API key is available.
Put one (or both) of these in a `.env` file — in the folder you launch the app
from, or in `~/.config/pytrackinganalysis/.env` — or in the environment:

```
ANTHROPIC_API_KEY=...
OPENAI_API_KEY=...
```

Only the key's *presence* is checked up front; a revoked or mistyped key shows
up as an error message when a summary is requested.

## Generating a summary

1. Load an experiment and run the analysis.
2. In the **AI** card, click **AI summary…**, pick a provider and model, and
   click **Generate**. The choice is remembered for next time. The model list
   is fetched from each provider and cached; it refreshes itself when it is
   more than a month old, and the refresh button next to the model dropdown
   fetches it on demand. Offline, the saved list keeps working.
3. The provider is sent the report's own content — cover metadata, figures
   (as images), statistics, and the per-fly summary CSVs — never the raw
   tracking data.
4. On success the summary is saved to `analysis/<name>_AI_Summary.txt` and the
   report PDF is rebuilt automatically so the two never disagree.

If the call fails (bad key, offline, rate limit), you get an error message and
nothing else changes — the report is never blocked by the AI.

## Lifecycle

- The saved file **is** the opt-in: the report embeds an AI Summary section
  exactly when `<name>_AI_Summary.txt` exists.
- **Re-running the analysis deletes the saved summary.** It describes a single
  analysis run; once the figures and statistics change, keeping it would put
  stale prose next to fresh results. Regenerate it from the AI card after the
  run.
- Regenerating replaces the saved summary and rebuilds the report.

Always review the summary — it is a language-model narrative of your results,
not a verified scientific conclusion.
