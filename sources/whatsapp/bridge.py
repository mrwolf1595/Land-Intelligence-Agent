"""
Python FastAPI receiving WhatsApp messages.
"""
from fastapi import FastAPI, BackgroundTasks, HTTPException
import uvicorn
from core.database import save_message
from core.logger import get_logger
from pipeline.classifier import classify_message
from config import PYTHON_BRIDGE_PORT

app = FastAPI()
logger = get_logger("bridge")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "whatsapp-bridge"}


@app.post("/message")
async def receive_message(payload: dict, background_tasks: BackgroundTasks):
    """Receive message from Node.js WhatsApp client."""
    background_tasks.add_task(process_message, payload)
    return {"status": "queued"}


async def process_message(raw_msg: dict):
    classified = classify_message(raw_msg)
    if classified.get("msg_type") != "irrelevant":
        save_message(classified)
        logger.info(f"Saved {classified['msg_type']}: {classified.get('description', '')[:60]}")


@app.post("/test/message")
async def test_message(payload: dict):
    """For testing: accept a message without background processing."""
    try:
        classified = classify_message(payload)
        return {"classified": classified}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/test/ping")
async def test_ping():
    """For testing: simple connectivity check."""
    return {"pong": True}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PYTHON_BRIDGE_PORT)
