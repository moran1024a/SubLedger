from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.models import User
from app.schemas import StatisticsResponse
from app.services.statistics import summary

router = APIRouter(prefix="/api/v1/statistics", tags=["statistics"])


@router.get("/summary", response_model=StatisticsResponse)
def statistics_summary(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return summary(db, user)
