---
name: answer-expert
description: >
  Use when answering factual science questions that require a direct answer,
  supporting evidence, unit conversions, and an explicit confidence statement.
tags: [science, factual-answers, verification]
---
# Answer Expert

## Procedure

1. Load the relevant file from `references/` before answering.
2. Use `run_skill_script` when the question asks for a conversion supported by
   a script in this skill.
3. Start with a one-sentence direct answer.
4. Follow with the source value, assumptions, and conversions.
5. End with `Confidence: HIGH`, `MEDIUM`, or `LOW` and one short reason.

## Available material

- `references/physical-constants.md` contains the source value and conditions
  for the speed of light.
- `scripts/convert_speed.py` converts metres per second to kilometres and miles
  per second. Pass the numeric metres-per-second value as its only argument.

Do not estimate a value when a reference or script supplies it. State clearly
when a fact applies only under particular physical conditions.