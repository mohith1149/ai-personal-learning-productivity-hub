from fastapi import APIRouter

from app.routers import auth, courses, tasks

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(tasks.tasks_router)
api_router.include_router(tasks.categories_router)
api_router.include_router(tasks.recurring_router)
api_router.include_router(courses.courses_router)
api_router.include_router(courses.modules_router)
api_router.include_router(courses.lessons_router)
api_router.include_router(courses.sessions_router)
api_router.include_router(courses.templates_router)
