from fastapi import FastAPI, UploadFile, File, Form, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from dotenv import load_dotenv
import json
import os

from routes.auth import router as auth_router

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://ai-observability-copilot-frontend.vercel.app",
        "https://vercel.com/sumantk561s-projects/ai-observability-copilot-frontend/8No8dAgo8bXn98sTxLs8vhYs49YF",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)

log_history = []

# ------------------------
# Pattern Detection
# ------------------------
def detect_patterns(logs):
    error_count = sum(1 for log in logs if "ERROR" in log)
    warning_count = sum(1 for log in logs if "WARNING" in log)

    prediction = "Stable"
    if error_count > 3:
        prediction = "High chance of failure"
    elif warning_count > 5:
        prediction = "Potential instability"

    return {
        "error_count": error_count,
        "warning_count": warning_count,
        "prediction": prediction,
    }

# ------------------------
# Health Check
# ------------------------
@app.get("/")
def home():
    return {"message": "Backend running 🚀"}

# ------------------------
# Analyze API
# ------------------------
@app.post("/analyze")
async def analyze(
    file: UploadFile = File(...),
    api_key: str = Form(...)
):
    content = await file.read()
    logs = content.decode("utf-8")

    client = OpenAI(api_key=api_key)

    prompt = f"""
You are an SRE expert.

Return STRICT JSON:

{{
  "errors": [],
  "root_cause": "",
  "severity": "Low | Medium | High",
  "suggestions": []
}}

Logs:
{logs}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}],
        )

        content = response.choices[0].message.content.strip()

        try:
            return json.loads(content)
        except:
            return {
                "errors": [],
                "root_cause": "Parsing error",
                "severity": "Medium",
                "suggestions": [content],
            }

    except Exception as e:
        return {
            "errors": ["AI error"],
            "root_cause": str(e),
            "severity": "High",
            "suggestions": ["Check API key"],
        }

# ------------------------
# WebSocket
# ------------------------
@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    await websocket.accept()

    user_api_key = None

    try:
        while True:
            try:
                data = await websocket.receive_text()
            except WebSocketDisconnect:
                print("Client disconnected")
                break

            # Receive API key
            if data.startswith("API_KEY:"):
                user_api_key = data.replace("API_KEY:", "")
                continue

            if not user_api_key:
                continue

            log_history.append(data)
            if len(log_history) > 20:
                log_history.pop(0)

            pattern = detect_patterns(log_history)

            # AI CALL (throttled)
            try:
                client = OpenAI(api_key=user_api_key)

                response = client.chat.completions.create(
                    model="gpt-4.1-mini",
                    messages=[{"role": "user", "content": data}],
                )

                ai_content = response.choices[0].message.content

                try:
                    ai_json = json.loads(ai_content)
                except:
                    ai_json = {
                        "errors": [],
                        "root_cause": "Parsing error",
                        "severity": "Medium",
                        "suggestions": [],
                    }

            except Exception as e:
                ai_json = {
                    "errors": ["AI failed"],
                    "root_cause": str(e),
                    "severity": "High",
                    "suggestions": ["Check API key"],
                }

            final_output = {**ai_json, "metrics": pattern}

            try:
                await websocket.send_text(json.dumps(final_output))
            except:
                break

    finally:
        print("WebSocket closed")