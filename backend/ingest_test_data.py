"""Seed AudienceIQ with realistic NLP-processed test posts.

Run from the repository root with:
    python -m backend.ingest_test_data

Or from inside the backend directory with:
    python ingest_test_data.py
"""

from __future__ import annotations

import asyncio
import logging
from random import SystemRandom
from uuid import uuid4

try:
    from .main import SessionLocal, StructuredPost
    from .nlp_engine import IndicNLPEngine
except ImportError:
    from main import SessionLocal, StructuredPost
    from nlp_engine import IndicNLPEngine

logger = logging.getLogger(__name__)
randomizer = SystemRandom()
nlp = IndicNLPEngine()

MOCK_POSTS: list[dict[str, str]] = [
    {
        "platform": "reddit",
        "text": "Bhai yeh product toh ekdum bakwaas hai, waste of money!",
    },
    {
        "platform": "telegram",
        "text": "Super fast delivery, maza aa gaya! Definitely recommend karunga.",
    },
    {
        "platform": "reddit",
        "text": "Quality theek hai but price thoda zyada hai, not sure if worth it.",
    },
    {
        "platform": "telegram",
        "text": "Customer support ne issue instantly solve kar diya, bahut badhiya service.",
    },
    {
        "platform": "reddit",
        "text": "Pehle acha laga tha, lekin latest update ke baad app bilkul slow ho gaya.",
    },
]

DEMOGRAPHIC_GROUPS = ("18-24", "25-34", "35-44", "45+")


def random_metrics() -> tuple[int, int]:
    reach = randomizer.randint(1_000, 50_000)
    engagements = randomizer.randint(100, min(5_000, reach))
    return reach, engagements


async def seed_database() -> int:
    """Analyze and insert the mock posts, returning the inserted row count."""

    db = SessionLocal()
    inserted = 0

    try:
        for index, post in enumerate(MOCK_POSTS, start=1):
            analysis = await nlp.analyze_text(post["text"])
            reach, engagements = random_metrics()

            row = StructuredPost(
                platform=post["platform"],
                post_id=f"seed-{uuid4().hex}",
                text=post["text"],
                sentiment_label=str(analysis["sentiment"]),
                engagement_count=engagements,
                reach=reach,
                topic="AudienceIQ seed data",
                demographic_group=randomizer.choice(DEMOGRAPHIC_GROUPS),
            )
            db.add(row)
            inserted += 1

            logger.info(
                "Processed seed post %d/%d: %s (confidence=%s)",
                index,
                len(MOCK_POSTS),
                analysis["sentiment"],
                analysis["confidence"],
            )

        db.commit()
        return inserted
    except Exception:
        db.rollback()
        logger.exception("Test data seeding failed; transaction rolled back")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    inserted_count = asyncio.run(seed_database())
    print(f"Successfully inserted {inserted_count} test posts into structured_posts.")
