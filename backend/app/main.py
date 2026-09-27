from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes import router
from backend.app.database import SessionLocal, initialize_schema
from backend.app.services.risk_cache import initialize_risk_snapshot

logger = logging.getLogger("nirikshan")


@asynccontextmanager
async def lifespan(app: FastAPI):
	initialize_schema()
	logger.info("Building Nirikshan risk snapshot...")
	db = SessionLocal()
	try:
		snapshot = initialize_risk_snapshot(db)
		logger.info("Risk snapshot ready: %s works", len(snapshot))
		yield
	except Exception:
		logger.exception("Nirikshan risk snapshot initialization failed")
		raise
	finally:
		db.close()

app = FastAPI(
	title="Nirikshan Investigation API",
	description="Read-only investigation views over MPLADS detection evidence.",
	version="1.0.0",
	lifespan=lifespan,
)

app.add_middleware(
	CORSMiddleware,
	allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
	allow_credentials=False,
	allow_methods=["GET"],
	allow_headers=["*"],
)

app.include_router(router)


@app.get("/health", tags=["system"], summary="Health check")
def health() -> dict[str, str]:
	return {"status": "ok"}
