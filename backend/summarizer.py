"""Beginner-friendly research paper summarization with resumable chunk caching."""

import hashlib
import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable

import requests

OLLAMA_URL = os.getenv("OLLAMA_URL", "").strip() or "http://localhost:11434/api/generate"
MODEL_NAME = os.getenv("OLLAMA_MODEL", "").strip() or "llama3.2:3b"
CHUNK_SIZE = 4000
REQUEST_TIMEOUT = (10, 600)  # connect timeout, read timeout in seconds
PROGRESS_HEARTBEAT_SECONDS = 15
CACHE_DIR = Path(tempfile.gettempdir()) / "researchmate_summary_cache"

ProgressCallback = Callable[[int, str, dict[str, Any] | None], None] | None


def get_active_provider(override: str | None = None) -> str:
    """Determine the active AI provider: 'gemini', 'grok', 'groq', or 'ollama'.
    
    Priority:
    1. Explicit override passed from request (e.g. X-AI-Provider header)
    2. AI_PROVIDER env var ('gemini', 'grok', 'groq', 'ollama', 'local')
    3. If GEMINI_API_KEY is present -> 'gemini'
    4. If XAI_API_KEY or GROK_API_KEY is present -> 'grok'
    5. If GROQ_API_KEY is present -> 'groq'
    6. Default fallback -> 'ollama' (local offline AI)
    """
    if override:
        cand = override.strip().lower()
        if cand in ("gemini", "grok", "groq", "ollama", "local"):
            return "ollama" if cand == "local" else cand

    forced = os.getenv("AI_PROVIDER", "").strip().lower()
    if forced in ("gemini", "grok", "groq", "ollama", "local"):
        return "ollama" if forced == "local" else forced
    if os.getenv("GEMINI_API_KEY", "").strip():
        return "gemini"
    if os.getenv("XAI_API_KEY", "").strip() or os.getenv("GROK_API_KEY", "").strip():
        return "grok"
    if os.getenv("GROQ_API_KEY", "").strip():
        return "groq"
    return "ollama"


def _is_local_ollama_available() -> bool:
    """Check if local Ollama daemon is currently responsive."""
    try:
        ping_url = OLLAMA_URL.replace("/api/generate", "/api/tags")
        res = requests.get(ping_url, timeout=1.5)
        return res.ok
    except Exception:
        return False


def call_ollama(prompt: str, max_tokens: int = 200) -> str:
    """Send one prompt to the active AI provider and return its response text."""
    return stream_ollama(prompt, max_tokens, json_format=False)


_cached_gemini_models: list[str] = []


def _resolve_gemini_models(api_key: str) -> list[str]:
    """Retrieve and prioritize available Gemini models dynamically for this key."""
    global _cached_gemini_models
    if _cached_gemini_models:
        return _cached_gemini_models

    configured = os.getenv("GEMINI_MODEL", "").strip()
    defaults = [
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.0-flash",
        "gemini-flash-latest",
    ]
    if configured:
        fallbacks = [m for m in defaults if m != configured]
        _cached_gemini_models = [configured, *fallbacks]
        return _cached_gemini_models

    try:
        res = requests.get(
            f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}",
            timeout=5,
        )
        if res.ok:
            data = res.json()
            available = [
                m["name"].replace("models/", "")
                for m in data.get("models", [])
                if "generateContent" in m.get("supportedGenerationMethods", [])
            ]
            # Exclude non-text models (audio, tts, embedding, imagen)
            text_models = [
                m for m in available
                if not any(tag in m.lower() for tag in ("tts", "audio", "embed", "imagen"))
            ]
            flash_models = [m for m in text_models if "flash" in m.lower()]
            if flash_models:
                def _model_priority(name: str) -> int:
                    if name == "gemini-2.5-flash":
                        return 100
                    if name == "gemini-2.5-flash-lite":
                        return 90
                    if name == "gemini-2.0-flash":
                        return 80
                    return 50

                prioritized = sorted(flash_models, key=_model_priority, reverse=True)
                _cached_gemini_models = prioritized
                print(f"[AI] Discovered available text Gemini models: {prioritized[:3]}", flush=True)
                return prioritized
            if text_models:
                _cached_gemini_models = text_models
                return text_models
    except Exception as exc:
        print(f"[AI] Note: could not query Gemini models list ({exc}); using defaults.", flush=True)

    _cached_gemini_models = defaults
    return defaults


def _stream_gemini(
    prompt: str,
    max_tokens: int = 200,
    progress_callback: Callable[[str], None] | None = None,
    *,
    json_format: bool = False,
    heartbeat_callback: Callable[[], None] | None = None,
) -> str:
    """Generate response via Google Gemini REST API (Server-Sent Events streaming)."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set.")

    candidate_models = _resolve_gemini_models(api_key)

    generation_config: dict[str, Any] = {
        "temperature": 0.2,
        "maxOutputTokens": max_tokens,
    }
    if json_format:
        generation_config["responseMimeType"] = "application/json"

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": generation_config,
    }

    last_error: Exception | None = None

    for model_idx, model in enumerate(candidate_models):
        is_last_model = (model_idx == len(candidate_models) - 1)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?alt=sse&key={api_key}"

        for attempt in range(2):
            response_text = []
            heartbeat_stop = threading.Event()
            heartbeat_errors: list[Exception] = []

            def report_heartbeat() -> None:
                while not heartbeat_stop.wait(PROGRESS_HEARTBEAT_SECONDS):
                    try:
                        if heartbeat_callback is not None:
                            heartbeat_callback()
                    except Exception as exc:
                        heartbeat_errors.append(exc)
                        return

            heartbeat_thread = None
            if heartbeat_callback is not None:
                heartbeat_thread = threading.Thread(target=report_heartbeat, daemon=True)
                heartbeat_thread.start()

            retry_same = False
            try:
                with requests.post(
                    url,
                    json=payload,
                    stream=True,
                    timeout=REQUEST_TIMEOUT,
                ) as response:
                    if response.status_code in (429, 503):
                        if attempt == 0:
                            print(f"[AI] Gemini model '{model}' returned HTTP {response.status_code} (high demand); waiting 2s to retry...", flush=True)
                            time.sleep(2.0)
                            retry_same = True
                            continue
                        elif not is_last_model:
                            print(f"[AI] Gemini model '{model}' returned HTTP {response.status_code}; trying next candidate...", flush=True)
                            break
                    elif response.status_code in (400, 404):
                        if not is_last_model:
                            print(f"[AI] Gemini model '{model}' returned HTTP {response.status_code}; trying next candidate...", flush=True)
                            break

                    if not response.ok:
                        err_detail = response.text[:300]
                        raise RuntimeError(f"Gemini API ({model}) returned HTTP {response.status_code}: {err_detail}")

                    response.encoding = "utf-8"
                    for line in response.iter_lines(decode_unicode=True):
                        if not line:
                            continue
                        if line.startswith("data: "):
                            line_data = line[6:].strip()
                            if not line_data:
                                continue
                            try:
                                update = json.loads(line_data)
                            except json.JSONDecodeError:
                                continue
                            candidates = update.get("candidates", [])
                            if candidates:
                                parts = candidates[0].get("content", {}).get("parts", [])
                                for part in parts:
                                    text = part.get("text", "")
                                    if text:
                                        response_text.append(text)
                                        if progress_callback is not None:
                                            progress_callback("".join(response_text))
            except Exception as exc:
                last_error = exc
                if retry_same:
                    continue
                if not is_last_model and any(code in str(exc) for code in ("404", "400", "429", "503")):
                    time.sleep(1.0)
                    break
                raise
            finally:
                heartbeat_stop.set()
                if heartbeat_thread is not None:
                    heartbeat_thread.join()

            if heartbeat_errors:
                raise heartbeat_errors[0]

            generated_text = "".join(response_text).strip()
            if generated_text:
                return generated_text

    if last_error:
        raise last_error
    raise RuntimeError("Gemini API returned an empty response.")


def _stream_grok(
    prompt: str,
    max_tokens: int = 200,
    progress_callback: Callable[[str], None] | None = None,
    *,
    json_format: bool = False,
    heartbeat_callback: Callable[[], None] | None = None,
) -> str:
    """Generate response via xAI Grok REST API (OpenAI-compatible streaming)."""
    api_key = os.getenv("XAI_API_KEY", "").strip() or os.getenv("GROK_API_KEY", "").strip()
    if not api_key:
        if os.getenv("GROQ_API_KEY", "").strip():
            return _stream_groq(
                prompt,
                max_tokens=max_tokens,
                progress_callback=progress_callback,
                json_format=json_format,
                heartbeat_callback=heartbeat_callback,
            )
        raise RuntimeError("Neither XAI_API_KEY nor GROK_API_KEY is configured in your environment.")

    model = os.getenv("GROK_MODEL", "").strip() or "grok-2-latest"
    url = "https://api.x.ai/v1/chat/completions"

    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": max_tokens,
        "stream": True,
    }
    if json_format:
        payload["response_format"] = {"type": "json_object"}

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    response_text = []
    heartbeat_stop = threading.Event()
    heartbeat_errors: list[Exception] = []

    def report_heartbeat() -> None:
        while not heartbeat_stop.wait(PROGRESS_HEARTBEAT_SECONDS):
            try:
                if heartbeat_callback is not None:
                    heartbeat_callback()
            except Exception as exc:
                heartbeat_errors.append(exc)
                return

    heartbeat_thread = None
    if heartbeat_callback is not None:
        heartbeat_thread = threading.Thread(target=report_heartbeat, daemon=True)
        heartbeat_thread.start()

    try:
        with requests.post(
            url,
            json=payload,
            headers=headers,
            stream=True,
            timeout=REQUEST_TIMEOUT,
        ) as response:
            if not response.ok:
                err_detail = response.text[:300]
                raise RuntimeError(f"Grok API returned HTTP {response.status_code}: {err_detail}")
            response.encoding = "utf-8"
            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue
                if line.startswith("data: "):
                    line_data = line[6:].strip()
                    if line_data == "[DONE]":
                        break
                    try:
                        update = json.loads(line_data)
                    except json.JSONDecodeError:
                        continue
                    choices = update.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        text = delta.get("content", "")
                        if text:
                            response_text.append(text)
                            if progress_callback is not None:
                                progress_callback("".join(response_text))
    finally:
        heartbeat_stop.set()
        if heartbeat_thread is not None:
            heartbeat_thread.join()

    if heartbeat_errors:
        raise heartbeat_errors[0]

    generated_text = "".join(response_text).strip()
    if not generated_text:
        raise RuntimeError("Grok API returned an empty response.")
    return generated_text


def _stream_groq(
    prompt: str,
    max_tokens: int = 200,
    progress_callback: Callable[[str], None] | None = None,
    *,
    json_format: bool = False,
    heartbeat_callback: Callable[[], None] | None = None,
) -> str:
    """Generate response via Groq Cloud REST API (OpenAI-compatible streaming)."""
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set.")

    model = os.getenv("GROQ_MODEL", "").strip() or "llama-3.3-70b-versatile"
    url = "https://api.groq.com/openai/v1/chat/completions"

    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": max_tokens,
        "stream": True,
    }
    if json_format:
        payload["response_format"] = {"type": "json_object"}

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    response_text = []
    heartbeat_stop = threading.Event()
    heartbeat_errors: list[Exception] = []

    def report_heartbeat() -> None:
        while not heartbeat_stop.wait(PROGRESS_HEARTBEAT_SECONDS):
            try:
                if heartbeat_callback is not None:
                    heartbeat_callback()
            except Exception as exc:
                heartbeat_errors.append(exc)
                return

    heartbeat_thread = None
    if heartbeat_callback is not None:
        heartbeat_thread = threading.Thread(target=report_heartbeat, daemon=True)
        heartbeat_thread.start()

    try:
        with requests.post(
            url,
            json=payload,
            headers=headers,
            stream=True,
            timeout=REQUEST_TIMEOUT,
        ) as response:
            if not response.ok:
                err_detail = response.text[:300]
                raise RuntimeError(f"Groq API returned HTTP {response.status_code}: {err_detail}")
            response.encoding = "utf-8"
            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue
                if line.startswith("data: "):
                    line_data = line[6:].strip()
                    if line_data == "[DONE]":
                        break
                    try:
                        update = json.loads(line_data)
                    except json.JSONDecodeError:
                        continue
                    choices = update.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        text = delta.get("content", "")
                        if text:
                            response_text.append(text)
                            if progress_callback is not None:
                                progress_callback("".join(response_text))
    finally:
        heartbeat_stop.set()
        if heartbeat_thread is not None:
            heartbeat_thread.join()

    if heartbeat_errors:
        raise heartbeat_errors[0]

    generated_text = "".join(response_text).strip()
    if not generated_text:
        raise RuntimeError("Groq API returned an empty response.")
    return generated_text


def _stream_ollama(
    prompt: str,
    max_tokens: int = 200,
    progress_callback: Callable[[str], None] | None = None,
    *,
    json_format: bool = True,
    heartbeat_callback: Callable[[], None] | None = None,
) -> str:
    """Generate response via local Ollama daemon."""
    response_text = []
    heartbeat_stop = threading.Event()
    heartbeat_errors: list[Exception] = []

    def report_heartbeat() -> None:
        while not heartbeat_stop.wait(PROGRESS_HEARTBEAT_SECONDS):
            try:
                if heartbeat_callback is not None:
                    heartbeat_callback()
            except Exception as exc:
                heartbeat_errors.append(exc)
                return

    heartbeat_thread = None
    if heartbeat_callback is not None:
        heartbeat_thread = threading.Thread(target=report_heartbeat, daemon=True)
        heartbeat_thread.start()

    try:
        payload = {
            "model": MODEL_NAME,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": 0.2,
                "num_ctx": 4096,
                "num_predict": max_tokens,
            },
        }
        if json_format:
            payload["format"] = "json"

        with requests.post(
            OLLAMA_URL,
            json=payload,
            stream=True,
            timeout=REQUEST_TIMEOUT,
        ) as response:
            response.raise_for_status()
            response.encoding = "utf-8"
            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    update = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise RuntimeError(
                        "Ollama returned an invalid streaming response."
                    ) from exc
                if update.get("error"):
                    raise RuntimeError(f"Ollama generation failed: {update['error']}")
                text = update.get("response", "")
                if text:
                    response_text.append(text)
                    if progress_callback is not None:
                        progress_callback("".join(response_text))
    finally:
        heartbeat_stop.set()
        if heartbeat_thread is not None:
            heartbeat_thread.join()

    if heartbeat_errors:
        raise heartbeat_errors[0]

    generated_text = "".join(response_text).strip()
    if not generated_text:
        raise RuntimeError("Ollama returned an empty response.")
    return generated_text


def stream_ollama(
    prompt: str,
    max_tokens: int = 200,
    progress_callback: Callable[[str], None] | None = None,
    *,
    json_format: bool = True,
    heartbeat_callback: Callable[[], None] | None = None,
    provider: str | None = None,
) -> str:
    """Dispatches generation to active AI provider (Gemini, Grok, Groq, or Ollama fallback)."""
    active_provider = get_active_provider(provider)

    if active_provider == "gemini":
        try:
            return _stream_gemini(
                prompt,
                max_tokens=max_tokens,
                progress_callback=progress_callback,
                json_format=json_format,
                heartbeat_callback=heartbeat_callback,
            )
        except Exception as exc:
            # If Grok / Groq is configured, fail over automatically
            if os.getenv("XAI_API_KEY") or os.getenv("GROK_API_KEY"):
                print(f"[AI] Gemini call failed ({exc}); falling back to Grok.", flush=True)
                return _stream_grok(
                    prompt,
                    max_tokens=max_tokens,
                    progress_callback=progress_callback,
                    json_format=json_format,
                    heartbeat_callback=heartbeat_callback,
                )
            if os.getenv("GROQ_API_KEY"):
                print(f"[AI] Gemini call failed ({exc}); falling back to Groq.", flush=True)
                return _stream_groq(
                    prompt,
                    max_tokens=max_tokens,
                    progress_callback=progress_callback,
                    json_format=json_format,
                    heartbeat_callback=heartbeat_callback,
                )
            # Fall back to local Ollama if running on a machine with responsive Ollama
            if _is_local_ollama_available():
                print(f"[AI] Gemini call failed ({exc}); falling back to local Ollama.", flush=True)
                return _stream_ollama(
                    prompt,
                    max_tokens=max_tokens,
                    progress_callback=progress_callback,
                    json_format=json_format,
                    heartbeat_callback=heartbeat_callback,
                )
            raise

    if active_provider == "grok":
        try:
            return _stream_grok(
                prompt,
                max_tokens=max_tokens,
                progress_callback=progress_callback,
                json_format=json_format,
                heartbeat_callback=heartbeat_callback,
            )
        except Exception as exc:
            if _is_local_ollama_available():
                print(f"[AI] Grok call failed ({exc}); falling back to local Ollama.", flush=True)
                return _stream_ollama(
                    prompt,
                    max_tokens=max_tokens,
                    progress_callback=progress_callback,
                    json_format=json_format,
                    heartbeat_callback=heartbeat_callback,
                )
            raise

    if active_provider == "groq":
        try:
            return _stream_groq(
                prompt,
                max_tokens=max_tokens,
                progress_callback=progress_callback,
                json_format=json_format,
                heartbeat_callback=heartbeat_callback,
            )
        except Exception as exc:
            if _is_local_ollama_available():
                print(f"[AI] Groq call failed ({exc}); falling back to local Ollama.", flush=True)
                return _stream_ollama(
                    prompt,
                    max_tokens=max_tokens,
                    progress_callback=progress_callback,
                    json_format=json_format,
                    heartbeat_callback=heartbeat_callback,
                )
            raise

    return _stream_ollama(
        prompt,
        max_tokens=max_tokens,
        progress_callback=progress_callback,
        json_format=json_format,
        heartbeat_callback=heartbeat_callback,
    )


# Friendly alias
stream_ai = stream_ollama


def split_text(text: str, chunk_size: int = CHUNK_SIZE) -> list[str]:
    """Split extracted paper text into manageable chunks."""
    return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]


def _cache_path(paper_text: str, provider: str | None = None) -> Path:
    """Return a stable cache filename for this exact paper and configuration."""
    active = get_active_provider(provider)
    model = (
        os.getenv("GEMINI_MODEL", "gemini-2.5-flash") if active == "gemini"
        else os.getenv("GROK_MODEL", "grok-2-latest") if active == "grok"
        else os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile") if active == "groq"
        else MODEL_NAME
    )
    cache_key = f"{active}|{model}|{CHUNK_SIZE}|{paper_text}"
    digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{digest}.json"


def _save_cache(path: Path, data: dict) -> None:
    """Write cache data atomically so interrupted writes do not corrupt it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".tmp")
    temporary_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary_path, path)


def summarize_paper(
    paper_text: str,
    progress_callback: ProgressCallback = None,
    provider: str | None = None,
) -> str:
    """Summarize a paper and resume completed chunks from the local cache.

    Progress allocation:
      0-5%: upload handled by main.py
      5-15%: PDF text extraction handled by main.py
      15-85%: chunk summaries
      90%: final summary generation started
      92%: final summary successfully generated
    """

    def report(
        progress: int,
        message: str,
        partial_result: dict[str, Any] | None = None,
    ) -> None:
        if progress_callback is not None:
            progress_callback(progress, message, partial_result)

    if not paper_text.strip():
        raise ValueError("No paper text was provided.")

    start_time = time.time()
    chunks = split_text(paper_text)
    if not chunks:
        raise ValueError("No text chunks were created from the paper.")

    cache_path = _cache_path(paper_text, provider=provider)

    try:
        if cache_path.exists():
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        else:
            cache = {"chunk_summaries": {}, "final_summary": None}
    except (OSError, json.JSONDecodeError):
        cache = {"chunk_summaries": {}, "final_summary": None}

    # Reuse the final result if this exact paper was already summarized.
    if cache.get("final_summary"):
        print("[AI] Reusing cached final summary.", flush=True)
        report(92, "Summary loaded. Preparing paper classification...")
        return cache["final_summary"]

    total_chunks = len(chunks)
    print(f"[AI] Paper split into {total_chunks} chunks.", flush=True)
    chunk_summaries: list[str] = []

    try:
        for index, chunk in enumerate(chunks, start=1):
            cache_key = str(index)
            cached_summary = cache.get("chunk_summaries", {}).get(cache_key)

            if cached_summary:
                print(
                    f"[AI] Reusing cached chunk {index}/{total_chunks}.",
                    flush=True,
                )
                chunk_summaries.append(cached_summary)

            else:
                chunk_start = time.monotonic()
                print(
                    f"[AI] Summarizing chunk {index}/{total_chunks}...",
                    flush=True,
                )

                prompt = f"""You are ResearchMate, a research paper assistant.

Summarize this paper section in simple English. Keep only important methods,
facts, findings, and limitations. Do not invent information. This is only one
section of the paper. Return 3 to 5 concise bullet points.

PAPER SECTION:
{chunk}
"""

                partial_result = {
                    "partial_summary": "\n\n".join(chunk_summaries),
                    "chunks_completed": index - 1,
                    "total_chunks": total_chunks,
                }

                def report_chunk_heartbeat() -> None:
                    elapsed = int(time.monotonic() - chunk_start)
                    report(
                        15 + int(((index - 1) / total_chunks) * 70),
                        f"AI is analyzing section {index}/{total_chunks} "
                        f"({elapsed}s elapsed)...",
                        partial_result,
                    )

                report(
                    15 + int(((index - 1) / total_chunks) * 70),
                    f"AI is preparing section {index}/{total_chunks}...",
                    partial_result,
                )
                chunk_summary = stream_ollama(
                    prompt,
                    max_tokens=200,
                    json_format=False,
                    heartbeat_callback=report_chunk_heartbeat,
                    provider=provider,
                )
                chunk_summaries.append(chunk_summary)

                cache.setdefault("chunk_summaries", {})[cache_key] = chunk_summary
                _save_cache(cache_path, cache)

                print(
                    f"[AI] Chunk {index} completed in "
                    f"{time.monotonic() - chunk_start:.1f} seconds.",
                    flush=True,
                )

            # Cached and newly generated chunks both count as completed.
            progress = 15 + int((index / total_chunks) * 70)
            report(
                progress,
                f"Processing chunk {index}/{total_chunks}",
                {
                    "partial_summary": "\n\n".join(chunk_summaries),
                    "chunks_completed": index,
                    "total_chunks": total_chunks,
                },
            )

        report(
            90,
            "Creating the final summary...",
            {
                "partial_summary": "\n\n".join(chunk_summaries),
                "chunks_completed": total_chunks,
                "total_chunks": total_chunks,
            },
        )
        print("[AI] Creating the final summary...", flush=True)

        combined_text = "\n\n".join(chunk_summaries)
        final_start = time.monotonic()

        def report_final_heartbeat() -> None:
            elapsed = int(time.monotonic() - final_start)
            report(
                90,
                f"AI is creating the final summary ({elapsed}s elapsed)...",
                {
                    "partial_summary": combined_text,
                    "chunks_completed": total_chunks,
                    "total_chunks": total_chunks,
                },
            )

        final_prompt = f"""You are ResearchMate, an AI research paper assistant.

Explain this research paper to a beginner using simple English.
Use these sections:
1. Paper Overview
2. Problem Being Solved
3. Methodology
4. Key Findings
5. Limitations
6. Important Technical Terms
7. Final Takeaway

Use clear headings and bullet points. Explain technical terms in plain English.
Do not invent facts, statistics, or findings. If information is missing, state
that clearly. Combine repeated information.

SECTION SUMMARIES:
{combined_text}

Write one clear, well-organized final summary.
"""
        final_summary = stream_ollama(
            final_prompt,
            max_tokens=700,
            json_format=False,
            heartbeat_callback=report_final_heartbeat,
            provider=provider,
        )

        cache["final_summary"] = final_summary
        _save_cache(cache_path, cache)

        print(
            f"[AI] Total processing time: {time.time() - start_time:.1f} seconds.",
            flush=True,
        )
        report(92, "Summary completed. Preparing paper classification...")
        return final_summary

    except requests.exceptions.ConnectionError as exc:
        active = get_active_provider(provider)
        if active == "gemini":
            raise RuntimeError(
                "Could not connect to Google Gemini API. Please check internet connection or GEMINI_API_KEY."
            ) from exc
        if active == "grok":
            raise RuntimeError(
                "Could not connect to xAI Grok API. Please check internet connection or XAI_API_KEY / GROK_API_KEY."
            ) from exc
        if active == "groq":
            raise RuntimeError(
                "Could not connect to Groq API. Please check internet connection or GROQ_API_KEY."
            ) from exc
        is_cloud = bool(
            os.getenv("RENDER")
            or os.getenv("RENDER_SERVICE_ID")
            or "render" in os.getenv("FRONTEND_URL", "").lower()
        )
        if is_cloud:
            raise RuntimeError(
                "Cannot connect to Ollama from Cloud (Render). Ollama runs on your local computer at localhost:11434. "
                "To enable cloud summarization on Render, add GEMINI_API_KEY (free from Google AI Studio at aistudio.google.com), "
                "XAI_API_KEY, or GROQ_API_KEY in your Render Dashboard -> Environment Variables. "
                "Or switch your frontend target to 'Use Local' to use your local Ollama."
            ) from exc
        raise RuntimeError(
            "Cannot connect to Ollama. Ensure Ollama is running at localhost:11434, "
            "or configure an AI key (GEMINI_API_KEY / XAI_API_KEY / GROQ_API_KEY) in backend/.env."
        ) from exc

    except requests.exceptions.Timeout as exc:
        active = get_active_provider(provider)
        ai_name = "Gemini" if active == "gemini" else "Grok" if active == "grok" else "Groq" if active == "groq" else "Ollama"
        raise RuntimeError(
            f"{ai_name} timed out. Completed chunks were saved; retry the same PDF to resume."
        ) from exc

    except requests.exceptions.RequestException as exc:
        active = get_active_provider(provider)
        ai_name = "Gemini" if active == "gemini" else "Grok" if active == "grok" else "Groq" if active == "groq" else "Ollama"
        raise RuntimeError(f"{ai_name} request failed: {exc}") from exc
