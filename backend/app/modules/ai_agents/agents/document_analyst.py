# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Document Analyst - answers questions strictly from a project's documents.

Tool (declarative - wired into the global registry on import):

* ``search_documents(q, project_id, __agent_context__)`` - proxy over the
  real file-search index (``file_search.service.search_content``), the
  full-text / indexed search over extracted document chunks. Scoped to a
  single project, it returns the top matches as
  ``{document_id, title_or_filename, snippet, score}``.

Data integrity (no-stubs / NEVER-fabricate rule): the tool only ever
returns text the indexer actually extracted from a real uploaded file. It
NEVER invents document content. It also distinguishes two very different
empty states so the LLM can answer honestly:

* **No index / unavailable** - file_search is unreachable, or the project
  has zero indexed files. Returns ``{"error": "unavailable", ...}``.
* **No results for this query** - the project IS indexed but nothing
  matched. Returns ``matches=[]`` with an explicit note so the agent can
  say "not found in the project documents" instead of guessing.

Access control (IDOR defence): the run's invoking user is threaded into the
tool via the trusted ``__agent_context__`` (the runner strips any LLM-forged
context and re-injects the real one). Before reading anything the tool
verifies that user owns or belongs to the target project via
:func:`._access.assert_user_can_access_project`; on denial - or when no user
is in scope - it returns the same ``{"error": "unavailable"}`` shape as a
missing index, so the LLM never reads another tenant's documents and the
project's existence is never leaked.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.modules.ai_agents.agents._access import (
    assert_user_can_access_project,
    coerce_user_id,
)
from app.modules.ai_agents.base import (
    Agent,
    FunctionTool,
    global_tool_registry,
    register_agent,
)

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = (
    "You are a Document Analyst answering questions about a single "
    "construction project. You may ONLY use information returned by the "
    "search_documents tool - the project's uploaded documents. You must not "
    "use outside knowledge to answer project-specific questions. "
    "Call search_documents to retrieve relevant snippets, then answer "
    "strictly from those snippets. For every statement you make, cite the "
    "source document by its title or filename (e.g. 'per Spec-Section-03.pdf'). "
    "If search_documents returns no matches for a query, reply exactly "
    "'not found in the project documents' rather than guessing. If the tool "
    "reports the index is unavailable or empty, tell the user the project "
    "documents could not be searched. Never fabricate document text or "
    "quote a document you were not shown."
)


# ── Tool implementation ──────────────────────────────────────────────────────


async def _tool_search_documents(
    q: str,
    project_id: str | None = None,
    __agent_context__: dict | None = None,  # noqa: N803 - runner-injected key
) -> dict[str, Any]:
    """Full-text search the project's indexed documents.

    Queries the real file-search index via
    ``file_search.service.search_content``. ``project_id`` falls back to the
    runner-supplied ``__agent_context__`` when not passed explicitly.

    Returns the top matches, each ``{document_id, title_or_filename,
    snippet, score}``. Two distinct empty states are reported:

    * ``{"error": "unavailable", ...}`` - file_search is unreachable OR the
      project has no indexed files at all (nothing to search).
    * ``{"matches": [], "note": "no_results", ...}`` - the index exists but
      nothing matched this query.

    NEVER fabricates document text - every snippet comes from the indexer.
    """
    q_clean = (q or "").strip()

    # The trusted invoking user is threaded into __agent_context__ by the
    # runner (the LLM cannot forge it - any model-supplied context is stripped
    # and the real one re-injected). Fail closed: with no user in scope we
    # cannot authorize a cross-tenant read, so report the index as unreadable.
    user_uuid = coerce_user_id(__agent_context__)
    if user_uuid is None:
        return {
            "query": q_clean,
            "matches": [],
            "error": "unavailable",
            "detail": ("No authenticated user in scope - cannot search documents. Do not invent document content."),
        }

    # Resolve the project scope: explicit arg wins, else the trusted
    # runner context. The LLM cannot forge the context (the runner strips
    # any LLM-supplied __agent_context__ and re-injects the real one).
    pid_raw = project_id
    if not pid_raw and isinstance(__agent_context__, dict):
        pid_raw = __agent_context__.get("project_id")

    if not pid_raw:
        return {
            "query": q_clean,
            "matches": [],
            "error": "unavailable",
            "detail": (
                "No project in scope - cannot search documents without a project_id. Do not invent document content."
            ),
        }

    try:
        project_uuid = uuid.UUID(str(pid_raw))
    except (ValueError, TypeError):
        return {
            "query": q_clean,
            "matches": [],
            "error": "unavailable",
            "detail": f"Invalid project_id {pid_raw!r}; cannot scope the search.",
        }

    if not q_clean:
        return {
            "query": q_clean,
            "project_id": str(project_uuid),
            "matches": [],
            "note": "empty query",
        }

    try:
        from sqlalchemy import func, select

        from app.database import async_session_factory
        from app.modules.file_search.models import FileSearchIndex
        from app.modules.file_search.service import search_content

        async with async_session_factory() as session:
            # IDOR guard: the invoking user must own or belong to this project
            # before we read ANYTHING from it. On denial we return the same
            # "unavailable" shape as a missing index so we never leak whether
            # the project exists across tenants.
            if not await assert_user_can_access_project(session, project_uuid, user_uuid):
                return {
                    "query": q_clean,
                    "project_id": str(project_uuid),
                    "matches": [],
                    "error": "unavailable",
                    "detail": (
                        "No access to this project, so its documents could not "
                        "be searched. Do not invent any document content."
                    ),
                }

            # First establish whether the project has ANY indexed content.
            # This is what lets us tell "no index / unavailable" apart from
            # "indexed, but nothing matched this query".
            indexed_count = (
                await session.execute(
                    select(func.count()).select_from(FileSearchIndex).where(FileSearchIndex.project_id == project_uuid)
                )
            ).scalar_one()

            if not indexed_count:
                return {
                    "query": q_clean,
                    "project_id": str(project_uuid),
                    "matches": [],
                    "error": "unavailable",
                    "detail": (
                        "No documents are indexed for this project yet, so "
                        "there is nothing to search. Tell the user the "
                        "project documents could not be searched - do not "
                        "invent any document content."
                    ),
                }

            hits = await search_content(
                session,
                project_uuid,
                q_clean,
                mode="content",
                limit=8,
            )
    except Exception as exc:  # pragma: no cover - DB / module unavailable
        logger.debug("search_documents unavailable: %s", exc)
        return {
            "query": q_clean,
            "project_id": str(project_uuid),
            "matches": [],
            "error": "unavailable",
            "detail": (
                "Document search index is not reachable in this context. "
                "No document text available - do not invent content; report "
                "that the project documents could not be searched."
            ),
        }

    matches = [
        {
            "document_id": hit.file_id,
            "title_or_filename": hit.canonical_name,
            "snippet": hit.snippet,
            "score": round(float(hit.score), 4),
        }
        for hit in hits
    ]

    if not matches:
        return {
            "query": q_clean,
            "project_id": str(project_uuid),
            "matches": [],
            "note": (
                "no_results: the project is indexed but nothing matched this "
                "query. Answer 'not found in the project documents'."
            ),
        }

    return {
        "query": q_clean,
        "project_id": str(project_uuid),
        "matches": matches,
    }


# ── Registration ─────────────────────────────────────────────────────────────


def register_document_analyst() -> None:
    """Idempotent registration of the Document Analyst agent and its tool."""
    global_tool_registry.register(
        FunctionTool(
            name="search_documents",
            description=(
                "Full-text search the current project's uploaded documents. "
                "Returns up to 8 matches, each with document_id, "
                "title_or_filename, snippet and score. Always call this "
                "before answering - never quote a document you were not "
                "shown. matches=[] with note 'no_results' means nothing "
                "matched (answer 'not found in the project documents'); "
                "error='unavailable' means the index is missing or empty."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "q": {
                        "type": "string",
                        "description": "Free-text query over document content",
                    },
                    "project_id": {
                        "type": "string",
                        "description": (
                            "Project UUID to scope the search to. Optional - "
                            "defaults to the project in the run context."
                        ),
                    },
                },
                "required": ["q"],
            },
            func=_tool_search_documents,
        )
    )

    register_agent(
        Agent(
            name="document_analyst",
            display_name="Document Analyst",
            category="documents",
            icon="file-search",
            tagline="Ask questions across a project's uploaded documents",
            description=(
                "Answers questions strictly from the project's uploaded "
                "documents, citing the source document for every statement "
                "and saying so plainly when the answer is not in them."
            ),
            example_prompts=[
                "What does the specification say about concrete cover to reinforcement?",
                "Find every mention of fire-rating requirements in the project documents.",
                "Summarize the scope described in the uploaded tender documents.",
            ],
            system_prompt=SYSTEM_PROMPT,
            max_iterations=8,
            allowed_tools=["search_documents"],
        )
    )
