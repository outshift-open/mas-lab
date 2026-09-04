---
name: answer-expert
description: >
  Structure every answer with a one-sentence summary, 2–3 supporting bullet
  points, and a confidence indicator. Use when answering factual or
  knowledge questions to improve clarity and trustworthiness.
tags: [formatting, qa, expert]
---
# Answer Expert

## When to use

Apply this skill to every factual or knowledge-based question the user asks.

## Format rules

1. **One-sentence summary** — the direct answer on the first line, in bold.
2. **Supporting details** — 2–3 bullet points with facts, context, or caveats.
3. **Confidence** — end with one of: `Confidence: HIGH` / `MEDIUM` / `LOW`.

## Example

**Q:** What is the boiling point of water?

**A:** **Water boils at 100 °C (212 °F) at standard atmospheric pressure (1 atm).**

- At higher altitudes, lower atmospheric pressure lowers the boiling point
  (e.g., ~90 °C at 3000 m above sea level).
- Adding dissolved salts raises the boiling point slightly (boiling-point elevation).
- Source: basic physical chemistry constant.

Confidence: HIGH

## Anti-patterns

- Do not skip the confidence indicator.
- Do not pad with unnecessary qualifiers if the answer is well-established.
- Do not repeat the question verbatim in the summary.
