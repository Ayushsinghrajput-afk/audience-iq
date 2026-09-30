# AudienceIQ: Technical Architecture & Research Report
**Smart India Hackathon 2026 Submission**

## Executive Summary
While our presentation slides cover the high-level impact and business viability of AudienceIQ, this document details the engineering choices, architectural pivots, and underlying research that power the platform. Our goal was to build a highly scalable, real-time social intelligence dashboard tailored specifically for the Indian linguistic context, while maintaining zero proprietary SaaS lock-in.

## 1. Data Ingestion: The API Reality & Our Pivot
Modern social platforms have drastically fortified their perimeters against unauthenticated scraping. 

**The Challenge:** 
During initial development, we attempted asynchronous `.json` scraping of public Reddit endpoints via Python's `httpx`. We immediately hit `403 Forbidden` IP blocks caused by advanced anti-bot firewalls. Using outdated libraries like PRAW was also non-viable for a production-grade application.

**The Hackathon MVP Solution (Simulation Pipeline):**
To guarantee zero-downtime and a robust evaluation environment for the judges, we built a highly sophisticated incremental simulation pipeline. When the "Sync Live Data" endpoint is hit, the FastAPI backend dynamically generates randomized, context-rich social payloads in memory, bypassing network blocks while proving the end-to-end AI ingestion flow.

**The Enterprise Roadmap (OAuth2):**
For production, the architecture is designed to integrate official OAuth2 Client Credentials workflows. By registering the backend as an official developer application, we unlock enterprise rate limits (e.g., 100 requests/minute), ensuring compliant, continuous data streaming into our database.

## 2. The AI & NLP Core: Conquering the Language Gap
Standard western NLP models (like standard BERT or OpenAI APIs) struggle significantly with Indian social data, which is heavily code-mixed (Hinglish/Tanglish) and filled with localized slang.

*   **Foundational Research:** We leveraged research from AI4Bharat (IIT Madras) and implemented pre-trained **IndicBERT** variants tailored for Indian linguistic structures.
*   **Offloading Compute:** Running massive transformer models locally causes memory overflow on standard 16GB RAM machines. We bypassed this hardware limit by offloading inference to the **Hugging Face Inference API**.
*   **Bounded Concurrency:** To prevent crashing our application or hitting API rate limits during bulk ingestion (processing 500+ posts at once), we engineered a bounded concurrent processing queue in Python. This ensures our sentiment engine analyzes batches safely and asynchronously.

## 3. Backend & State Management
Our backend completely abandons heavy, bloated enterprise infrastructure (No Kafka, No Redis for the MVP) in favor of a lean, high-speed stack.

*   **FastAPI & ASGI:** Modeled on TechEmpower benchmarks, FastAPI serves our REST endpoints. Because it runs on Uvicorn (an ASGI server), it handles thousands of asynchronous requests concurrently without blocking the main thread.
*   **PostgreSQL & JSONB:** We utilize a relational PostgreSQL database via SQLAlchemy. The core `StructuredPost` model relies on `JSON/JSONB` metadata columns. This provides the strict schema of a SQL database while allowing flexible, schema-less storage for unpredictable social media metrics (likes, shares, upvotes).

## 4. Frontend Engineering: Visualizing Scale
Rendering thousands of data points on a web dashboard typically causes massive browser lag (DOM bloat). 

*   **Canvas-Based Rendering:** For our Influence Network mapping, we utilized `react-force-graph-2d`. Instead of rendering hundreds of HTML elements (which crashes the browser), it paints physics-based nodes and edges directly onto a WebGL/Canvas layer. This enables smooth zooming, panning, and hover hit-detection even with massive datasets.
*   **Real-time Polling & State:** The React/Vite frontend implements smart background polling (`setInterval` wrapped in `useEffect` hooks). It silently fetches delta updates from the backend every 15 seconds, ensuring the dashboard feels genuinely "live" without requiring the user to manually refresh.

## 5. Security & Deployment Rollout
The architecture is containerized and built for strict B2G (Business-to-Government) compliance.
*   **Data Sovereignty:** By packaging the entire FastAPI and PostgreSQL stack via Docker, it can be deployed entirely on-premise on secure National Informatics Centre (NIC) servers or private state-police clouds. No external analytics entity ever touches the government's internal tracking metrics.
*   **Scalability:** As the platform scales nationally, the architecture supports database sharding across regions, separating read-heavy analytical queries from write-heavy social ingestion streams.
