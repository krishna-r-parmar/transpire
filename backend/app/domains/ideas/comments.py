"""Review comments on ideas awaiting approval.

Colleagues consulted on a step (a notification group, or other HoDs) add advice; the
approver and the submitter reply. Comments never block a decision, but an approver who has
not replied to a comment must confirm before deciding.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.tenant_context import apply_tenant_to_transaction
from app.domains.audit.controllers import record_audit_event
from app.domains.ideas.approval_notifications import (
    APPROVAL_PREFERENCE,
    _context,
    _send,
    wants_email,
)
from app.domains.ideas.models import (
    Idea,
    IdeaApprovalStage,
    IdeaComment,
    IdeaStatus,
    IdeaStepConsultation,
)
from app.domains.identity.access import can_contribute, is_workspace_admin
from app.domains.identity.models import User

MAX_COMMENT_LENGTH = 4000


class CommentCommand(BaseModel):
    body: str = Field(min_length=1, max_length=MAX_COMMENT_LENGTH)
    parent_id: uuid.UUID | None = None


class CommentRecord(BaseModel):
    id: uuid.UUID
    parent_id: uuid.UUID | None
    round_number: int
    author_name: str
    author_role: str  # "approver" | "submitter" | "consulted" | "admin"
    body: str
    created_at: datetime
    is_mine: bool


class CommentThread(BaseModel):
    comments: list[CommentRecord]
    can_comment: bool
    consulted_on: list[str]
    unanswered_for_me: int


class CommentNotFoundError(Exception):
    pass


class CommentForbiddenError(Exception):
    pass


async def _current_round(session: AsyncSession, idea: Idea) -> int:
    return int(
        await session.scalar(
            select(func.coalesce(func.max(IdeaApprovalStage.round_number), 1)).where(
                IdeaApprovalStage.tenant_id == idea.tenant_id, IdeaApprovalStage.idea_id == idea.id
            )
        )
        or 1
    )


async def _participants(
    session: AsyncSession, idea: Idea
) -> tuple[set[uuid.UUID], dict[uuid.UUID, list[str]], set[uuid.UUID]]:
    approver_ids = {
        user_id
        for user_id in (
            await session.scalars(
                select(IdeaApprovalStage.assignee_user_id).where(
                    IdeaApprovalStage.tenant_id == idea.tenant_id,
                    IdeaApprovalStage.idea_id == idea.id,
                    IdeaApprovalStage.status.not_in(("waiting", "skipped")),
                )
            )
        ).all()
        if user_id
    }
    consulted: dict[uuid.UUID, list[str]] = {}
    for consultation in (
        await session.scalars(
            select(IdeaStepConsultation).where(
                IdeaStepConsultation.tenant_id == idea.tenant_id,
                IdeaStepConsultation.idea_id == idea.id,
            )
        )
    ).all():
        for raw in consultation.user_ids:
            consulted.setdefault(uuid.UUID(raw), []).append(consultation.stage_name)
    pending = {
        user_id
        for user_id in (
            await session.scalars(
                select(IdeaApprovalStage.assignee_user_id).where(
                    IdeaApprovalStage.tenant_id == idea.tenant_id,
                    IdeaApprovalStage.idea_id == idea.id,
                    IdeaApprovalStage.status == "pending",
                )
            )
        ).all()
        if user_id
    }
    return approver_ids, consulted, pending


async def unanswered_for(
    session: AsyncSession, idea: Idea, approver_id: uuid.UUID, round_number: int
) -> int:
    """Comments in this round from other people that the approver has not replied to."""
    comments = list(
        (
            await session.scalars(
                select(IdeaComment).where(
                    IdeaComment.tenant_id == idea.tenant_id,
                    IdeaComment.idea_id == idea.id,
                    IdeaComment.round_number == round_number,
                )
            )
        ).all()
    )
    answered = {
        comment.parent_id
        for comment in comments
        if comment.parent_id and comment.author_user_id == approver_id
    }
    return sum(
        1
        for comment in comments
        if comment.parent_id is None
        and comment.author_user_id != approver_id
        and comment.author_user_id != idea.submitter_user_id
        and comment.id not in answered
    )


async def _load(session: AsyncSession, tenant_id: uuid.UUID, idea_id: uuid.UUID) -> Idea:
    idea = await session.scalar(select(Idea).where(Idea.tenant_id == tenant_id, Idea.id == idea_id))
    if idea is None:
        raise CommentNotFoundError
    return idea


def _may_comment(
    idea: Idea,
    user_id: uuid.UUID,
    roles: list[str],
    approvers: set[uuid.UUID],
    consulted: dict[uuid.UUID, list[str]],
) -> bool:
    if idea.status != IdeaStatus.SUBMITTED or not can_contribute(roles):
        return False
    return (
        user_id == idea.submitter_user_id
        or user_id in approvers
        or user_id in consulted
        or is_workspace_admin(roles)
    )


async def get_comment_thread(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    roles: list[str],
    idea_id: uuid.UUID,
    session: AsyncSession,
) -> CommentThread:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        idea = await _load(session, tenant_id, idea_id)
        approvers, consulted, pending = await _participants(session, idea)
        visible = (
            user_id == idea.submitter_user_id
            or user_id in approvers
            or user_id in consulted
            or is_workspace_admin(roles)
        )
        if not visible:
            raise CommentForbiddenError
        rows = (
            await session.execute(
                select(IdeaComment, User.display_name)
                .join(User, User.id == IdeaComment.author_user_id)
                .where(IdeaComment.tenant_id == tenant_id, IdeaComment.idea_id == idea_id)
                .order_by(IdeaComment.created_at)
            )
        ).all()

        def role_of(author: uuid.UUID) -> str:
            if author == idea.submitter_user_id:
                return "submitter"
            if author in approvers:
                return "approver"
            if author in consulted:
                return "consulted"
            return "admin"

        current_round = await _current_round(session, idea)
        return CommentThread(
            comments=[
                CommentRecord(
                    id=comment.id,
                    parent_id=comment.parent_id,
                    round_number=comment.round_number,
                    author_name=name,
                    author_role=role_of(comment.author_user_id),
                    body=comment.body,
                    created_at=comment.created_at,
                    is_mine=comment.author_user_id == user_id,
                )
                for comment, name in rows
            ],
            can_comment=_may_comment(idea, user_id, roles, approvers, consulted),
            consulted_on=consulted.get(user_id, []),
            unanswered_for_me=await unanswered_for(session, idea, user_id, current_round)
            if user_id in pending
            else 0,
        )


async def post_comment(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    roles: list[str],
    idea_id: uuid.UUID,
    command: CommentCommand,
    settings: Settings,
    session: AsyncSession,
) -> CommentThread:
    async with session.begin():
        await apply_tenant_to_transaction(session, tenant_id)
        idea = await _load(session, tenant_id, idea_id)
        approvers, consulted, pending = await _participants(session, idea)
        if not _may_comment(idea, user_id, roles, approvers, consulted):
            raise CommentForbiddenError
        parent = None
        if command.parent_id:
            parent = await session.scalar(
                select(IdeaComment).where(
                    IdeaComment.tenant_id == tenant_id,
                    IdeaComment.idea_id == idea_id,
                    IdeaComment.id == command.parent_id,
                )
            )
            if parent is None:
                raise CommentNotFoundError
            if parent.parent_id is not None:
                parent = await session.get(IdeaComment, parent.parent_id)  # one level of replies
        comment = IdeaComment(
            tenant_id=tenant_id,
            idea_id=idea_id,
            round_number=await _current_round(session, idea),
            author_user_id=user_id,
            parent_id=parent.id if parent else None,
            body=command.body.strip(),
        )
        session.add(comment)
        await session.flush()
        author = await session.get(User, user_id)
        record_audit_event(
            session,
            tenant_id=tenant_id,
            actor_user_id=user_id,
            subject_user_id=idea.submitter_user_id,
            event_type="idea.comment_added",
            entity_type="idea",
            entity_id=idea.id,
            entity_reference=idea.reference,
            summary=f"{author.display_name if author else 'Someone'} commented on {idea.reference}.",
            details={"comment_id": str(comment.id), "reply": parent is not None},
        )
        # Tell whoever needs to act on it: the current approvers for new advice, and the
        # original author for a reply. Never email the author about their own comment.
        recipients: set[uuid.UUID] = set()
        if parent is None:
            recipients |= pending
        else:
            recipients.add(parent.author_user_id)
            recipients |= pending if parent.author_user_id != user_id else set()
        recipients.discard(user_id)
        if recipients:
            _, _, data = await _context(session, idea, settings)
            excerpt = comment.body if len(comment.body) <= 600 else f"{comment.body[:600]}…"
            for recipient in (
                await session.scalars(select(User).where(User.id.in_(recipients)))
            ).all():
                if not wants_email(recipient, APPROVAL_PREFERENCE):
                    continue
                _send(
                    session,
                    settings,
                    idea,
                    recipient=recipient,
                    template_key="comment_posted",
                    subject=f"{author.display_name if author else 'A colleague'} commented on "
                    f"{idea.reference}",
                    data={
                        **data,
                        "author_name": author.display_name if author else "A colleague",
                        "comment": excerpt,
                        "is_reply": "yes" if parent else "",
                        "action_label": "Read and reply",
                    },
                )
    return await get_comment_thread(tenant_id, user_id, roles, idea_id, session)
