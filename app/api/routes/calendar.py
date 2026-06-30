from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.registry import get_calendar
from app.api.deps import get_project_for_user
from app.db.models import CalendarEvent, CalendarEventAttendee, Project, ProjectMember
from app.db.session import get_db
from app.ports.calendar import CalendarEventDraft
from app.schemas import CalendarEventInput, CalendarEventOut

router = APIRouter(tags=["Calendar"])


@router.get("/projects/{project_id}/events", response_model=list[CalendarEventOut])
async def list_events(
    project: Project = Depends(get_project_for_user),
    db: AsyncSession = Depends(get_db),
) -> list[CalendarEvent]:
    result = await db.execute(
        select(CalendarEvent)
        .where(CalendarEvent.project_id == project.id)
        .order_by(CalendarEvent.starts_at.asc())
    )
    return list(result.scalars().all())


@router.post("/projects/{project_id}/events", response_model=CalendarEventOut, status_code=status.HTTP_201_CREATED)
async def create_event(
    body: CalendarEventInput,
    project: Project = Depends(get_project_for_user),
    db: AsyncSession = Depends(get_db),
) -> CalendarEvent:
    attendee_emails: list[str] = []
    for mid in body.attendee_member_ids:
        member = await db.get(ProjectMember, mid)
        if member and member.email:
            attendee_emails.append(member.email)

    calendar = get_calendar()
    external = await calendar.create_event(
        project.id,
        CalendarEventDraft(
            title=body.title,
            starts_at=body.starts_at,
            ends_at=body.ends_at,
            recurrence_rule=body.recurrence_rule,
            attendee_emails=attendee_emails,
            create_meet_link=body.create_meet_link,
        ),
    )

    event = CalendarEvent(
        project_id=project.id,
        title=body.title,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
        recurrence_rule=body.recurrence_rule,
        meet_link=external.meet_link,
        external_event_id=external.event_id,
    )
    db.add(event)
    await db.flush()

    for mid in body.attendee_member_ids:
        member = await db.get(ProjectMember, mid)
        db.add(
            CalendarEventAttendee(
                event_id=event.id,
                member_id=mid,
                email=member.email if member else None,
            )
        )

    await db.commit()
    await db.refresh(event)
    return event
