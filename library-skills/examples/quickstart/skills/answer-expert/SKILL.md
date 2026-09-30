---
name: answer-expert
description: >
  Use when answering factual or knowledge questions. Call
  `activate_skill("answer-expert")` first and follow the loaded
  instructions; the catalog text is when-to-use only, not the layout.
tags: [formatting, qa, expert]
---
# Answer Expert

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
