---
name: advisor
description: Consult a fresh instance of the Fable model for a second opinion when a session is genuinely stuck -- a repeated test failure with no clear cause, a design choice with real tradeoffs, or a judgment call worth checking before committing to it. Use when you notice you are guessing, about to retry the same fix a third time, or about to make a call that would be expensive to get wrong. Not for routine work: most judgment calls are yours to make and record, per docs/claude/working.md.
---

Ben's standing instruction: "use /advisor if needed." It exists because a
second, differently-trained model catches a blind spot a single session can
talk itself past, not because this session's own judgment is untrusted.

## When to reach for it

- The same fix has failed twice and a third attempt would just be a guess.
- A real architectural or design fork with more than one defensible answer,
  and no `[BEN: ...]` fact would resolve it (a fact only Ben has still goes to
  him, never to Fable).
- A finding that looks like a repo defect but the diagnosis feels shaky
  (`.claude/rules/slate-operation.md` § Verify before reporting a defect
  still applies first: grep before asking).
- Before a large, hard-to-reverse construction or refactor choice, when a
  second read of the same evidence would change what you'd write.

Not for: routine judgment calls (decide and record why, per
`docs/claude/working.md`), anything a boundary in `CLAUDE.md` already
settles, or a fact only Ben has (that is a `[BEN: ...]` flag, never a
question to another model).

## How to consult it

Spawn a single `Agent` call with `model: "fable"` (`subagent_type: "claude"`
is fine; the model override is what matters). Give it:

- the concrete blocker, stated plainly (not "help me," the actual question);
- what has already been tried and ruled out, so it does not re-suggest it;
- the exact file paths and line numbers it needs, since it starts with no
  context of this conversation;
- what shape of answer you need back (a yes/no with reasoning, a ranked list
  of options, a spotted bug).

Ask it for a candid, adversarial read, not agreement. If your own draft or
diagnosis is included, tell it so and ask it to argue the other side first.

## After it answers

Fable's answer is a second opinion, not a ruling. Read it, weigh it against
the repo's own evidence, and decide yourself, exactly as any other judgment
call: say which way you went and why. It never substitutes for a fact only
Ben has, never weakens an evidence gate or permanent boundary in `CLAUDE.md`,
and its own output is never itself evidence for a run (the same rule that
already applies to any MCP or subagent output). If it disagrees with you and
you still think you're right, say so and proceed -- getting a second opinion
does not obligate you to take it.
