# P9: the judgment layer, built into the engine (R37)

Brief for chunk `P9`. Status, dependencies and hand-back are tracked in
`docs/ROADMAP.md` (status board, and the cards for Sessions 60, 61 and 62);
this file is the strategy. How to build it is the implementing session's call.
Written 2026-10-04 from the Week 4 Classic slate (`changelog.md`, 2026-10-04)
and Ben's R37, said during that slate with the clock running. Ben's aim: "make
sure it can be incorporated into the engine and I don't need to steer so much."

## What happened on Week 4

The engine delivered a legal portfolio. Ben had to step in three times before
lock, and each time the next build was better:

1. **The C1 file was legal but too concentrated:** 5 quarterbacks, and 13
   people in 15 of 39 rows. The slate rules already send that to the thesis
   builder (`.claude/rules/slate-operation.md`), and it worked: 16
   quarterbacks, max exposure 13/39.
2. **"Don't blindly exclude, don't blindly roster."** The judgment pass found
   every starting quarterback scored. It also found four starters whose prior
   still described their old role. Braelon Allen (Breece Hall `OUT`) scored
   3.58. Zach Ertz (Goedert `OUT`) scored 0.55. Jauan Jennings (Justin
   Jefferson `OUT`, a transfer) scored 0.29. Emanuel Wilson (Price on IR,
   Charbonnet `OUT`) scored 3.04. None of them was excluded; the engine priced
   them as backups. The validated tools could not place them, because
   `value-add` and `redeploy` rank by that same prior. They went in by a
   recorded hand swap.
3. **"Redeploy excess salary only as a Pareto gain."** My first redeploy
   raised prior points but made the portfolio more concentrated: mean overlap
   1.13 to 1.15, distinct people 115 to 112. I rejected it. The rule I shipped
   took a swap only when the incoming person was used at least 2 fewer times
   than the person leaving. Prior sum went 4148.5 to 4189.8, distinct people
   115 to 120, mean overlap 1.13 to 1.07, top-3 union 29 to 28, and max
   exposure stayed 13.

Each of those three steps should run without Ben asking.

## The two goals, and how every construction step answers to them

Ben's goals (R34): maximize the probability of winning a large prize within
each contest, and minimize the probability of a washout across the portfolio.
For this brief, a change is an **improvement** only when it is a Pareto gain
on both goals. With the proxies the engine has today:

- **Large-prize proxy, per lineup:** the row's gated prior points. It is a
  prior and never EV; the no-EV rule is unchanged. Every lineup also keeps a
  game script: QB, a pass catcher from his team, and a bring-back.
- **Washout proxy, portfolio:** max person exposure, top-3 union coverage,
  mean pairwise overlap and distinct people. Leverage stays unmeasured until
  there is an ownership input, and the handoff says so.

A move that raises one goal and lowers the other is a trade, not an
improvement. The engine reports it and never takes it on its own.

## The three parts

### 1. The injury room moves the workload (Session 60)

When a person DraftKings marks `OUT` or `IR` held a material prior share, the
share he vacates goes to his position room. That is the reading
`participation.redistribute_opportunity` already implements and documents as
its default. Its docstring measures it on Charbonnet and Emanuel Wilson. But
`prior_review.py:2364` and `cli.py:1932` call it with `redistribute=False`, so
Classic and Showdown scoring keep every survivor at his backup share. A grep of
the roadmap, changelog, archives and git log found no ruling behind
`False`. The implementing session checks that first and stops for Ben if one
exists.

The redistribution is deterministic, local and versioned, and it is reported
person by person (vacated share, absorbed share, from whom). It writes no
number from prose. It is the model's own rule applied to DraftKings bytes the
run already binds. The status that triggers it is a DraftKings status, not
official activity evidence. That is no different from today, where the same
status already takes the person out.

### 2. The judgment pass runs inside the run (Session 61)

`docs/claude/working.md` § Classic judgment pass is the manual procedure.
The engine should do the parts that need no judgment and hand over the rest
as a short list:

- **Starters check.** Every depth-chart starting quarterback, including the
  promoted backup of a DraftKings-`OUT` starter, is in the scored pool. If one
  is not, the run names him.
- **Injury-room report.** For each `OUT` or `IR` starter: who inherits, that
  person's prior before and after Session 60, and his salary.
- **Underpriced-role candidates.** People whose role changed today but whose
  prior still describes the old one, ranked for the agent to research. Sources:
  depth rank 1 at his position with a low prior, the main absorber in the
  injury-room report, a transfer whose new-team role is larger. This is a list
  for the agent's research, never a selection.
- **A Classic construction judgment input.** This is Session 52's
  `nfl_construction_judgment_v1`, given a Classic schema version and widened
  past role-gate exclusions to these candidates. It names a person by exact
  DraftKings ID, a row minimum, a reason and sources, writes no number, and
  goes into the thesis build as a protected placement. Pareto redeploy
  (part 3) never removes a protected person. It never overrides a DraftKings
  `OUT`, an official inactive, a `BLOCK`, or an unresolved material role
  change, and a P-class limitation travels with the file.
- **Backup quarterbacks leave the thesis pool** before construction, except a
  promoted backup. Week 4's first build rostered Nick Mullens, who was not on
  his team's depth chart.

### 3. Salary is redeployed only as a Pareto gain (Session 62)

Ben (R37): leaving salary unused is fine and can be strategic. The goal is
not to spend the cap; it is to find out whether unused salary can buy a gain on
both goals at once. So:

- **Unused salary is never a defect.** No QA line, limit or default treats it
  as one, and no step chases a salary floor.
- **A redeploy swap is accepted only when all of these hold:**
  - it raises the row's prior;
  - it fits the cap;
  - it keeps the row legal and distinct;
  - it leaves the QB, his stack, the bring-back, the DST and every protected
    person alone;
  - after it, no washout proxy is worse than before: max exposure, top-3 union
    and mean pairwise overlap no higher, distinct people no fewer.

  A sufficient local rule is that the incoming person was used at least 2 fewer
  times than the person leaving. Week 4 used exactly that rule
  (`data/inbox/slates/wk4-classic-2026-10-04/construction/pareto_redeploy_record.py`).
  The engine checks the portfolio-level proxies after each swap anyway.
- **The report shows both goals before and after.** It lists every rejected
  candidate swap with the goal it would have hurt. A swap rejected for
  concentration is information, not a failure.

## Late games

Ben (R37): a late game with no active list at the early lock is fine,
because late swap covers it. Missing official activity for people in a later
window is not a gap to chase before the early lock, and not a reason to keep
them out of the portfolio. The handoff lists them as the **late-swap watch
list**, with each one's Friday status, and the run reports them that way
rather than as an open blocker. The certification rule is unchanged:
`OFFICIAL_STATUS_*` still stops certification. Late swap
(`swap_inactives.py --mode late-swap`, governed `late-swap`) re-checks those
people once their window's inactives post.

## What this does not do

- It writes no model value from research, and calls nothing EV, ROI, win
  probability or calibrated.
- It relaxes no evidence gate, overrides no DraftKings `OUT` or official
  inactive, and never repeats a lineup (R29).
- It does not choose for Ben between two goals that disagree. When no Pareto
  gain exists, the portfolio stays as it is and the report says so.

## Acceptance across the chunk

On the Week 4 frozen inputs (committed under
`data/inbox/slates/wk4-classic-2026-10-04/`), with no hand steps, `run-slate`
must:

- score Braelon Allen, Emanuel Wilson and Zach Ertz above their Week 4 priors
  (Session 60);
- name every starting quarterback scored, and list Allen, Ertz, Jennings and
  Wilson as candidates (Session 61);
- never roster a backup quarterback whose starter is active;
- produce a redeploy whose washout proxies are each no worse than before it
  (Session 62).
