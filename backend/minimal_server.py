#!/usr/bin/env python3
"""
Minimal backend server for testing without Redis/DB dependencies
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True, 
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/history")
async def history():
    # Return mock data for testing
    return {
        "s": "ok",
        "t": [1745831700, 1745832000, 1745832300],
        "o": [25400, 25420, 25440],
        "h": [25450, 25470, 25490], 
        "l": [25390, 25410, 25430],
        "c": [25430, 25450, 25470]
    }

@app.get("/marks")
async def marks():
    return {"marks": []}

@app.post("/api/labels")
async def create_label(data: dict):
    print(f"Label creation request: {data}")
    return {"success": True, "message": "Label saved (mock)"}

@app.delete("/api/labels") 
async def delete_label(data: dict):
    print(f"Label deletion request: {data}")
    return {"success": True, "message": "Label deleted (mock)"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8083)