"""Dashboard endpoint. Login required."""
from fastapi import APIRouter

from app.core.deps import CurrentUser, DbSession
from app.schemas import dashboard as s
from app.services import dashboard as svc

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=s.Dashboard)
def get_dashboard(user: CurrentUser, db: DbSession):
    """Today at a glance, computed from your real data on every request."""
    return svc.build(db, user)
