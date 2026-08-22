# AI summary

AI writing is optional. It summarizes results the pipeline already produced; it does not analyze raw tracking data or compute new statistics.

There are two related outputs:

- **Experiment AI Summary** - created from the Hub's **AI** tile for the loaded replicate and embedded in that replicate's PDF report.
- **Project AI narrative** - created from the Project panel's **AI narrative...** action after Combined Analysis; the Project report is rebuilt immediately so the narrative is embedded.

Both are clearly labeled in reports as AI-generated.

## Enabling AI

Add one or both API keys to a `.env` file in the launch folder, to `~/.config/pytrackinganalysis/.env`, or to the environment:

```
ANTHROPIC_API_KEY=...
OPENAI_API_KEY=...
```

The app checks only that a key exists before enabling the action. Bad keys, offline providers, or rate limits show an error when you request a summary.

## Experiment summary

1. Load a replicate by double-clicking it in the Project table.
2. Run analysis so the report content, figures, stats, and summary CSVs exist.
3. Open **AI -> AI summary...**, choose provider and model, and click **Generate**.
4. The summary is saved to `analysis/<experiment>_AI_Summary.txt`.
5. The experiment report is rebuilt automatically so the PDF and text file agree.

The provider receives report-ready content: cover metadata, figures as images, statistics, and per-fly summaries. It is not sent raw tracking files.

## Project narrative

1. Run **Create report** or **Update report** for the Project so Combined Analysis is current.
2. Click **AI narrative...** in the Project panel and choose a provider.
3. The narrative is saved to `analysis/<project>_AI_Summary.txt`.
4. The Project report is rebuilt immediately so the PDF and text file agree.

## In scripts

Project Scripts have a **Generate AI narrative** action (provider choice; it soft-fails by default so a provider error never kills a pipeline). The built-in pipelines do not include it - building Combined Analysis deletes a saved narrative, so add it as a final step of a custom Project Script when you want the narrative refreshed automatically.

## Lifecycle

- The saved text file is the opt-in. Reports embed AI prose only while the corresponding `*_AI_Summary.txt` exists.
- Re-running an experiment analysis deletes its experiment AI Summary.
- Rebuilding a Project Combined Analysis deletes its Project AI narrative. Because **Create report** and **Update report** rebuild Combined Analysis, run **AI narrative...** after the final report refresh when you want AI prose in the PDF.
- A Batch Run's default Report pipeline rebuilds each Project's Combined Analysis, so it deletes any saved narrative in every Project it touches. Regenerate afterwards, or designate a custom Project Script that ends with **Generate AI narrative** (see the **Batch runs** help topic).
- Regenerating replaces the saved text.

Always review AI prose before using it. It is a language-model summary of pipeline outputs, not an independent scientific conclusion.
