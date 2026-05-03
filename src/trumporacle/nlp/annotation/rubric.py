"""Rubric text and version for LLM labeler (spec sections 4 and 9.4).

v1.2 (2026-05-03) — third iteration after the manual audit cycle.
Combines v1.1's markers for levels 4-5 with a v1.0-style coverage of
level 3 that v1.1 had eroded. Switches the prompt from a free-form
description to an explicit top-down decision procedure.

History:
- v1.0 (initial): minimal levels + rules. Audit κ=0.198, MAE=0.500,
  bias=-0.50. Systematically sub-classed (level 4 missed 5/6; level 5
  missed 4/30 LLM-3 items).
- v1.1: added level-4/5 markers + few-shot + anti-default warning.
  κ=0.258 (better) but MAE=0.763 (much worse). 5 items at level 3
  regressed to 0 or 1 because the model became too literal about
  dehumanization markers and missed soft delegitimation language
  ("not truthful", "treacherous", "casts doubt", "sordid").
- v1.2 (current): keeps v1.1's level-4/5 markers, adds explicit
  procedural ladder, broadens level-3 markers to include credibility
  attacks beyond "rigged/corrupt", keeps the single-output guard.
"""

RUBRIC_VERSION = "llm_v1.2"

RUBRIC_BODY = """
You annotate PUBLIC political text on an ordinal valence scale 0-6.

Levels:
0 Neutral/factual — announcements, protocol, factual reporting without
  evaluative framing.
1 Normal political criticism — substantive disagreement on policy or
  outcomes, expressed without attacking the opponent's character or
  legitimacy.
2 Ridicule — nicknames, mockery, belittling without grave accusation
  ("Sleepy Joe", "low-energy", "buffoon").
3 Delegitimation — ANY framing that attacks the target's credibility,
  sincerity, integrity, competence, or institutional trustworthiness.
  This is broader than "rigged/corrupt": it includes "not truthful",
  "treacherous", "casts doubt on", "sordid", "RINO", "fake news",
  "withheld evidence", "bought and paid for", "sleazebag", "thug",
  "lied", "cover-up", framing through guilt-by-association ("funded by
  pro-CCP billionaire"), or framing institutional inaction as bad faith
  ("government's unwillingness to stop the cartel").
4 Dehumanization / designated enemy — frames target as a STRUCTURAL
  ENEMY of the polity OR as a sub-human / pathological category.
  Decisive test: could the language be substituted by "person/citizen"
  without loss of meaning? If no, it's level 4.
  Markers: "vermin", "animals", "parasites", "infestation", "enemy of
  the people", "communist takeover", "danger to our Country",
  "destroying America", criminal-ethnic framing ("meth engineers",
  "illegal aliens" + crime), "they are not human".
5 Veiled punishment / threat — frames consequences as future
  inevitability for the target, without naming a specific coercive
  action. Includes institutional sanctions framed as escalating
  retribution.
  Markers: "they will pay", "their day of reckoning is coming", "we
  won't have a Country [if X]", "should be fired/forced/examined" when
  paired with delegitimation, "their time will come", "consequences
  they cannot imagine".
6 Direct action / explicit threat — names a coercive or violent action
  explicitly, OR quotes a third party doing so verbatim.
  Markers: "lock them up", "kill", "hang", "march on", "by any means
  necessary", explicit calls to incarcerate / mobilize / harm.

Decision procedure (apply IN ORDER, stop at the first match):

  Q1. Does the post NAME a coercive/violent action (against the target,
      their property, their position) — either as a direct call or as a
      verbatim quote of a third party doing so?
        YES → level 6.
  Q2. Does the post frame future negative consequences for the target
      ("they will pay", "should be fired", "won't have a Country" as a
      conditional threat, "their time will come")?
        YES → level 5.
  Q3. Does the post use language that frames the target as a structural
      enemy of the polity OR as a sub-human / pathological category?
        YES → level 4.
  Q4. Does the post attack the target's credibility, sincerity,
      integrity, competence, or institutional trustworthiness — through
      ANY framing, not only the literal "rigged/corrupt"?
        YES → level 3.
  Q5. Does the post mock, ridicule, or belittle the target with
      nicknames or contemptuous adjectives, without grave accusation?
        YES → level 2.
  Q6. Does the post express substantive political disagreement on
      policy or outcomes, without character attack?
        YES → level 1.
  Q7. Otherwise → level 0.

Critical rules:
- The post level is the SINGLE level resulting from the procedure above.
  Apply Q1 first, then Q2, etc. The first YES wins. This is equivalent
  to "post level = MAX level present", written as a ladder.
- Rate the CONTENT, not the author's reputation or apparent intent.
- Ignore whether claims are factually true or false.
- Sarcasm/irony: annotate the apparent literal level of the threat or
  attack (a sarcastic "lock him up" still scores 6).
- Quotation: if the post quotes a third party using strong language,
  annotate at the level of the QUOTED CONTENT — the post carries that
  content into circulation regardless of the author's framing.
- Tie between two levels: pick the HIGHER one.

Output exactly ONE annotation for the post as a whole, even if multiple
targets are present. If multiple targets are present, the annotation
applies to the SINGLE target corresponding to the level returned by the
procedure. Do not emit more than one annotation.

Few-shot examples (real corpus):

EX1 (level 0): "Following the revelation of pictures and sordid details
of former NFL reporter Diana Russini's longtime affair... another story
emerged."
→ Q1-Q2 no. Q3 no. Q4: "sordid details" + "casts doubt on her hero
story" attacks credibility → YES, level 3.
(Note: this is a level-3 example despite looking like news. The framing
is the signal.)

EX2 (level 1): "I disagree with the Fed's rate decision; this policy
will hurt small businesses."
→ Q1-Q4 no (no character attack, no enemy framing). Q5 no (no mockery).
Q6 yes → level 1.

EX3 (level 2): "Sleepy Joe is at it again with his low-energy speeches."
→ Q1-Q3 no. Q4: nicknames don't attack integrity per se → no. Q5 yes
(nicknames + belittling without accusation) → level 2.

EX4 (level 3): "Virginia Gov. Abigail Spanberger is not a centrist and
was not truthful about plans on redistricting."
→ Q1-Q3 no. Q4: "not truthful" attacks sincerity/credibility → YES,
level 3.

EX5 (level 3): "Two leftist groups that received funding from a
pro-Chinese Communist Party tech-billionaire reportedly helped organize
protesters."
→ Q1-Q3 no. Q4: guilt-by-association framing through hostile-actor
funding link attacks the groups' legitimacy → YES, level 3.

EX6 (level 4): "Low IQ Democrat Minority Leader, Hakeem Jeffries, is
nothing but a THUG, and he is a danger to our Country!"
→ Q1-Q2 no. Q3: "danger to our Country" frames as structural threat to
polity → YES, level 4.

EX7 (level 4): "China doesn't need missiles to attack the United
States. They're already using hackers, spies, and meth engineers."
→ Q1-Q2 no. Q3: "meth engineers" applies a sub-criminal category to a
foreign actor → YES, level 4.

EX8 (level 5): "America's Elections are Rigged. We are either going to
fix them, or we won't have a Country!"
→ Q1 no. Q2: "won't have a Country" frames future inevitability of
catastrophic consequence as conditional threat → YES, level 5.

EX9 (level 6): '"86" is a mob term for "kill him." They say 86 him! 86
47 means "kill President Trump."'
→ Q1: post quotes "kill" verbatim → YES, level 6 (regardless of
author's framing as denunciation; quotation rule applies).

Output JSON only with: level, target_type, target_name, rationale, confidence.
"""


def build_user_prompt(text: str) -> str:
    """User message with post text."""

    return f"Annotate the following text:\n\n{text}\n"
