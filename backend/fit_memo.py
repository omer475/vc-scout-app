"""Reads a pitch deck and judges it against the firm's own knowledge base,
producing a one-page "fit memo" grounded in the firm's past decisions.

Uses Claude (strong at cited, judgment-heavy writing). The firm's knowledge
base is sent as a cached system block so repeated analyses are cheap.
"""

import io
import json
import os

# Default to a strong, cost-reasonable model; override with ANTHROPIC_MODEL.
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

DOC_TYPE_LABELS = {
    "thesis": "Investment thesis",
    "memo": "Past investment memo",
    "pass_reason": "Reason for passing on a deal",
    "portfolio": "Portfolio company",
    "other": "Firm document",
}


# ── Text extraction from uploaded files ──

def extract_text(filename: str, raw: bytes) -> str:
    """Pull plain text out of a PDF, Word doc, or text file."""
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        return _extract_pdf(raw)
    if name.endswith(".docx"):
        return _extract_docx(raw)
    # txt, md, csv, anything else → decode as text
    try:
        return raw.decode("utf-8", errors="ignore")
    except Exception:
        return raw.decode("latin-1", errors="ignore")


def _extract_pdf(raw: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        raise RuntimeError("pypdf not installed — run: pip install pypdf")
    reader = PdfReader(io.BytesIO(raw))
    parts = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n".join(parts).strip()


def _extract_docx(raw: bytes) -> str:
    try:
        import docx
    except ImportError:
        raise RuntimeError("python-docx not installed — run: pip install python-docx")
    document = docx.Document(io.BytesIO(raw))
    return "\n".join(p.text for p in document.paragraphs).strip()


# ── Prompt building ──

SYSTEM_GUIDANCE = """You are an analyst at a venture capital firm. Your job is to judge a new pitch \
deck against THIS firm's specific strategy, taste, and track record — not against generic VC wisdom.

You will be given the firm's knowledge base: its investment thesis, past investment memos, reasons it \
has passed on deals, and its current portfolio. Treat these as the ground truth for what this firm \
likes, avoids, and has already seen.

When you assess a new deck:
- Compare it to the firm's stated thesis and to specific past decisions.
- When you make a claim about fit, cite the firm's own history (e.g. "the firm passed on a similar \
B2B marketplace because of thin margins"; "matches the firm's thesis on vertical SaaS").
- Be honest and specific. A useful memo names concrete reasons, not platitudes.
- Flag conflicts: e.g. the company competes with a portfolio company, or contradicts the thesis.
- If the knowledge base is thin, say so and lower your confidence rather than inventing history."""


def build_knowledge_base(docs) -> str:
    """Render the firm's docs into a single text block for the system prompt."""
    if not docs:
        return "(The firm has not uploaded any knowledge yet. You have no past decisions to cite.)"
    chunks = []
    for d in docs:
        label = DOC_TYPE_LABELS.get(d.doc_type, "Firm document")
        chunks.append(f"### {label}: {d.title}\n{d.content}")
    return "\n\n---\n\n".join(chunks)


FIT_MEMO_TOOL = {
    "name": "submit_fit_memo",
    "description": "Return the structured fit assessment of the pitch deck against the firm's knowledge base.",
    "input_schema": {
        "type": "object",
        "properties": {
            "company_name": {"type": "string", "description": "The startup's name, from the deck."},
            "one_liner": {"type": "string", "description": "One sentence on what the company does."},
            "verdict": {
                "type": "string",
                "enum": ["strong_fit", "possible_fit", "weak_fit", "pass"],
                "description": "Overall fit with THIS firm's strategy.",
            },
            "fit_score": {
                "type": "integer",
                "description": "0-100 score for how well this fits the firm's thesis and taste.",
            },
            "memo_markdown": {
                "type": "string",
                "description": (
                    "A one-page memo in markdown. Include sections: a short summary, "
                    "**Why it fits** / **Why it might not**, **What the firm's history says** "
                    "(citing specific past memos / pass reasons / portfolio overlap), "
                    "**Open questions for the founder**, and a final recommendation."
                ),
            },
        },
        "required": ["company_name", "verdict", "fit_score", "memo_markdown"],
    },
}


def generate_fit_memo(deck_text: str, docs) -> dict:
    """Call Claude to produce a structured fit memo. Returns the tool input dict.

    Raises RuntimeError with a friendly message on missing key / SDK / API errors.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "No ANTHROPIC_API_KEY set. Add it to backend/.env (local) or the "
            "backend's environment variables (deployed) to enable deck analysis."
        )
    if not deck_text or not deck_text.strip():
        raise RuntimeError("Could not read any text from the deck. Is it a text-based PDF (not scanned images)?")

    try:
        from anthropic import Anthropic
    except ImportError:
        raise RuntimeError("anthropic SDK not installed — run: pip install anthropic")

    knowledge_base = build_knowledge_base(docs)
    client = Anthropic(api_key=api_key)

    try:
        resp = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=4000,
            system=[
                {"type": "text", "text": SYSTEM_GUIDANCE},
                {
                    "type": "text",
                    "text": "FIRM KNOWLEDGE BASE:\n\n" + knowledge_base,
                    # Stable across deck analyses for this firm → cache it.
                    "cache_control": {"type": "ephemeral"},
                },
            ],
            tools=[FIT_MEMO_TOOL],
            tool_choice={"type": "tool", "name": "submit_fit_memo"},
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Here is a new pitch deck. Assess its fit with this firm and call "
                        "submit_fit_memo with your analysis.\n\nPITCH DECK:\n\n" + deck_text[:120_000]
                    ),
                }
            ],
        )
    except Exception as e:
        raise RuntimeError(f"Claude API error: {e}")

    for block in resp.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "submit_fit_memo":
            return dict(block.input)

    # Fallback: model returned text instead of a tool call.
    text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text")
    try:
        return json.loads(text)
    except Exception:
        raise RuntimeError("Claude did not return a structured memo. Try again.")
