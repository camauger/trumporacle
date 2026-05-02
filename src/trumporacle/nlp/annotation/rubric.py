"""Rubric text and version for LLM labeler (spec sections 4 and 9.4)."""

RUBRIC_VERSION = "llm_v1.0"

RUBRIC_BODY = """
You annotate PUBLIC political text on an ordinal valence scale 0-6.

Levels:
0 Neutral/factual — announcements, protocol, no significant negative charge.
1 Normal political criticism — disagreement in a democratic frame.
2 Ridicule — nicknames, mockery, rhetorical belittling without grave accusation.
3 Delegitimation — questions legitimacy, sincerity, integrity ("rigged", "corrupt").
4 Dehumanization / designated enemy — structural enemy, subhuman framing.
5 Veiled punishment / threat — consequences implied without direct violence incitement.
6 Direct action / explicit threat — clear incitement to coercive or violent action.

Rules:
- Post level = MAX level present in the post.
- Rate content, not author reputation.
- Ignore whether claims are true/false.
- Sarcasm: annotate apparent semantic level of the threat/attack.
- If torn between two levels, choose the HIGHER level.

Output JSON only with: level, target_type, target_name, rationale, confidence.
"""


def build_user_prompt(text: str) -> str:
    """User message with post text."""

    return f"Annotate the following text:\n\n{text}\n"
