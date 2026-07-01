from fastapi import APIRouter

from app.api.routes import (
    admin,
    auth,
    bindings,
    calendar,
    confirmations,
    connections,
    documents,
    meetings,
    members,
    milestones,
    notifications,
    numbering,
    projects,
    tasks,
    templates,
    traceability,
    webhooks,
    liff,
)

api_router = APIRouter(prefix="/v1")
api_router.include_router(admin.router)
api_router.include_router(webhooks.router)
api_router.include_router(auth.router)
api_router.include_router(liff.router)
api_router.include_router(projects.router)
api_router.include_router(members.router)
api_router.include_router(connections.router)
api_router.include_router(bindings.router)
api_router.include_router(templates.router)
api_router.include_router(numbering.router)
api_router.include_router(documents.router)
api_router.include_router(tasks.router)
api_router.include_router(milestones.router)
api_router.include_router(meetings.router)
api_router.include_router(calendar.router)
api_router.include_router(traceability.router)
api_router.include_router(confirmations.router)
api_router.include_router(notifications.router)
