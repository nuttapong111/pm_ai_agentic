from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_project_for_user
from app.db.models import Project, Requirement, Task, TestCase, TraceabilityLink
from app.db.session import get_db
from app.schemas import TraceabilityCoverage, TraceabilityLinkInput

router = APIRouter(tags=["Traceability"])


@router.get("/projects/{project_id}/traceability", response_model=list[TraceabilityCoverage])
async def get_traceability(
    project: Project = Depends(get_project_for_user),
    db: AsyncSession = Depends(get_db),
) -> list[TraceabilityCoverage]:
    reqs = await db.execute(select(Requirement).where(Requirement.project_id == project.id))
    requirements = list(reqs.scalars().all())
    coverage_list: list[TraceabilityCoverage] = []

    for req in requirements:
        links = await db.execute(
            select(TraceabilityLink).where(TraceabilityLink.requirement_id == req.id)
        )
        link_rows = list(links.scalars().all())
        task_keys: list[str] = []
        test_codes: list[str] = []
        has_task = False
        has_test = False

        for link in link_rows:
            if link.task_id:
                has_task = True
                task = await db.get(Task, link.task_id)
                if task:
                    ref = task.external_ref or {}
                    task_keys.append(ref.get("key", str(task.id)[:8]))
            if link.test_case_id:
                has_test = True
                tc = await db.get(TestCase, link.test_case_id)
                if tc:
                    test_codes.append(tc.code)

        if has_task and has_test:
            cov = "covered"
        elif has_task:
            cov = "missing_test"
        else:
            cov = "no_task"

        coverage_list.append(
            TraceabilityCoverage(
                requirement_id=req.id,
                code=req.code,
                title=req.title,
                coverage=cov,
                task_keys=task_keys,
                test_case_codes=test_codes,
            )
        )
    return coverage_list


@router.post("/projects/{project_id}/traceability/requirements", status_code=status.HTTP_201_CREATED)
async def create_requirement(
    body: dict,
    project: Project = Depends(get_project_for_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    req = Requirement(
        project_id=project.id,
        code=body.get("code", f"REQ-{body.get('seq', '001')}"),
        title=body.get("title", "Requirement"),
        description=body.get("description"),
    )
    db.add(req)
    await db.commit()
    await db.refresh(req)
    return {"id": str(req.id), "code": req.code}


@router.post("/projects/{project_id}/traceability/test-cases", status_code=status.HTTP_201_CREATED)
async def create_test_case(
    body: dict,
    project: Project = Depends(get_project_for_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    tc = TestCase(
        project_id=project.id,
        code=body.get("code", "TC-001"),
        title=body.get("title", "Test case"),
        requirement_id=UUID(body["requirementId"]) if body.get("requirementId") else None,
        steps=body.get("steps", []),
        expected_result=body.get("expectedResult"),
    )
    db.add(tc)
    await db.commit()
    await db.refresh(tc)
    return {"id": str(tc.id), "code": tc.code}


@router.post("/projects/{project_id}/traceability/links", status_code=status.HTTP_201_CREATED)
async def create_traceability_link(
    body: TraceabilityLinkInput,
    project: Project = Depends(get_project_for_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    if bool(body.task_id) == bool(body.test_case_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="ต้องระบุ taskId หรือ testCaseId อย่างใดอย่างหนึ่ง",
        )

    req = await db.get(Requirement, body.requirement_id)
    if not req or req.project_id != project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ไม่พบ requirement")

    link = TraceabilityLink(
        project_id=project.id,
        requirement_id=body.requirement_id,
        task_id=body.task_id,
        test_case_id=body.test_case_id,
    )
    db.add(link)
    await db.commit()
    return {"status": "created"}
