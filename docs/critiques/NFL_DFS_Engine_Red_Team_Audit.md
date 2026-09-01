# Quantitative & Adversarial Audit: Greenfield NFL DFS Optimization Engine

---

## 1\. Executive Synthesis (The Architecture in Plain English)

The proposed architecture outlines a fully local, free-and-open-source (FOSS) DraftKings NFL Daily Fantasy Sports (DFS) platform targeting Classic and Showdown (Captain Mode) contests.

                                PROPOSED PIPELINE



  \[FOSS Data Sources\]        \[Deterministic Modeling\]        \[Joint Simulation\]

  • nflverse / nflreadpy  ─► • Team/Game Environment      ─► • 2k-5k "DESIGN"

  • NWS API (Weather)        • Positional Opportunities      • 10k-25k "SELECT"

  • Public Vegas Lines       • Role-Delta Reallocation       • 10k-25k "REFEREE"

  • Official Inactives                                                │

                                                                      ▼

  \[Output & Upload\]            \[Contest Selection\]          \[Candidate Generation\]

  • Independent Certifier ◄─ • Pareto Front Optimization ◄─ • MILP Lineup Solves

  • Byte-Verified CSV        • Upside vs. Non-Washout        • Stacks & Correlations

  • Excel Review Sync        • Opponent Field Mixture        • Duplication Pruning

### Execution Pipeline Mechanics

1. **Intake & Identity:** Ingests official DraftKings salary/entry CSVs, reconciling player identities with `nflverse`/GSIS data dictionaries.
2. **Deterministic Opportunity Modeling:** Converts team environments, Vegas lines, pace, and situation-adjusted opportunity metrics into baseline distribution parameters.
3. **Joint Game & Slate Simulation:** Executes bottom-up Monte Carlo simulations (possessions, plays, targets, touchdowns, and defensive events) across three isolated scenario banks (`DESIGN`, `SELECT`, `REFEREE`).
4. **Opponent Field & Ownership Generation:** Models contest-specific field distributions and ownership priors via a cold-start partial-pooling mixture model.
5. **Candidate & Portfolio Selection:** Solves thousands of MILP lineup candidates from scenario draws, then selects 1 to 150 entries along a balanced Pareto frontier optimizing **Top-1% Upside** versus **Non-Washout (Break-Even)** probability.
6. **QA, Certification & Late Swap:** Runs a 3-pass adversarial review, executes independent byte-level CSV certification for manual DraftKings upload, handles conditional late swaps, and performs post-slate learning with automated rollback.

---

## 2\. Fatal Blockers & Critical Flaws (Must Fix Before Any Code Is Written)

┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐

│                                       CRITICAL FAILURE POINTS                                          │

├───────────────────────────────┬───────────────────────────────────┬────────────────────────────────────┤

│ Mathematical & Game-Theoretic │ Infrastructure & Timing           │ Data Pipeline & Operating System   │

├───────────────────────────────┼───────────────────────────────────┼────────────────────────────────────┤

│ • Anti-correlated dual-       │ • 90-minute inactives compute     │ • Windows Excel file-locking       │

│   objective Pareto frontier   │   bottleneck (10k-25k Python sims)│   (PermissionError crashes)        │

│ • Uncalibrated cold-start     │ • Late news cascade failure       │ • Missing real-time route / snap   │

│   ownership false leverage    │ • Duplicated payout dilution math │   charting in free FOSS feeds      │

└───────────────────────────────┴───────────────────────────────────┴────────────────────────────────────┘

### Flaw 1: The "Non-Washout" Pareto Compromise Destroys GPP Expected Value

* **The Error:** The engine optimizes portfolio selection along a Pareto frontier balancing **Upside** ($P(\\text{Top 1% finish})$) against **Non-Washout** ($P(\\text{Gross Payout} \\ge \\text{Total Entry Fees})$) using a normalized Nash product.
* **Mathematical Reality:** In top-heavy DraftKings GPPs (where 1st place receives 20–25% of the total prize pool and min-cashes yield a meager $1.5\\times$ to $2\\times$ return), optimizing for "Break-Even Defense" is **diametrically opposed** to maximizing long-term Tournament Expected Value ($+EV$).
* **The Consequence:** To artificially inflate $P(\\text{Gross Payout} \\ge \\text{Fees})$, the optimizer will force high-floor, high-median chalk plays (e.g., high-volume pass-catching RBs on favorites) into lineups at the expense of asymmetric, high-variance tournament leverage. Min-cashing in GPPs is a slow-bleed strategy because the contest rake (15–16%) mathematically penalizes flat payout outcomes.
* **The Mandate:** Eliminate the Nash-product Non-Washout objective for GPPs. The selection objective must directly maximize **Portfolio Simulated Prize Equity:** $$\\max \\sum\_{i=1}^{N\_{\\text{scenarios}}} \\text{Payout}\\left(\\text{Rank}(\\text{Lineup}, \\text{Field}\_i)\\right) \- \\text{RakePenalty}$$ Reserve capital preservation objectives strictly for 50/50, Double-Up, and H2H slates.

---

### Flaw 2: Cold-Start Ownership Estimation Creates Disastrous "False Leverage"

* **The Error:** The architecture rejects commercial data feeds and relies on an internal cold-start partial-pooling model (salary, rank, projection, Vegas, archetype) to generate slate ownership and 10,000+ opponent lineups.
* **Mathematical Reality:** DFS ownership is highly non-linear, driven by industry herd mentality, content touts, and late-breaking value. If a starting RB is ruled out 60 minutes before lock and his backup is minimum salary ($4,000):
  - **Actual High-Stakes Field Ownership:** $55% \- 75%$
  - **Unanchored Statistical Cold-Start Estimate:** $20% \- 30%$
* **The Consequence:** The game simulator will evaluate the backup as having massive positive leverage ($40%$ projection-to-ownership delta) when in reality the player is hyper-chalk. Conversely, the engine will create "contrarian" leverage against players who are already low-owned, loading the portfolio with sub-optimal, negative-EV assets.
* **The Mandate:**
  1. Structure ownership priors around **Implied Value & Chalk Heuristics** (e.g., Points-per-Dollar relative to positional baseline \+ Team Implied Total).
  2. Implement an **Operator-Overridable Ownership Bracket** directly in the workbook.
  3. Subject all candidate selection to **Ownership Uncertainty Stress-Testing** ($\\pm 15%$ perturbation sweeps across top-10 owned players).

---

### Flaw 3: Bottom-Up Play-by-Play Generative Simulation Bottleneck at $T-90$ Minutes

* **The Error:** The system attempts to draw 10,000–25,000 complete bottom-up game scripts (drive count, play-by-play, latent states, pass/run allocation, yardage, defensive events) locally in Python within the pre-lock window.
* **Computational Reality:** In a 12-game Classic slate, modeling 24 teams, 600+ active players, and individual drive states across 25,000 iterations in pure Python/NumPy/Polars will exceed 30–45 minutes of CPU compute time.
* **The Consequence:** Official NFL inactives are released at $T-90$ minutes (11:30 AM EST). A 45-minute simulation cycle leaves zero margin for late news, model reconciliation, candidate solving, QA review, and manual CSV upload before the 1:00 PM EST lock. A surprise 12:40 PM inactive will completely brick the system.
* **The Mandate:** Abandon micro-level drive/play-by-play Markov simulations for live slate execution. Replace with a **Top-Down Hierarchical Gaussian Copula / Correlated Gamma Poisson Model**:
  1. Sample Team Totals and Play Volume from Vegas priors.
  2. Sample Team Touchdowns and Yardage.
  3. Distribute volume to players via Dirichlet distributions parameterized by role-deltas.
  4. Vectorize entirely in NumPy/C-extensions to complete 25,000 full slate simulations in $\<15\\text{ seconds}$.

---

### Flaw 4: Windows Excel OS File-Locking Crash during Live Execution

* **The Error:** The pipeline relies on an `openpyxl` Python layer writing to a 12-tab Excel workbook (`nfl-dfs.xlsx`) while the operator reviews blockers, evidence, and portfolio candidates.
* **OS-Level Failure:** In Microsoft Windows, opening an `.xlsx` file in Microsoft Excel places an exclusive OS read/write file-lock on the file. Any background Python script attempting to refresh or write to that file will instantly throw a fatal: `PermissionError: [Errno 13] Permission denied: 'nfl-dfs.xlsx'`
* **The Consequence:** The operator will have the workbook open at 12:45 PM to review late inactives, triggering an unhandled Python crash that halts slate certification.
* **The Mandate:** Decouple operator interaction from the core engine:
  1. Python must write to versioned, timestamped workbooks (e.g., `artifacts/review_slate_2026W01_T1245.xlsx`) or export plain CSV/JSON state.
  2. The intake/review parser must only read from a designated, unlinked staging directory.
  3. Include explicit exception handling and CLI prompts alerting the operator if an open file lock is detected.

---

### Flaw 5: FOSS Data Pipeline Lags on Real-Time Routes and Snaps

* **The Error:** The blueprint assumes access to route participation, real-time depth chart promotions, and situational metrics via `nflreadpy`/`nflverse`.
* **Data Reality:** `nflverse` PBP and participation tracking data are batch-processed post-game. During the live season, target charting and snap data are only updated on Tuesday/Wednesday following the games. Furthermore, raw free data does not provide real-time injury practice designations or mid-week first-team rep changes.
* **The Consequence:** The system will model early-season rookie breakouts or role adjustments using stale prior-week proxies, completely missing pre-game practice role changes reported by beat writers.
* **The Mandate:** Formalize the **Proxy Opportunity Model**:
  - For current-slate projections, strictly utilize: $$\\text{Target Share Priors} \\times \\text{Vegas Implied Team Dropbacks} \+ \\text{High-Value Touch Base Rates}$$
  - Forbid the engine from claiming route-run fidelity unless explicitly fed by user-reviewed manual depth chart overrides in the intake workbook.

---

## 3\. Structural Vulnerabilities & Over-Engineering Flags

┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐

│                                    STRUCTURAL VULNERABILITY AUDIT                                      │

├────────────────────────────────┬──────────────────────────────────────┬───────────────────────────────┤

│ Vector                         │ Architectural Vulnerability          │ Severity                      │

├────────────────────────────────┼──────────────────────────────────────┼───────────────────────────────┤

│ Format Nuance (Showdown)       │ Failure to model Duplication Dilution│ HIGH                          │

│ Format Nuance (Classic)        │ Missing Secondary Stacking Rules     │ HIGH                          │

│ Qualitative Layer / LLM        │ Hallucination in Role-Delta Engine   │ CRITICAL                      │

│ Automated Learning             │ Overfitting Weekly Standings Noise   │ MEDIUM                        │

│ Operational Execution          │ Multi-Pass Manual Terminal Commands  │ HIGH                          │

└────────────────────────────────┴──────────────────────────────────────┴───────────────────────────────┘

### 1\. Showdown Format: Ignoring Chopped Payout Dilution

* **Vulnerability:** In DraftKings Showdown contests, up to $30%$ of the field duplicates high-chalk builds (e.g., starting $50,000$ salary constructions with QB Captain). If a lineup ties 500 ways for 1st place in a $200,000 top prize GPP, the realized payout is: $$\\frac{$200,000}{500} \= $400$$
* **Fix:** The Showdown optimizer must include an explicit **Salary Left Penalty & Duplication Estimator**:
  - Enforce a salary cap constraint of $\\le $49,600$ for hyper-chalk game scripts or explicitly calculate **Expected Divided Payout** ($EV / \\text{Simulated Duplicate Count}$).

---

### 2\. Classic Format: Missing Secondary Correlation & DST Game-Script Rules

* **Vulnerability:** The proposal relies on joint game simulations to "naturally" discover stacking shapes. However, stochastic noise in 2,000 `DESIGN` solves will frequently select unstacked QBs, naked WRs, or un-correlated single-game flyers.
* **Fix:** Hard-code structural MILP rules in candidate generation:
  - **QB Primary Stack:** QB \+ $\\ge 1$ Pass Catcher (WR/TE) from same team.
  - **Game Bring-Back:** $\\ge 1$ Pass Catcher/RB from opposing team (in games with Total $\\ge 44.0$).
  - **Negative Correlation Invariant:** Prohibit DST paired with opposing QB/WR1/WR2.
  - **Positive Ground Correlation:** Allow RB \+ DST from same team when team is favored by $\\ge 3.5$.

---

### 3\. Qualitative & LLM Judgment Layer: Hallucination Risk in Role-Deltas

* **Vulnerability:** Allowing an LLM agent to interpret qualitative beat reports and assign numerical "role deltas" to backup players risks massive hallucinations (e.g., confusing a special-teams RB3 with a goal-line RB2).
* **Fix:** Zero-Trust Deterministic Role Handcuffs:
  - All role redistributions must follow strict mathematical conservation: $$\\Delta \\text{Share}*{\\text{Active Backup}} \= \\text{Share}*{\\text{Inactive Starter}} \\times \\text{Depth Chart Factor} \\times \\text{Historical Role Cap}$$
  - No natural-language LLM output may directly alter projection floats without passing strict sanity checks ($\\text{Projection} \\le \\text{Positional Max Threshold}$).

---

### 4\. Over-Engineered Weekly Auto-Learning & Rollback

* **Vulnerability:** Attempting to fit complex machine learning ensembles and automated parameter rollbacks on a week-to-week basis creates extreme risk of overfitting to 1-slate sample noise (e.g., an anomalous defensive TD slate).
* **Fix:** Freeze model weights for the entire 18-week NFL season. Restrict weekly updates strictly to **Empirical Calibration Shifts** (e.g., Brier score calibration on ownership priors and baseline team pace parameters).

---

## 5\. Concrete Remediation Directives

Before writing production code in `C:\Users\benja\Documents\Claude\nfl-dfs`, execute the following step-by-step refactoring of the architecture.

                                REFACTORED ARCHITECTURE



  ┌─────────────────────────┐     ┌─────────────────────────┐     ┌─────────────────────────┐

  │   1\. Fast Simulation    │     │  2\. Direct GPP Equity   │     │  3\. Slate Constraints   │

  │ • Vectorized Copula     │ ──► │ • Simulated Payout Maxim│ ──► │ • Mandatory DK Stacks   │

  │ • 25,000 runs in \<15s   │     │ • Drop Non-Washout Nash │     │ • Showdown Salary Left  │

  └─────────────────────────┘     └─────────────────────────┘     └─────────────────────────┘

               │                                                               │

               ▼                                                               ▼

  ┌─────────────────────────┐                                     ┌─────────────────────────┐

  │  4\. Ownership Stress    │                                     │  5\. 2-Step Launcher     │

  │ • Implied Chalk Ranges  │ ──────────────────────────────────► │ • T-90 Ingest & Auto-Run│

  │ • ±15% Perturbation     │                                     │ • 1-Click Certified CSV │

  └─────────────────────────┘                                     └─────────────────────────┘

### Directive 1: Replace Micro-Sim with Vectorized Top-Down Correlated Engine

\# Mandated Architecture: Vectorized Slate Generator (NumPy / SciPy)

class SlateSimulationEngine:

    def \_\_init\_\_(self, slate\_games, n\_scenarios=25000):

        self.n\_scenarios \= n\_scenarios

        self.slate\_games \= slate\_games

    def run\_fast\_simulation(self):

        \# 1\. Sample correlated Game Totals & Spreads via Cholesky decomposition

        \# 2\. Vectorized Poisson draws for Team TDs and Drive Field Goals

        \# 3\. Dirichlet allocation for Team Target and Carry Distributions

        \# 4\. Generate DK Fantasy Points Matrix: Shape (n\_scenarios, n\_players)

        pass

* **Performance Requirement:** 25,000 scenarios across 12 games executed, scored, and pivoted in $\\le 15.0\\text{ seconds}$.

---

### Directive 2: Redefine GPP Portfolio Selection Objective

Replace the multi-objective Pareto Nash Product with pure **Contest-Specific Simulated ROI**:

$$\\text{Portfolio Score} \= \\frac{1}{S} \\sum\_{s=1}^{S} \\left\[ \\sum\_{k=1}^{K} \\text{Payout}\\Big(\\text{Rank}(\\text{Lineup}*k, \\text{Field}*{s})\\Big) \\right\] \- \\lambda \\cdot \\text{Lineup Overlap Penalty}$$

* Where $S \= 25,000$ scenarios, $K \= \\text{number of portfolio entries}$ (1–150), and $\\lambda$ penalizes duplicate player exposures beyond defined risk thresholds.

---

### Directive 3: Enforce Exact DraftKings Mathematical Rules & Stacking Invariants

┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐

│                                      MANDATORY SOLVER CONSTRAINTS                                      │

├───────────────────────────────────┬────────────────────────────────────────────────────────────────────┤

│ Classic GPP Solves                │ Showdown Captain Solves                                            │

├───────────────────────────────────┼────────────────────────────────────────────────────────────────────┤

│ • Primary Stack: QB \+ ≥1 WR/TE    │ • Salary Ceiling: Max $49,600 spent (leaves ≥$400 for uniqueness)  │

│ • Bring-Back: ≥1 Opponent WR/TE/RB│ • Max 1 Kicker/DST per lineup unless script is low-total (\<38)    │

│ • Forbid DST vs Opposing QB/WR    │ • Exact 1.5x Multiplier for Salary and Scoring on CPT slot         │

│ • Max 3 Offensive Players per team│ • Minimum 1 player from each team                                  │

└───────────────────────────────────┴────────────────────────────────────────────────────────────────────┘

---

### Directive 4: Streamline Operator Experience for Game-Day Execution

Replace the multi-command state machine with a **3-Phase Automated Execution Flow**:

\# 1\. Pre-Slate Setup (Run Tuesday \- Saturday)

.\\run\_slate.ps1 \-Mode Ingest \-Slate Classic\_Main

\# 2\. Game-Day Inactives & Full Optimization (Run at 11:35 AM EST)

.\\run\_slate.ps1 \-Mode Optimize \-Entries "DraftKings\_Entries.csv" \-MaxEntries 150

\# 3\. Output Verification & Direct Upload (Generates Certified Upload File)

\# Output: C:\\Users\\benja\\Documents\\Claude\\nfl-dfs\\upload\\DK\_UPLOAD\_CERTIFIED.csv

---

### Directive 5: Zero-Trust Late-Swap Verification Engine

Ensure the late-swap module guarantees:

1. **Byte-Level Cell Immutability:** Pre-lock games ($1:00\\text{ PM}$) are frozen; roster IDs, positions, and entry assignments cannot be modified by the solver.
2. **Reachable Continuation Solving:** Solve remaining slots exclusively using players from $4:05\\text{ PM}$, $4:25\\text{ PM}$, and $8:20\\text{ PM}$ slates.
3. **Live Contest Conditioning:** Swap decisions must evaluate the live leaderboard distribution to calculate whether to pivot to ultra-leverage or preserve median cash equity.

---

## 6\. Summary Audit Scorecard

| Evaluation Dimension | Proposal Rating | Post-Remediation Status |
| :---- | :---- | :---- |
| **Quantitative Rigor** | **FAIL** (Slow micro-sims, flawed dual-objective) | **PASS** (Vectorized copula, pure GPP equity) |
| **Game Theory & Mechanics** | **FAIL** (Uncalibrated ownership, Showdown dupes) | **PASS** (Salary-left filters, leverage sweeps) |
| **FOSS Feasibility** | **WARNING** (Route charting lag, inactives latency) | **PASS** (Opportunity proxy, strict caching) |
| **Qualitative/LLM Layer** | **WARNING** (Vague QA loops, hallucination risk) | **PASS** (Deterministic assertion checks) |
| **Operational Usability** | **FAIL** (Excel OS locks, complex CLI cadence) | **PASS** (Decoupled CSVs, 1-click execution) |

**Final Verdict:** The conceptual ambition of the proposal is sound, but its current mathematical objectives and simulation architecture will fail under live game-day conditions. Refactoring to a vectorized simulation engine, eliminating the Non-Washout objective, and enforcing deterministic game-script constraints are non-negotiable prerequisites before writing code.
