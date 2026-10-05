"""AudienceIQ analytics API.

Run with:
    uvicorn backend.main:app --reload

The processing pipeline can insert rows into ``structured_posts``. This API
only reads the structured PostgreSQL data and exposes an overview payload for
the React dashboard.
"""

import os
import asyncio
import random
import uuid
from collections.abc import Generator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import DateTime, Integer, String, Text, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

try:
    from .nlp_engine import IndicNLPEngine
except ImportError:
    from nlp_engine import IndicNLPEngine


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5432/audienceiq",
)
CREATE_TABLES_ON_STARTUP = os.getenv("CREATE_TABLES_ON_STARTUP", "true").lower() in {
    "1",
    "true",
    "yes",
}

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=1800,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class StructuredPost(Base):
    """One NLP-processed social post.

    ``reach`` and ``engagement_count`` are stored as integer totals produced
    by the ingestion/processing pipeline. Sentiment labels are title-cased so
    they map directly to the API response buckets.
    """

    __tablename__ = "structured_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    post_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    sentiment_label: Mapped[str] = mapped_column(
        String(16), nullable=False, index=True
    )
    engagement_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reach: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    topic: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, index=True
    )
    demographic_group: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )


class MetricValue(BaseModel):
    value: int | float
    change: float | None = None


class SentimentBucket(BaseModel):
    count: int
    percentage: float


class SentimentResponse(BaseModel):
    total_posts: int
    positive: SentimentBucket
    neutral: SentimentBucket
    negative: SentimentBucket


class DemographicRow(BaseModel):
    label: str
    percentage: float


class PerformancePoint(BaseModel):
    month: str
    reach: int
    engagements: int


class TopPost(BaseModel):
    text: str
    reach: int
    engagement_rate: float


class NetworkNode(BaseModel):
    id: str
    label: str
    group: str
    value: int
    reach: int


class NetworkLink(BaseModel):
    source: str
    target: str


class NetworkResponse(BaseModel):
    nodes: list[NetworkNode]
    links: list[NetworkLink]


class OverviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    metrics: dict[str, MetricValue]
    sentiment: SentimentResponse
    demographics: list[DemographicRow]
    performance: list[PerformancePoint]
    monthly_trends: list[PerformancePoint]
    top_posts: list[TopPost]
    network: NetworkResponse


class AnalyzeRequest(BaseModel):
    text: str


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_: FastAPI):
    if CREATE_TABLES_ON_STARTUP:
        Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="AudienceIQ Analytics API",
    version="0.1.0",
    lifespan=lifespan,
)
nlp = IndicNLPEngine()

SYNC_POST_TEXTS = [
    "The product launch exceeded every expectation, and our onboarding was incredibly smooth.",
    "Bhai yeh delivery itni fast thi ki order karte hi aa gaya, maza aa gaya!",
    "The new fintech app makes tracking monthly expenses genuinely effortless.",
    "Markets are volatile this week, so I am keeping my portfolio diversified and patient.",
    "Our startup finally closed the seed round after months of investor conversations.",
    "Yaar customer support ne issue ekdum jaldi solve kar diya, very impressed.",
    "The dashboard looks polished, but the reporting filters still need serious work.",
    "This cloud service saved our team hours during the migration and scaled without drama.",
    "Honestly, the latest update broke notifications and the overall experience is frustrating.",
    "AI tools are changing how small teams prototype products with very limited budgets.",
    "Bakwaas checkout experience, payment fail hua aur refund ka koi clear update nahi hai.",
    "The quarterly results were steady, with strong revenue but cautious guidance ahead.",
    "Our founder story resonated with the community and brought in thoughtful early users.",
    "Naya feature kaafi useful hai, especially for teams managing multiple campaigns together.",
    "I am not convinced this valuation makes sense given the current interest-rate environment.",
    "The engineering team shipped the fix overnight and communication was excellent.",
    "Product-market fit is still a question; user growth looks promising but retention is mixed.",
    "This laptop is fast, quiet, and easily handles my daily development workload.",
    "Worst support experience ever, three tickets later and nobody has taken ownership.",
    "The local business community is collaborating on a practical digital payments workshop.",
    "Investors are watching the IPO pipeline closely as tech sentiment slowly improves.",
    "Bhai app ka interface clean hai, but thoda Hinglish support hota toh aur better hota.",
    "The campaign generated reach, although conversions were below the original forecast.",
    "Great value for money and the setup guide made deployment surprisingly simple.",
]
SYNC_TOPICS = [
    "Product", "Fintech", "Startups", "Technology", "Markets", "AI", "Customer experience"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173","https://audience-iq-eight.vercel.app/"],
    allow_origin_regex=r"https://audience-iq-.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


def as_number(value: Any) -> int:
    """Convert SQL aggregate values, including Decimal, to JSON-safe integers."""

    return int(value or 0)


def percentage(count: int, total: int) -> float:
    return round((count / total) * 100, 2) if total else 0.0


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/analyze")
async def analyze_text(request: AnalyzeRequest) -> dict[str, str | float]:
    return await nlp.analyze_text(request.text)


@app.post("/api/sync-live-data")
async def sync_live_data(db: Session = Depends(get_db)) -> dict[str, int | str]:
    """Generate, analyze, and append a realistic live-data batch."""

    await asyncio.sleep(4)
    now = datetime.now(timezone.utc)
    existing_count = db.scalar(select(func.count(StructuredPost.id))) or 0
    batch_size = 500 if existing_count < 100 else random.randint(5, 15)
    random_posts = [
        {
            "text": random.choice(SYNC_POST_TEXTS),
            "created_at": (
                now - timedelta(days=random.randint(0, 364))
                if existing_count < 100
                else now - timedelta(seconds=random.randint(0, 24 * 60 * 60))
            ),
            "reach": random.randint(1_000, 250_000),
            "engagement_count": random.randint(100, 25_000),
            "topic": random.choice(SYNC_TOPICS),
            "demographic_group": random.choice(["18-24", "25-34", "35-44", "45+"]),
        }
        for _ in range(batch_size)
    ]

    semaphore = asyncio.Semaphore(12)

    async def analyze_post(post: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str | float]]:
        async with semaphore:
            return post, await nlp.analyze_text(post["text"])

    analyzed_posts = await asyncio.gather(*(analyze_post(post) for post in random_posts))
    rows = [
        StructuredPost(
            platform="reddit",
            post_id=f"live_{uuid.uuid4().hex}",
            text=post["text"],
            sentiment_label=str(result["sentiment"]),
            engagement_count=post["engagement_count"],
            reach=post["reach"],
            topic=post["topic"],
            demographic_group=post["demographic_group"],
            created_at=post["created_at"],
        )
        for post, result in analyzed_posts
    ]

    try:
        db.add_all(rows)
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail="Live data could not be saved",
        ) from exc

    return {
        "status": "ok",
        "message": "Live data synced",
        "rows": len(rows),
        "total_rows": int(existing_count) + len(rows),
    }


@app.get("/analytics/overview", response_model=OverviewResponse)
def analytics_overview(db: Session = Depends(get_db)) -> OverviewResponse:
    """Return aggregate metrics used by the AudienceIQ overview dashboard."""

    try:
        reach, engagements, total_posts = db.execute(
            select(
                func.coalesce(func.sum(StructuredPost.reach), 0),
                func.coalesce(func.sum(StructuredPost.engagement_count), 0),
                func.count(StructuredPost.id),
            )
        ).one()

        sentiment_rows = db.execute(
            select(
                func.lower(StructuredPost.sentiment_label),
                func.count(StructuredPost.id),
            ).group_by(func.lower(StructuredPost.sentiment_label))
        ).all()

        monthly_rows = db.execute(
            select(
                func.to_char(StructuredPost.created_at, "YYYY-MM").label("month"),
                func.coalesce(func.sum(StructuredPost.reach), 0).label("reach"),
                func.coalesce(
                    func.sum(StructuredPost.engagement_count), 0
                ).label("engagements"),
            )
            .group_by("month")
            .order_by("month")
        ).all()
        demographic_rows = db.execute(
            select(
                StructuredPost.demographic_group,
                func.count(StructuredPost.id),
            )
            .where(StructuredPost.demographic_group.is_not(None))
            .group_by(StructuredPost.demographic_group)
            .order_by(func.count(StructuredPost.id).desc())
        ).all()
        topic_rows = db.execute(
            select(
                StructuredPost.topic,
                func.count(StructuredPost.id).label("post_count"),
                func.coalesce(func.sum(StructuredPost.reach), 0).label("reach"),
            )
            .where(StructuredPost.topic.is_not(None))
            .group_by(StructuredPost.topic)
            .order_by(func.count(StructuredPost.id).desc())
            .limit(12)
        ).all()
        top_post_rows = db.execute(
            select(
                StructuredPost.text,
                StructuredPost.reach,
                StructuredPost.engagement_count,
            )
            .order_by(StructuredPost.reach.desc())
            .limit(4)
        ).all()
    except Exception as exc:
        # Keep database failures explicit to clients while avoiding internal
        # connection details in the response.
        raise HTTPException(
            status_code=503,
            detail="Analytics data is temporarily unavailable",
        ) from exc

    total_reach = as_number(reach)
    total_engagements = as_number(engagements)
    post_count = as_number(total_posts)
    sentiment_counts = {"positive": 0, "neutral": 0, "negative": 0}
    for label, count in sentiment_rows:
        normalized = str(label or "").strip().lower()
        if normalized in sentiment_counts:
            sentiment_counts[normalized] = as_number(count)

    engagement_rate = (
        round((total_engagements / total_reach) * 100, 2) if total_reach else 0.0
    )
    sentiment = SentimentResponse(
        total_posts=post_count,
        **{
            label: SentimentBucket(
                count=count,
                percentage=percentage(count, post_count),
            )
            for label, count in sentiment_counts.items()
        },
    )
    network_nodes = [
        NetworkNode(
            id="topic_center",
            label="Audience topics",
            group="topic",
            value=post_count,
            reach=total_reach,
        )
    ]
    network_links = []
    for index, row in enumerate(topic_rows):
        topic_id = f"topic_{index}"
        network_nodes.append(
            NetworkNode(
                id=topic_id,
                label=str(row.topic),
                group="topic",
                value=as_number(row.post_count),
                reach=as_number(row.reach),
            )
        )
        network_links.append(NetworkLink(source="topic_center", target=topic_id))
    network = NetworkResponse(nodes=network_nodes, links=network_links)
    performance = [
        PerformancePoint(
            month=str(row.month),
            reach=as_number(row.reach),
            engagements=as_number(row.engagements),
        )
        for row in monthly_rows
    ]
    top_posts = [
        TopPost(
            text=str(row.text),
            reach=as_number(row.reach),
            engagement_rate=round(
                (as_number(row.engagement_count) / as_number(row.reach)) * 100,
                2,
            ) if as_number(row.reach) else 0.0,
        )
        for row in top_post_rows
    ]

    return OverviewResponse(
        metrics={
            "total_reach": MetricValue(value=total_reach),
            "total_engagements": MetricValue(value=total_engagements),
            "engagement_rate": MetricValue(value=engagement_rate),
            "total_posts": MetricValue(value=post_count),
        },
        sentiment=sentiment,
        demographics=[
            DemographicRow(
                label=str(label),
                percentage=percentage(as_number(count), post_count),
            )
            for label, count in demographic_rows
            if label
        ],
        performance=performance,
        monthly_trends=performance,
        top_posts=top_posts,
        network=network,
    )
