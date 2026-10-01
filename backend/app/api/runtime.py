from fastapi import APIRouter, Depends, Request

from app.api.dependencies import require_admin
from app.schemas import RuntimeResponse

router = APIRouter(prefix="/api/v1/admin", tags=["runtime"], dependencies=[Depends(require_admin)])


@router.get("/runtime", response_model=RuntimeResponse)
def runtime(request: Request):
    return request.app.state.scheduler.snapshot()
