"""This module contains the ORM for managing content in the `ContentDB` database and
database helper functions such as saving, updating, deleting, and retrieving content.
"""

from datetime import datetime, timezone
from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    delete,
    false,
    select,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship, selectinload

from ..config import (
    PGVECTOR_DISTANCE,
    PGVECTOR_EF_CONSTRUCTION,
    PGVECTOR_M,
    PGVECTOR_VECTOR_SIZE,
)
from ..models import Base, JSONDict
from ..schemas import FeedbackSentiment, QuerySearchResult
from ..tags.models import content_tags_table
from ..utils import embedding
from .schemas import ContentCreate, ContentUpdate


class ContentDB(Base):
    """ORM for managing content.

    This database ties into the Admin app and allows the user to view, add, edit,
    and delete content in the `content` table.
    """

    __tablename__ = "content"
    __table_args__ = (
        Index(
            "ix_content_embedding",
            "content_embedding",
            postgresql_using="hnsw",
            postgresql_with={
                "M": {PGVECTOR_M},
                "ef_construction": {PGVECTOR_EF_CONSTRUCTION},
            },
            postgresql_ops={"embedding": {PGVECTOR_DISTANCE}},
        ),
    )

    content_embedding: Mapped[Vector] = mapped_column(
        Vector(int(PGVECTOR_VECTOR_SIZE)), nullable=False
    )
    content_id: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)
    content_metadata: Mapped[JSONDict] = mapped_column(JSON, nullable=False)
    content_tags = relationship(
        "TagDB", secondary=content_tags_table, back_populates="contents"
    )
    content_text: Mapped[str] = mapped_column(String(length=2000), nullable=False)
    content_title: Mapped[str] = mapped_column(String(length=150), nullable=False)
    created_datetime_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    display_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    positive_votes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    negative_votes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    query_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_datetime_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    workspace_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workspace.workspace_id", ondelete="CASCADE"),
        nullable=False,
    )

    def __repr__(self) -> str:
        """Construct the string representation of the `ContentDB` object.

        Returns
        -------
        str
            A string representation of the `ContentDB` object.
        """

        return (
            f"ContentDB(content_id={self.content_id}, "
            f"content_embedding=..., "
            f"content_title={self.content_title}, "
            f"content_text={self.content_text}, "
            f"content_metadata={self.content_metadata}, "
            f"content_tags={self.content_tags}, "
            f"created_datetime_utc={self.created_datetime_utc}, "
            f"display_number={self.display_number}, "
            f"is_archived={self.is_archived}), "
            f"updated_datetime_utc={self.updated_datetime_utc}), "
            f"workspace_id={self.workspace_id}"
        )


async def save_content_to_db(
    *,
    asession: AsyncSession,
    content: ContentCreate,
    exclude_archived: bool = False,
    workspace_id: int,
) -> ContentDB:
    """Vectorize the content and save to the database.

    Parameters
    ----------
    asession
        The SQLAlchemy async session to use for all database connections.
    content
        The content to save.
    exclude_archived
        Specifies whether to exclude archived content.
    workspace_id
        The ID of the workspace to save the content to.

    Returns
    -------
    ContentDB
        The content object if it exists, otherwise the newly created content object.
    """

    metadata = {
        "trace_workspace_id": "workspace_id-" + str(workspace_id),
        "generation_name": "save_content_to_db",
    }

    content_embedding = await _get_content_embeddings(
        content=content, metadata=metadata
    )
    latest_display_number = await get_latest_display_number(
        asession=asession, workspace_id=workspace_id
    )
    content_db = ContentDB(
        content_embedding=content_embedding,
        content_metadata=content.content_metadata,
        content_tags=content.content_tags,
        content_text=content.content_text,
        content_title=content.content_title,
        display_number=latest_display_number + 1,
        created_datetime_utc=datetime.now(timezone.utc),
        updated_datetime_utc=datetime.now(timezone.utc),
        workspace_id=workspace_id,
    )
    asession.add(content_db)

    await asession.commit()
    await asession.refresh(content_db)

    result = await get_content_from_db(
        asession=asession,
        content_id=content_db.content_id,
        exclude_archived=exclude_archived,
        workspace_id=content_db.workspace_id,
    )
    return result or content_db


async def update_content_in_db(
    *,
    asession: AsyncSession,
    content: ContentCreate,
    content_id: int,
    workspace_id: int,
) -> ContentDB:
    """Update content and content embedding in the database.

    NB: The path operation that invokes this function should disallow archived content
    to be updated.

    Parameters
    ----------
    asession
        The SQLAlchemy async session to use for all database connections.
    content
        The content to update.
    content_id
        The ID of the content to update.
    workspace_id
        The ID of the workspace to update the content in.

    Returns
    -------
    ContentDB
        The content object if it exists, otherwise the newly updated content object.
    """

    metadata = {
        "trace_workspace_id": "workspace_id-" + str(workspace_id),
        "generation_name": "update_content_in_db",
    }

    content_embedding = await _get_content_embeddings(
        content=content, metadata=metadata
    )
    content_db = ContentDB(
        content_embedding=content_embedding,
        content_id=content_id,
        content_metadata=content.content_metadata,
        content_tags=content.content_tags,
        content_text=content.content_text,
        content_title=content.content_title,
        is_archived=content.is_archived,
        updated_datetime_utc=datetime.now(timezone.utc),
        workspace_id=workspace_id,
    )

    content_db = await asession.merge(content_db)
    await asession.commit()
    await asession.refresh(content_db)
    result = await get_content_from_db(
        asession=asession,
        content_id=content_db.content_id,
        exclude_archived=False,  # Don't exclude for newly updated content!
        workspace_id=content_db.workspace_id,
    )

    return result or content_db


async def archive_content_from_db(
    *, asession: AsyncSession, content_id: int, workspace_id: int
) -> None:
    """Archive content from the database.

    Parameters
    ----------
    asession
        The SQLAlchemy async session to use for all database connections.
    content_id
        The ID of the content to archived.
    workspace_id
        The ID of the workspace to archive the content from.
    """

    stmt = (
        update(ContentDB)
        .where(ContentDB.workspace_id == workspace_id)
        .where(ContentDB.content_id == content_id)
        .values(is_archived=True)
    )
    await asession.execute(stmt)
    await asession.commit()


async def delete_content_from_db(
    *, asession: AsyncSession, content_id: int, workspace_id: int
) -> None:
    """Delete content from the database.

    Parameters
    ----------
    asession
        The SQLAlchemy async session to use for all database connections.
    content_id
        The ID of the content to delete.
    workspace_id
        The ID of the workspace to delete the content from.
    """

    association_stmt = delete(content_tags_table).where(
        content_tags_table.c.content_id == content_id
    )
    await asession.execute(association_stmt)
    stmt = (
        delete(ContentDB)
        .where(ContentDB.workspace_id == workspace_id)
        .where(ContentDB.content_id == content_id)
    )
    await asession.execute(stmt)
    await asession.commit()


async def get_content_from_db(
    *,
    asession: AsyncSession,
    content_id: int,
    exclude_archived: bool = True,
    workspace_id: int,
) -> ContentDB | None:
    """Retrieve content from the database.

    Parameters
    ----------
    asession
        The SQLAlchemy async session to use for all database connections.
    content_id
        The ID of the content to retrieve.
    exclude_archived
        Specifies whether to exclude archived content.
    workspace_id
        The ID of the workspace requesting the content.

    Returns
    -------
    ContentDB
        The content object if it exists, otherwise `None`.
    """

    stmt = (
        select(ContentDB)
        .options(selectinload(ContentDB.content_tags))
        .where(ContentDB.workspace_id == workspace_id)
        .where(ContentDB.content_id == content_id)
    )
    if exclude_archived:
        stmt = stmt.where(ContentDB.is_archived == false())
    content_row = (await asession.execute(stmt)).first()
    return content_row[0] if content_row else None


async def get_list_of_content_from_db(
    *,
    asession: AsyncSession,
    exclude_archived: bool = True,
    limit: Optional[int] = None,
    offset: int = 0,
    workspace_id: int,
) -> list[ContentDB]:
    """Retrieve all content from the database for the specified workspace.

    Parameters
    ----------
    asession
        The SQLAlchemy async session to use for all database connections.
    exclude_archived
        Specifies whether to exclude archived content.
    limit
        The maximum number of content items to retrieve. If not specified, then all
        content items are retrieved.
    offset
        The number of content items to skip.
    workspace_id
        The ID of the workspace to retrieve content from.

    Returns
    -------
    list[ContentDB]
        A list of content objects in the specified workspace if they exist, otherwise
    an empty list.
    """

    stmt = (
        select(ContentDB)
        .options(selectinload(ContentDB.content_tags))
        .where(ContentDB.workspace_id == workspace_id)
        .order_by(ContentDB.display_number)
    )
    if exclude_archived:
        stmt = stmt.where(ContentDB.is_archived == false())
    if offset > 0:
        stmt = stmt.offset(offset)
    if isinstance(limit, int) and limit > 0:
        stmt = stmt.limit(limit)
    content_rows = (await asession.execute(stmt)).all()
    return [c[0] for c in content_rows] if content_rows else []


async def _get_content_embeddings(
    *, content: ContentCreate | ContentUpdate, metadata: Optional[dict] = None
) -> list[float]:
    """Vectorize the content.

    Parameters
    ----------
    content
        The content to vectorize.
    metadata
        The metadata to use for the embedding generation.

    Returns
    -------
    list[float]
        The vectorized content embedding.
    """

    text_to_embed = content.content_title + "\n" + content.content_text
    return await embedding(metadata=metadata, text_to_embed=text_to_embed)


async def get_similar_content_async(
    *,
    asession: AsyncSession,
    exclude_archived: bool = True,
    metadata: Optional[dict] = None,
    n_similar: int,
    question: str,
    workspace_id: int,
) -> dict[int, QuerySearchResult]:
    """Get the most similar points in the vector table.

    Parameters
    ----------
    asession
        The SQLAlchemy async session to use for all database connections.
    exclude_archived
        Specifies whether to exclude archived content.
    metadata
        The metadata to use for the embedding generation
    n_similar
        The number of similar content items to retrieve.
    question
        The question to search for similar content.
    workspace_id
        The ID of the workspace to search for similar content in.

    Returns
    -------
    dict[int, QuerySearchResult]
        A dictionary of similar content items if they exist, otherwise an empty
        dictionary.
    """

    metadata = metadata or {}
    metadata["generation_name"] = "get_similar_content_async"

    question_embedding = await embedding(metadata=metadata, text_to_embed=question)

    return await get_search_results(
        asession=asession,
        exclude_archived=exclude_archived,
        n_similar=n_similar,
        question_embedding=question_embedding,
        workspace_id=workspace_id,
    )


async def get_search_results(
    *,
    asession: AsyncSession,
    exclude_archived: bool = True,
    n_similar: int,
    question_embedding: list[float],
    workspace_id: int,
) -> dict[int, QuerySearchResult]:
    """Get similar content to given embedding and return search results.

    NB: We first exclude archived content and then order by the cosine distance.

    Parameters
    ----------
    asession
        The SQLAlchemy async session to use for all database connections.
    exclude_archived
        Specifies whether to exclude archived content.
    n_similar
        The number of similar content items to retrieve.
    question_embedding
        The embedding vector of the question to search for.
    workspace_id
        The ID of the workspace to search for similar content in.

    Returns
    -------
    dict[int, QuerySearchResult]
        A dictionary of similar content items if they exist, otherwise an empty
        dictionary.
    """

    distance = ContentDB.content_embedding.cosine_distance(question_embedding).label(
        "distance"
    )

    query = select(ContentDB, distance).where(ContentDB.workspace_id == workspace_id)

    if exclude_archived:
        query = query.where(ContentDB.is_archived == false())

    query = query.order_by(distance).limit(n_similar)

    search_result = (await asession.execute(query)).all()

    results_dict = {}
    for i, r in enumerate(search_result):
        results_dict[i] = QuerySearchResult(
            distance=r[1],
            id=r[0].content_id,
            text=r[0].content_text,
            title=r[0].content_title,
        )
    return results_dict


async def increment_query_count(
    *,
    asession: AsyncSession,
    contents: dict[int, QuerySearchResult] | None,
    workspace_id: int,
) -> None:
    """Increment the query count for the content.

    Parameters
    ----------
    asession
        The SQLAlchemy async session to use for all database connections.
    contents
        The content to increment the query count for.
    workspace_id
        The ID of the workspace to increment the query count in.
    """

    if contents is None:
        return
    for content in contents.values():
        content_db = await get_content_from_db(
            asession=asession, content_id=content.id, workspace_id=workspace_id
        )
        if content_db:
            content_db.query_count = content_db.query_count + 1
            await asession.merge(content_db)
            await asession.commit()


async def update_votes_in_db(
    *,
    asession: AsyncSession,
    content_id: int,
    vote: str,
    workspace_id: int,
) -> ContentDB | None:
    """Update votes in the database.

    Parameters
    ----------
    asession
        The SQLAlchemy async session to use for all database connections
    content_id
        The ID of the content to vote on.
    vote
        The sentiment of the vote.
    workspace_id
        The ID of the workspace to vote on the content in.

    Returns
    -------
    ContentDB
        The content object if it exists, otherwise `None`.
    """

    content_db = await get_content_from_db(
        asession=asession, content_id=content_id, workspace_id=workspace_id
    )
    if not content_db:
        return None

    match vote:
        case FeedbackSentiment.POSITIVE:
            content_db.positive_votes += 1
        case FeedbackSentiment.NEGATIVE:
            content_db.negative_votes += 1

    content_db = await asession.merge(content_db)
    await asession.commit()
    return content_db


async def get_latest_display_number(
    *, asession: AsyncSession, workspace_id: int
) -> int:
    """Get the latest display number from the database.

    Parameters
    ----------
    asession
        The SQLAlchemy async session to use for all database connections.
    workspace_id
        The ID of the workspace to get the latest display number from.

    Returns
    -------
    int
        The latest display number if it exists, otherwise 0.
    """

    stmt = (
        select(ContentDB.display_number)
        .where(ContentDB.workspace_id == workspace_id)
        .order_by(ContentDB.display_number.desc())
        .limit(1)
    )
    result = await asession.execute(stmt)
    latest_display_number = result.scalar_one_or_none()
    return latest_display_number or 0
