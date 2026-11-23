from fastapi import APIRouter

from app.routers import auth, tasks

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(tasks.tasks_router)
api_router.include_router(tasks.categories_router)
api_router.include_router(tasks.recurring_router)
