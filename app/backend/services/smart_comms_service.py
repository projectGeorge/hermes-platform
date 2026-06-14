"""Smart Comms service for conversation and message persistence."""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.backend.core.domain_enums import SmartCommsContextType, SmartCommsMessageRole
from app.backend.models.smart_comms_conversation import SmartCommsConversation
from app.backend.models.smart_comms_message import SmartCommsMessage


async def resolve_conversation(
    session: AsyncSession,
    *,
    user_id: UUID,
    context_type: SmartCommsContextType,
    context_id: UUID | None = None,
    route_path: str,
    title: str | None = None,
) -> SmartCommsConversation:
    """Resolve or create a conversation for a page context."""
    stmt = select(SmartCommsConversation).where(
        SmartCommsConversation.user_id == user_id,
        SmartCommsConversation.context_type == context_type,
        SmartCommsConversation.context_id == context_id,
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing is not None:
        return existing

    conversation = SmartCommsConversation(
        user_id=user_id,
        context_type=context_type,
        context_id=context_id,
        route_path=route_path,
        title=title,
    )
    session.add(conversation)
    await session.flush()
    return conversation


async def persist_user_message(
    session: AsyncSession,
    conversation_id: UUID,
    content: str,
) -> SmartCommsMessage:
    """Persist a user message in a conversation."""
    message = SmartCommsMessage(
        conversation_id=conversation_id,
        role=SmartCommsMessageRole.USER,
        content=content,
    )
    session.add(message)
    await session.flush()
    return message


async def persist_assistant_message(
    session: AsyncSession,
    conversation_id: UUID,
    content: str,
    extra_metadata: dict[str, object] | None = None,
) -> SmartCommsMessage:
    """Persist an assistant message after successful streaming."""
    message = SmartCommsMessage(
        conversation_id=conversation_id,
        role=SmartCommsMessageRole.ASSISTANT,
        content=content,
        extra_metadata=extra_metadata,
    )
    session.add(message)
    await session.flush()
    return message


async def get_conversation_or_404_for_user(
    session: AsyncSession,
    conversation_id: UUID,
    user_id: UUID,
) -> SmartCommsConversation | None:
    """Get a conversation only if it belongs to the given user, otherwise None."""
    conversation = await session.get(SmartCommsConversation, conversation_id)
    if conversation is None or conversation.user_id != user_id:
        return None
    return conversation


async def get_conversation_messages(
    session: AsyncSession,
    conversation_id: UUID,
) -> list[SmartCommsMessage]:
    """Get all messages for a conversation, ordered by creation time."""
    stmt = (
        select(SmartCommsMessage)
        .where(SmartCommsMessage.conversation_id == conversation_id)
        .order_by(SmartCommsMessage.created_at)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def delete_conversation(
    session: AsyncSession,
    conversation_id: UUID,
    user_id: UUID,
) -> None:
    """Delete a conversation and all its messages if it belongs to the user."""
    conversation = await session.get(SmartCommsConversation, conversation_id)
    if conversation is None or conversation.user_id != user_id:
        raise HTTPException(status_code=404, detail="Conversation not found")

    await session.execute(
        delete(SmartCommsMessage).where(SmartCommsMessage.conversation_id == conversation_id)
    )
    await session.delete(conversation)
    await session.flush()
