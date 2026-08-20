"""The OpenAI summarizer."""

from __future__ import annotations

import base64
import os
import re
from typing import TYPE_CHECKING

from .base import AISummaryError, AISummarizer

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .payload import SummaryPayload

_TIMEOUT_SECONDS = 300.0
_MAX_RETRIES = 3
# ``max_completion_tokens`` (the ``max_tokens`` successor, required by the
# gpt-5 family) also budgets any internal reasoning tokens, so it is set well
# above the one page of prose actually wanted.
_MAX_COMPLETION_TOKENS = 8192
# Model listing is a quick metadata call the dialog may wait on — fail fast.
_LIST_TIMEOUT_SECONDS = 10.0

# OpenAI's /models mixes chat models with embeddings, audio, image, and
# legacy families. Keep the general chat/vision families and drop the rest;
# a wrong keep is harmless (the summary call fails with a clear message and
# the curated defaults still lead the list).
_ID_PREFIXES = re.compile(r"^(gpt-|o\d)")
_EXCLUDE_SUBSTRINGS = (
    "audio", "realtime", "tts", "transcribe", "whisper", "embed",
    "moderation", "dall-e", "image", "davinci", "babbage", "instruct",
    "search", "computer-use", "codex", "sora", "deep-research", "chatgpt",
    "gpt-3.5",
)
_DATED_SNAPSHOT = re.compile(r"-\d{4}-\d{2}-\d{2}$")


def _filter_model_ids(ids: list[str]) -> list[str]:
    kept = []
    for model_id in ids:
        if not _ID_PREFIXES.match(model_id):
            continue
        if any(fragment in model_id for fragment in _EXCLUDE_SUBSTRINGS):
            continue
        if _DATED_SNAPSHOT.search(model_id):
            continue  # dated duplicates of the alias ids
        kept.append(model_id)
    return kept


class OpenAISummarizer(AISummarizer):
    provider_name = "openai"
    display_name = "OpenAI"
    env_var = "OPENAI_API_KEY"
    # Curated vision-capable models (see AISummarizer.models). First = default.
    models = ("gpt-5.2", "gpt-4o")

    @classmethod
    def fetch_models(cls) -> list[str]:
        import openai

        from .base import load_api_env

        load_api_env()
        api_key = os.environ.get(cls.env_var, "").strip()
        if not api_key:
            raise AISummaryError(
                f"{cls.display_name}: no API key found. Set {cls.env_var} "
                f"in the environment or a .env file.")
        client = openai.OpenAI(
            api_key=api_key,
            timeout=_LIST_TIMEOUT_SECONDS,
            max_retries=0,
        )
        try:
            ids = [model.id for model in client.models.list()]
        except openai.OpenAIError as err:
            raise AISummaryError(
                f"{cls.display_name}: could not fetch the model list "
                f"({err.__class__.__name__}).") from err
        return _filter_model_ids(ids)

    def _request(self, instructions: str, payload: "SummaryPayload") -> str:
        import openai

        client = openai.OpenAI(
            api_key=self.api_key,
            timeout=_TIMEOUT_SECONDS,
            max_retries=_MAX_RETRIES,
        )
        content: list[dict] = []
        for title, png in payload.images:
            content.append({"type": "text", "text": f"Figure: {title}"})
            data = base64.standard_b64encode(png).decode("ascii")
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{data}"},
            })
        content.append({"type": "text", "text": payload.text})

        try:
            response = client.chat.completions.create(
                model=self.model,
                max_completion_tokens=_MAX_COMPLETION_TOKENS,
                messages=[
                    {"role": "system", "content": instructions},
                    {"role": "user", "content": content},
                ],
            )
        except openai.AuthenticationError as err:
            raise AISummaryError(
                f"{self.display_name}: the API key was rejected. Check "
                f"{self.env_var} in your .env file.") from err
        except openai.NotFoundError as err:
            raise AISummaryError(
                f"{self.display_name}: model '{self.model}' was not "
                f"recognised by the API.") from err
        except openai.RateLimitError as err:
            raise AISummaryError(
                f"{self.display_name}: rate-limited even after retries — "
                f"try again in a minute.") from err
        except openai.APIStatusError as err:
            raise AISummaryError(
                f"{self.display_name}: API error {err.status_code}.") from err
        except openai.APIConnectionError as err:
            raise AISummaryError(
                f"{self.display_name}: could not reach the API — check the "
                f"network connection.") from err

        return response.choices[0].message.content or ""
