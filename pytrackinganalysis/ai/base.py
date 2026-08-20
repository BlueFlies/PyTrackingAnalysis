"""Provider-agnostic core of the AI Summary feature (see CONTEXT.md, ADR-0004).

An :class:`AISummarizer` turns a :class:`~pytrackinganalysis.ai.payload.SummaryPayload`
(the report's own text and figures) into one page of prose via an external
provider. This module owns everything the concrete providers share — API-key
discovery, availability checks, and the summarize contract — so the Anthropic
and OpenAI subclasses stay thin request builders.

Design rules:

* No provider SDK is imported at module level — the package must import (and
  the availability check must run) on a machine with neither SDK usable.
* Keys come from the environment, optionally topped up from ``.env`` files.
  Presence of a key is what makes a provider *available*; validity is only
  discovered at call time (ADR-0004: a failed call never blocks anything).
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .payload import SummaryPayload


class AISummaryError(RuntimeError):
    """A summary could not be produced (missing key, provider error, refusal).

    Carries a user-facing message; callers surface it and move on — report
    creation is never blocked by this error (ADR-0004).
    """


_env_loaded = False


def load_api_env() -> None:
    """Load API keys from ``.env`` files into the environment, once.

    Looks in the per-user config directory (`~/.config/pytrackinganalysis/.env`)
    and then walks up from the current directory (python-dotenv's default), so
    both an installed app and a repo checkout find their keys. Real environment
    variables always win — nothing is overridden.
    """
    global _env_loaded
    if _env_loaded:
        return
    _env_loaded = True
    try:
        from dotenv import find_dotenv, load_dotenv
    except ImportError:  # pragma: no cover - dotenv is a declared dependency
        return
    config_env = os.path.join(
        os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
        "pytrackinganalysis", ".env")
    if os.path.isfile(config_env):
        load_dotenv(config_env, override=False)
    found = find_dotenv(usecwd=True)
    if found:
        load_dotenv(found, override=False)


class AISummarizer(ABC):
    """One provider's way of writing an AI Summary.

    Subclasses set the class attributes and implement :meth:`_request`. The
    curated ``models`` tuple is the always-works floor: every model on it is
    known to accept image input, and it is what the UI falls back to when the
    live list (see :meth:`fetch_models` and :mod:`.model_catalog`) is
    unavailable.
    """

    #: Stable key used in code, settings, and the registry (e.g. "anthropic").
    provider_name: str = ""
    #: Human label for dialogs and the summary's provenance line.
    display_name: str = ""
    #: Environment variable holding the API key.
    env_var: str = ""
    #: Curated, vision-capable model ids offered in the UI. First = default.
    models: tuple[str, ...] = ()

    @classmethod
    def default_model(cls) -> str:
        return cls.models[0]

    @classmethod
    def fetch_models(cls) -> list[str]:
        """This provider's current chat/vision-capable model ids, fresh from
        its model-listing API. Subclasses override with a real fetch (raising
        :class:`AISummaryError` on failure); the base default is the curated
        list, so a provider without a listing endpoint still refreshes cleanly.
        """
        return list(cls.models)

    @classmethod
    def is_available(cls) -> bool:
        """True when this provider's API key is present (not validated —
        validity is only known at call time, per ADR-0004)."""
        load_api_env()
        return bool(os.environ.get(cls.env_var, "").strip())

    def __init__(self, model: str | None = None) -> None:
        load_api_env()
        self.api_key = os.environ.get(self.env_var, "").strip()
        if not self.api_key:
            raise AISummaryError(
                f"{self.display_name}: no API key found. Set {self.env_var} "
                f"in the environment or a .env file.")
        self.model = model or self.default_model()

    def summarize(self, payload: "SummaryPayload", instructions: str) -> str:
        """Return the summary prose for *payload*, or raise AISummaryError."""
        text = (self._request(instructions, payload) or "").strip()
        if not text:
            raise AISummaryError(
                f"{self.display_name} ({self.model}) returned an empty summary.")
        return text

    @abstractmethod
    def _request(self, instructions: str, payload: "SummaryPayload") -> str:
        """Perform one provider call and return the raw summary text.

        Implementations translate their SDK's failures into
        :class:`AISummaryError` with a message a scientist can act on.
        """
