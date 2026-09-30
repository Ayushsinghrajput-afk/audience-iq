"""Async Hugging Face NLP adapter for AudienceIQ text processing."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

ENV_DIRECTORY = Path(__file__).resolve().parent
ENV_PATHS = (
    ENV_DIRECTORY / ".env",
    ENV_DIRECTORY / ".env.text",
    ENV_DIRECTORY / ".env.txt",
)
ENV_PATH = next((path for path in ENV_PATHS if path.is_file()), ENV_PATHS[0])
load_dotenv(dotenv_path=ENV_PATH)


class IndicNLPEngine:
    """Analyze multilingual and Hinglish text through Hugging Face Inference API.

    The engine intentionally fails soft: API outages, rate limits, missing
    credentials, malformed responses, and timeouts return a local heuristic
    result so ingestion can continue and retrying can happen upstream.
    """

    DEFAULT_MODEL_URL = (
        "https://router.huggingface.co/hf-inference/models/"
        "cardiffnlp/twitter-xlm-roberta-base-sentiment"
    )

    _POSITIVE_TERMS = {
        "amazing",
        "awesome",
        "best",
        "good",
        "great",
        "happy",
        "love",
        "loved",
        "superb",
        "अच्छा",
        "खुश",
        "शानदार",
        "पसंद",
    }
    _NEGATIVE_TERMS = {
        "awful",
        "bakwaas",
        "bad",
        "bekaar",
        "disappointed",
        "hate",
        "hated",
        "poor",
        "terrible",
        "waste",
        "बकवास",
        "खराब",
        "निराश",
    }

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model_url: str | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.api_key = api_key or os.getenv("HUGGINGFACE_API_KEY")
        self.model_url = (
            model_url
            or os.getenv("HUGGINGFACE_MODEL_URL")
            or self.DEFAULT_MODEL_URL
        )
        self.timeout = httpx.Timeout(timeout_seconds, connect=10.0)

    async def analyze_text(self, text: str) -> dict[str, str | float]:
        """Return normalized sentiment and confidence for ``text``."""

        if not text or not text.strip():
            return {"sentiment": "Neutral", "confidence": 0.0}

        if not self.api_key:
            logger.warning(
                "HUGGINGFACE_API_KEY is not configured; using local sentiment fallback"
            )
            return self._fallback(text)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.model_url,
                    headers=headers,
                    json={"inputs": text},
                )

            if response.status_code == 429:
                logger.warning("Hugging Face rate limit reached; using fallback")
                return self._fallback(text)

            response.raise_for_status()
            return self._normalize_response(response.json())
        except httpx.TimeoutException:
            logger.warning("Hugging Face request timed out; using fallback")
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Hugging Face request failed with HTTP %s; using fallback",
                exc.response.status_code,
            )
        except httpx.RequestError as exc:
            logger.warning("Hugging Face request error (%s); using fallback", exc)
        except (TypeError, ValueError, KeyError) as exc:
            logger.warning("Invalid Hugging Face response (%s); using fallback", exc)

        return self._fallback(text)

    @classmethod
    def _normalize_response(cls, payload: Any) -> dict[str, str | float]:
        """Normalize common HF text-classification response shapes."""

        candidates: Any = payload
        if (
            isinstance(payload, list)
            and payload
            and isinstance(payload[0], list)
        ):
            candidates = payload[0]

        if not isinstance(candidates, list) or not candidates:
            raise ValueError("Expected a non-empty list of label scores")

        scores = [
            item
            for item in candidates
            if isinstance(item, dict)
            and isinstance(item.get("label"), str)
            and isinstance(item.get("score"), (int, float))
        ]
        if not scores:
            raise ValueError("Response did not contain label scores")

        best = max(scores, key=lambda item: float(item["score"]))
        return {
            "sentiment": cls._normalize_label(str(best["label"])),
            "confidence": round(max(0.0, min(1.0, float(best["score"]))), 4),
        }

    @staticmethod
    def _normalize_label(label: str) -> str:
        normalized = label.strip().lower().replace("_", " ")

        if "positive" in normalized or normalized in {"label 2", "2"}:
            return "Positive"
        if "negative" in normalized or normalized in {"label 0", "0"}:
            return "Negative"
        if "neutral" in normalized or normalized in {"label 1", "1"}:
            return "Neutral"
        return "Neutral"

    @classmethod
    def _fallback(cls, text: str) -> dict[str, str | float]:
        """Use a small bilingual keyword heuristic when the API is unavailable."""

        normalized = text.casefold()
        words = set(normalized.replace("!", " ").replace(",", " ").split())
        positive_matches = len(words & cls._POSITIVE_TERMS)
        negative_matches = len(words & cls._NEGATIVE_TERMS)

        if negative_matches > positive_matches:
            sentiment = "Negative"
            matches = negative_matches
        elif positive_matches > negative_matches:
            sentiment = "Positive"
            matches = positive_matches
        else:
            sentiment = "Neutral"
            matches = 0

        confidence = min(0.9, 0.55 + matches * 0.1) if matches else 0.35
        return {"sentiment": sentiment, "confidence": round(confidence, 4)}


async def _test_engine() -> None:
    engine = IndicNLPEngine()
    result = await engine.analyze_text(
        "Bhai yeh product toh ekdum bakwaas hai, waste of money!"
    )
    print(result)


if __name__ == "__main__":
    asyncio.run(_test_engine())
