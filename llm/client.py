"""A thin provider-agnostic client for an OpenAI-compatible chat-completions endpoint.

Deliberately small: one POST, JSON in, JSON out, with a retry and a hard timeout. It speaks
the OpenAI chat-completions shape, which Groq, Gemini's compatibility layer, Ollama, and
OpenAI itself all accept, so switching providers is a base-URL and model-name change in
config, nothing here.

The client never raises on a missing key. `available()` reports whether a key is set, and
the caller checks that first so the pipeline degrades to "deterministic output only" rather
than crashing when run without credentials.
"""

import json
import urllib.error
import urllib.request

import config


class LLMUnavailable(Exception):
    """Raised when the client is asked to complete but no endpoint is configured. The caller
    is expected to check available() first; this is a backstop, not the normal path."""


def available():
    """True if an endpoint is configured. The default is a local Ollama, which needs no key,
    so availability keys off the base URL rather than a credential. Everything downstream
    keys off this so a run with no endpoint reachable skips the LLM step cleanly."""
    return bool(config.LLM_BASE_URL)


def reachable():
    """A fast check that the endpoint actually answers, so we skip the whole tier cleanly
    when (for the local default) Ollama isn't running, rather than timing out once per row.
    A short connect attempt to the models list is enough; any failure means not reachable."""
    if not available():
        return False
    try:
        request = urllib.request.Request(
            f"{config.LLM_BASE_URL}/models", headers=_headers(), method="GET"
        )
        with urllib.request.urlopen(request, timeout=3):
            return True
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _headers():
    """Build request headers. The Authorization header is only attached when a key is set,
    so a local keyless endpoint isn't sent an empty bearer token."""
    headers = {"Content-Type": "application/json"}
    if config.LLM_API_KEY:
        headers["Authorization"] = f"Bearer {config.LLM_API_KEY}"
    return headers


def complete(system_prompt, user_prompt, json_object=False):
    """Send one chat completion and return the raw text content. Retries a small number of
    times on transport errors, then gives up by raising, so the caller can record the row
    as un-explained rather than abort the whole run. With json_object set, asks the endpoint
    for JSON-object mode, which Ollama and the OpenAI-compatible providers honour by
    constraining the output to valid JSON."""
    if not available():
        raise LLMUnavailable("no LLM endpoint configured")

    payload = {
        "model": config.LLM_MODEL,
        "temperature": config.LLM_TEMPERATURE,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    if json_object:
        payload["response_format"] = {"type": "json_object"}
    body = json.dumps(payload).encode("utf-8")

    last_error = None
    for _ in range(config.LLM_RETRY_ATTEMPTS):
        request = urllib.request.Request(
            f"{config.LLM_BASE_URL}/chat/completions",
            data=body,
            headers=_headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=config.LLM_TIMEOUT_SECONDS) as response:
                data = json.loads(response.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"]
        except (urllib.error.URLError, KeyError, json.JSONDecodeError, TimeoutError) as problem:
            last_error = problem
            continue

    raise RuntimeError(f"LLM request failed after retries: {last_error}")
