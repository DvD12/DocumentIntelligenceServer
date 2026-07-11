from typing import Annotated

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import Field

from app.core.errors import DocIntelError
from app.retrieval.service import SearchService
from app.stores.metadata_repo import MetadataRepo

INSTRUCTIONS = (
    "This server exposes a company knowledge base of internal documents "
    "(compliance policies, product manuals, onboarding guides, FAQs). Ground your "
    "answers in retrieved chunks and cite each source as filename plus the pages or "
    "heading found in the result's `location`. Start broad with `search`; narrow with "
    "`search_by_tag` or `search_by_document` when the question clearly targets a topic "
    "or a specific document. Tools never modify the knowledge base."
)

TopK = Annotated[int, Field(ge=1, le=25, description="Number of chunks to return.")]


def build_mcp(
    service: SearchService, repo: MetadataRepo, json_response: bool = False
) -> FastMCP:
    mcp = FastMCP(
        "document-intelligence",
        instructions=INSTRUCTIONS,
        stateless_http=True,
        json_response=json_response,
        # Serves at /mcp (SDK default). The host app mounts this at root, so the
        # externally visible endpoint is POST /mcp without slash-redirects.
        #
        # DNS-rebinding protection is a defense for browser-reachable localhost
        # servers; this endpoint is Bearer-authenticated and served from arbitrary
        # deploy hostnames, where a Host allowlist only causes false rejections.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )

    def guarded(fn, /, *args, **kwargs) -> dict:
        """Convert domain errors into structured guidance the agent can act on."""
        try:
            return fn(*args, **kwargs)
        except DocIntelError as exc:
            return {"error": exc.code, "message": exc.message}

    @mcp.tool()
    def list_documents() -> dict:
        """List every document in the knowledge base with its metadata.

        Use this to discover what documents exist (e.g. before choosing a scoped
        search, or to answer "which documents cover X" by name). Returns id,
        filename, tags, chunk_count and timestamps per document. This is NOT a
        content search — for questions about what documents SAY, use `search`.
        """
        docs = repo.list_documents()
        return {
            "documents": [
                {
                    "id": d.id, "filename": d.filename, "tags": d.tags,
                    "chunk_count": d.chunk_count,
                    "uploaded_at": d.uploaded_at.isoformat(),
                    "updated_at": d.updated_at.isoformat(),
                }
                for d in docs
            ],
            "total": len(docs),
        }

    @mcp.tool()
    def list_tags() -> dict:
        """List all tags in use, with the number of documents carrying each.

        Use this before `search_by_tag` when you are unsure which topic tags
        exist, or to answer "what topic areas does the knowledge base cover".
        Tags are lowercase labels assigned by humans at upload time (e.g.
        'compliance', 'hr', 'onboarding', 'product').
        """
        return {"tags": [{"name": n, "document_count": c} for n, c in repo.list_tags()]}

    @mcp.tool()
    def search(query: str, top_k: TopK = 8) -> dict:
        """Semantic + keyword (hybrid) search across the ENTIRE knowledge base.

        The default search tool: use it when the question does not clearly
        belong to one topic area or one known document. Matches by meaning AND
        by exact terms, so include distinctive identifiers from the user's
        question (codes, acronyms, product names) verbatim in `query`. Returns
        the top_k most relevant chunks with their source document and a
        `location` (pages / heading_path) to cite. If results look off-topic,
        try `list_tags` + `search_by_tag` to narrow the scope.
        """
        return guarded(service.search, query, top_k=top_k)

    @mcp.tool()
    def search_by_tag(
        query: str,
        tags: Annotated[
            list[str], Field(min_length=1, description="Tags to restrict the search to.")
        ],
        tag_match: Annotated[
            str,
            Field(
                pattern="^(any|all)$",
                description="'any' = documents with at least one tag; 'all' = every tag.",
            ),
        ] = "any",
        top_k: TopK = 8,
    ) -> dict:
        """Hybrid search restricted to documents carrying the given tags.

        Use when the question clearly belongs to a topic area (e.g. compliance
        rules, HR policy, product behavior) — scoping by tag removes noise from
        unrelated departments. Call `list_tags` first if unsure which tags
        exist; unknown tags return an error listing valid ones. For questions
        with no obvious topic, prefer `search`.
        """
        return guarded(service.search, query, top_k=top_k, tags=tags, tag_match=tag_match)

    @mcp.tool()
    def search_by_document(
        query: str,
        documents: Annotated[
            list[str],
            Field(min_length=1, description="Document ids or exact filenames."),
        ],
        top_k: TopK = 8,
    ) -> dict:
        """Hybrid search restricted to specific documents (by id or filename).

        Use when the user names a document ("what does the AML policy say
        about...") or when a previous result identified the right document and
        you want to dig deeper into it. Accepts document ids (preferred, from
        earlier results) or exact filenames; unknown references return an error
        with the closest existing filenames.
        """
        return guarded(service.search, query, top_k=top_k, documents=documents)

    @mcp.tool()
    def get_document_outline(
        document: Annotated[str, Field(description="Document id or exact filename.")],
    ) -> dict:
        """Return one document's structure: headings, page ranges, chunk counts.

        Use to answer "what does document X cover" without a content search, or
        to decide whether `search_by_document` is worthwhile and how to phrase
        it (echoing a heading's wording into the query improves matching).
        Returns no chunk text — only structure.
        """
        return guarded(service.outline, document)

    @mcp.tool()
    def expand_chunk(
        document_id: Annotated[
            str, Field(description="`document.id` from a search result.")
        ],
        chunk_index: Annotated[
            int, Field(ge=0, description="`location.chunk_index` from a search result.")
        ],
        before: Annotated[int, Field(ge=0, le=3, description="Chunks before (max 3).")] = 1,
        after: Annotated[int, Field(ge=0, le=3, description="Chunks after (max 3).")] = 1,
    ) -> dict:
        """Fetch the chunks surrounding a search hit, in document order.

        Use when a search result clearly contains the answer but is cut off or
        references nearby context ("the limits above", a continuing table or
        list). Take `document_id` and `chunk_index` directly from that result.
        Bounded on purpose — for broader digging, use `search_by_document`.
        """
        return guarded(service.expand, document_id, chunk_index, before=before, after=after)

    return mcp
