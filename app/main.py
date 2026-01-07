from fastapi import FastAPI, UploadFile, File, Form, Depends
from sqlalchemy.orm import Session
from app.database import SessionLocal, engine
from app import models, calendar_logic
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import pandas as pd
import io
from datetime import datetime, timedelta
import os
import logging

# GitHub Actions test comment
# GitHub Actions test #2

# ----------------------------
# Configuration
# ----------------------------
models.Base.metadata.create_all(bind=engine)

SEMESTER_START = datetime(2026, 1, 19)
SEMESTER_END = datetime(2026, 5, 13)

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Group Schedule API")

# ----------------------------
# Static files
# ----------------------------

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def read_index():
    return FileResponse(os.path.join("static", "index.html"))

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ----------------------------
# Helpers
# ----------------------------

def generate_weekly_dates(start_date, end_date, weekday):
    """Return all dates between start and end that fall on weekday."""
    dates = []
    current = start_date
    while current.weekday() != weekday:
        current += timedelta(days=1)

    while current <= end_date:
        dates.append(current)
        current += timedelta(weeks=1)

    return dates

# ----------------------------
# Upload CSV
# ----------------------------

@app.post("/upload")
async def upload_csv(
    file: UploadFile = File(...),
    username: str = Form(...),
    db: Session = Depends(get_db)
):
    content = await file.read()
    df = pd.read_csv(io.BytesIO(content))

    user = models.User(username=username)
    db.add(user)
    db.commit()
    db.refresh(user)

    for _, row in df.iterrows():
        start_minutes = calendar_logic.time_to_minutes(row["Start Time"])
        end_minutes = calendar_logic.time_to_minutes(row["End Time"])
        start_date = datetime.strptime(row["Start Date"], "%m/%d/%Y")
        weekday_name = start_date.strftime("%A")

        event = models.ScheduleEvent(
            user_id=user.id,
            day=weekday_name,
            start=start_minutes,
            end=end_minutes
        )
        db.add(event)

    db.commit()

    return {
    "status": "uploaded",
    "username": username,
    "user_id": user.id   # <-- ADD THIS
    }

@app.get("/users")
def get_users(db: Session = Depends(get_db)):
    users = db.query(models.User).all()
    return [
        {"user_id": u.id, "username": u.username}
        for u in users
    ]

# ----------------------------
# Calendar endpoint
# ----------------------------

@app.get("/calendar")
def get_calendar(db: Session = Depends(get_db)):
    events = db.query(models.ScheduleEvent).all()

    if not events:
        return {"message": "No schedules uploaded yet."}

    grouped = {}
    for e in events:
        grouped.setdefault(e.user_id, []).append({
            "day": e.day,
            "start": e.start,
            "end": e.end,
            "user_id": e.user_id   # ✅ FIX
        })

    calendar_data = calendar_logic.compute_calendar(list(grouped.values()))
    return calendar_data

# ----------------------------
# Reset
# ----------------------------

@app.post("/reset")
def reset_schedules(db: Session = Depends(get_db)):
    db.query(models.ScheduleEvent).delete()
    db.query(models.User).delete()
    db.commit()
    logging.info("All schedules reset")
    return {"status": "reset"}
