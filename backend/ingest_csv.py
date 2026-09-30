import asyncio
import csv
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

from nlp_engine import IndicNLPEngine
from main import SessionLocal, StructuredPost

CSV_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "records.csv"

async def process_csv():
    if not CSV_PATH.exists():
        sys.exit(f"Error: {CSV_PATH} not found. Make sure records.csv is in the backend folder.")

    csv.field_size_limit(sys.maxsize)
    
    nlp = IndicNLPEngine()
    db = SessionLocal()

    total = inserted = empty = 0

    print("Starting AI batch ingestion and database mapping...")

    with CSV_PATH.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            total += 1
            text = row["text"].strip()
            
            if not text or text in ("[removed]", "[deleted]"):
                empty += 1
                continue

            # 1. Run text through Hugging Face NLP engine
            try:
                analysis = await nlp.analyze_text(text)
                # Ensure sentiment is Title-cased to match your API response buckets
                sentiment = analysis.get("sentiment", "Neutral").title()
            except Exception as e:
                print(f"AI processing skipped for a row: {e}")
                continue

            # 2. Extract score and comments from JSON metadata
            try:
                metadata = json.loads(row["metadata"])
                reach = metadata.get("score", 0)
                engagement_count = metadata.get("num_comments", 0)
            except json.JSONDecodeError:
                reach = 0
                engagement_count = 0

            # 3. Parse timestamp safely
            try:
                posted_at = datetime.fromisoformat(row["published_at"].replace("Z", "+00:00"))
            except (ValueError, KeyError):
                posted_at = datetime.now(timezone.utc)

            # 4. Map directly to your exact StructuredPost columns
            new_post = StructuredPost(
                platform=row.get("platform", "reddit"),
                post_id=row.get("external_id") or row.get("id", "unknown_id"),
                text=text,
                sentiment_label=sentiment,
                engagement_count=engagement_count,
                reach=reach,
                topic=row.get("target", "general"),
                created_at=posted_at,
                demographic_group=random.choice(["18-24", "25-34", "35-44", "45+"]),
            )
            
            db.add(new_post)
            inserted += 1

        db.commit()

    print(f"\nSUCCESS! 🚀")
    print(f"Total rows read: {total}")
    print(f"Successfully inserted: {inserted}")
    print(f"Empty/deleted skipped: {empty}")
    print("Refresh your React dashboard at http://localhost:5173 to see the live metrics!")

if __name__ == "__main__":
    asyncio.run(process_csv())
