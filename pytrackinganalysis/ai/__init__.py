"""AI-assisted functions — today, the AI Summary (see CONTEXT.md, ADR-0004).

A deliberately small provider layer: :class:`AISummarizer` subclasses talk to
the official Anthropic / OpenAI SDKs directly. No agent frameworks, no tool
use, no streaming — one request in (report text + figure images), one page of
prose out.

Public surface::

    available_providers()          -> the summarizer classes with a key present
    get_summarizer("anthropic")    -> a ready AISummarizer (or AISummaryError)
    build_payload(experiment)      -> the SummaryPayload a summarizer consumes
"""

from __future__ import annotations

from .anthropic_provider import AnthropicSummarizer
from .base import AISummaryError, AISummarizer, load_api_env
from .openai_provider import OpenAISummarizer
from .payload import SummaryPayload, build_payload

#: Registration order is presentation order in the UI.
PROVIDERS: tuple[type[AISummarizer], ...] = (
    AnthropicSummarizer,
    OpenAISummarizer,
)

__all__ = [
    "AISummaryError",
    "AISummarizer",
    "AnthropicSummarizer",
    "OpenAISummarizer",
    "PROVIDERS",
    "SummaryPayload",
    "available_providers",
    "build_payload",
    "get_summarizer",
    "load_api_env",
]


def available_providers() -> list[type[AISummarizer]]:
    """The providers whose API key is present (see ADR-0004: presence-gated —
    validity is only discovered when a summary is actually requested)."""
    return [provider for provider in PROVIDERS if provider.is_available()]


def get_summarizer(provider_name: str, model: str | None = None) -> AISummarizer:
    """A ready summarizer for *provider_name*, or raise AISummaryError."""
    for provider in PROVIDERS:
        if provider.provider_name == provider_name:
            return provider(model=model)
    known = ", ".join(p.provider_name for p in PROVIDERS)
    raise AISummaryError(
        f"Unknown AI provider '{provider_name}'. Known providers: {known}.")
