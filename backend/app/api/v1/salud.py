from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db

router = APIRouter(tags=["salud"])


@router.get("/salud")
def salud(db: Session = Depends(get_db)) -> dict:
    db.execute(text("SELECT 1"))
    return {"estado": "ok"}
