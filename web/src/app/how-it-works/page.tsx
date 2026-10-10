import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft, ArrowRight, Waypoints } from "lucide-react";
import { EvidenceGateFigure, QueryPathsFigure, ResolutionFigure, SourcePipelineFigure } from "./HowItWorksFigures";
import styles from "./page.module.css";

export const metadata: Metadata = {
  title: "How It Works · Institutional Entity Intelligence",
  description: "The technical guide to source ingestion, deterministic entity resolution, typed relationships, agent research and replayable evidence.",
};

const sourceFamilies = [
  ["Legal identity", "GLEIF LEI records, registration history and accounting relationships"],
  ["Regulatory filings", "SEC 13F, 13D/G, Forms 3/4/5, N-PORT, Form ADV and EDGAR submissions"],
  ["Registers and mappings", "Companies House, FFIEC NIC, SEC series and class records, and OpenFIGI"],
] as const;

export default function HowItWorksPage() {
  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <Link href="/" className={styles.brand} aria-label="Entity Intelligence home"><span><Waypoints aria-hidden="true" /></span>Entity intelligence</Link>
        <Link href="/" className={styles.openLink}>Open research <ArrowRight aria-hidden="true" /></Link>
      </header>

      <article className={styles.article}>
        <header className={styles.hero}>
          <Link href="/" className={styles.back}><ArrowLeft aria-hidden="true" /> Back to research</Link>
          <p className={styles.kicker}>How it works · Technical guide</p>
          <h1>From a messy name to a defensible answer.</h1>
          <p className={styles.lede}>Institutional records disagree by default. The same organisation can appear as a legal entity, investment manager, filer, fund series or beneficial owner, with a different name and identifier in every system. This platform connects those records without erasing what each source actually claims.</p>
          <div className={styles.meta}><span>Architecture</span><span>Entity resolution</span><span>Evidence systems</span><span>10 min read</span></div>
        </header>

        <div className={styles.body}>
          <nav className={styles.contents} aria-label="On this page">
            <span>On this page</span>
            <a href="#sources">Sources</a>
            <a href="#resolution">Resolution</a>
            <a href="#graph">Knowledge graph</a>
            <a href="#runtime">Runtime paths</a>
            <a href="#agent">Agent loop</a>
            <a href="#verification">Verification</a>
            <a href="#limits">Limits</a>
          </nav>

          <section className={styles.section} id="sources">
            <p className={styles.sectionLabel}>01 · Sources and storage</p>
            <h2>Each source keeps its own meaning all the way in.</h2>
            <p>There is no universal import script. Every source owns its raw parser, Pydantic validation model, Arrow schema and ingestion pipeline. A malformed row fails at that boundary instead of quietly entering the entity layer.</p>
            <div className={styles.sourceList}>
              {sourceFamilies.map(([title, description]) => <div key={title}><strong>{title}</strong><p>{description}</p></div>)}
            </div>
            <p>Clean records land in Parquet, the build-time system of record. Crosswalk decisions, human reviews, canonical identifiers and graph facts are all reproducible from there. OpenSearch is a serving layer shaped for fast reads, not a second source of truth.</p>
            <SourcePipelineFigure />
            <aside className={styles.note}><strong>The rebuild test</strong><p>If every serving index disappeared, running index and publish again should restore the application without losing a source fact or match decision.</p></aside>
          </section>

          <section className={styles.section} id="resolution">
            <p className={styles.sectionLabel}>02 · Entity resolution</p>
            <h2>Matching is a decision pipeline, not a similarity lookup.</h2>
            <p>A source name first retrieves a small candidate set from millions of legal entities. Retrieval considers full, core and compact name forms. Country is normally a soft signal because real filings often contain stale or incorrect jurisdictions.</p>
            <p>Pure comparison functions then produce named signals: name similarity, address and postcode agreement, jurisdiction, registration identifiers, fund number, and master or feeder conflicts. Configuration-owned weights turn those signals into a score. No learned model hides why a candidate gained or lost points.</p>
            <ResolutionFigure />
            <p>The final decision uses both the top score and the gap to the runner-up. A single strong candidate can become <code>AUTO_MATCH</code>. Two nearly equal candidates become <code>REVIEW</code>. Weak evidence becomes <code>UNMATCHED</code>. Abstaining is a feature: a confident wrong entity is worse than no match.</p>
            <div className={styles.codeMap}>
              <span><code>retrieval/candidates.py</code><small>Build candidate query</small></span>
              <span><code>matching/features.py</code><small>Compute comparison signals</small></span>
              <span><code>matching/scoring.py</code><small>Apply configured weights</small></span>
              <span><code>matching/decisions.py</code><small>Score and gap decision</small></span>
            </div>
          </section>

          <section className={styles.section} id="graph">
            <p className={styles.sectionLabel}>03 · Canonical entities and graph</p>
            <h2>Identity joins records. Typed edges preserve claims.</h2>
            <p>The canonical entity layer gives each resolved institution one internal entity record and attaches every external identifier with its source and confidence. A CIK, LEI, CRD number and company number can point to the same entity without pretending those identifier systems are interchangeable.</p>
            <p>The knowledge graph keeps legal entities, fund series, share classes, securities and people as separate node types. It also keeps every relationship type distinct:</p>
            <dl className={styles.edgeList}>
              <div><dt>Accounting parent</dt><dd>GLEIF consolidation relationship</dd></div>
              <div><dt>Bank control</dt><dd>FFIEC NIC regulatory control</dd></div>
              <div><dt>Beneficial owner</dt><dd>Schedule 13D/G ownership above the reporting threshold</dd></div>
              <div><dt>Significant control</dt><dd>Companies House persons with significant control</dd></div>
              <div><dt>Reported position</dt><dd>SEC 13F investment discretion, not ownership</dd></div>
            </dl>
            <p>This prevents two damaging shortcuts: attaching a security identifier to its issuer as though they were the same node, and treating an investment position as corporate ownership. Every graph fact retains a document ID and locator back to the record that asserted it.</p>
          </section>

          <section className={styles.section} id="runtime">
            <p className={styles.sectionLabel}>04 · Runtime</p>
            <h2>Search and agent mode are different interfaces over the same records.</h2>
            <p>Search is the direct path. The API retrieves ranked entity candidates, selects the first result by default, and opens its pre-shaped profile beside the list. The profile includes identity, lineage, identifiers, resolution decisions, typed connections and source-specific activity.</p>
            <p>Agent mode is the investigative path. It can chain several lookups, compare records and explain what the evidence does or does not establish. It does not get a private database shortcut. Its MCP tools call the same core entity, graph and filing logic used by the API and command line.</p>
            <QueryPathsFigure />
          </section>

          <section className={styles.section} id="agent">
            <p className={styles.sectionLabel}>05 · The research loop</p>
            <h2>The model chooses tools. The tools create the evidence.</h2>
            <ol className={styles.steps}>
              <li><span>1</span><div><strong>Plan a narrow lookup</strong><p>The model sees tool schemas and chooses a search, profile, hierarchy, filing or connection call.</p></div></li>
              <li><span>2</span><div><strong>Call the MCP server</strong><p>The orchestrator talks to a standalone process over stdio. Each tool is a thin wrapper around tested core logic.</p></div></li>
              <li><span>3</span><div><strong>Store evidence and facts</strong><p>Every result records its source, criteria, record references and reproducible query hash. Numeric facts include a document address.</p></div></li>
              <li><span>4</span><div><strong>Continue or submit</strong><p>The model can investigate further, but its final citations are restricted to evidence IDs produced in this conversation.</p></div></li>
              <li><span>5</span><div><strong>Verify the finished answer</strong><p>A separate decision model checks grounding, contradiction, citation support and scope against the complete tool transcript.</p></div></li>
            </ol>
            <p>The live interface streams these stages as server-sent events. Tool calls and results appear while the run is active; the finished answer replaces the activity feed while the evidence rail remains available.</p>
          </section>

          <section className={styles.section} id="verification">
            <p className={styles.sectionLabel}>06 · The answer gate</p>
            <h2>The model cannot type a number into the final answer.</h2>
            <p>Tools return addressed <code>Fact</code> objects. The draft refers to them with placeholders such as <code>{"{{f:fact_id}}"}</code>. Before accepting the answer, the submission gate groups every referenced fact by its originating tool call, repeats those calls and checks that each fact returns with the same value.</p>
            <EvidenceGateFigure />
            <p>Only then does the renderer replace placeholders with values. Computed changes and percentages must come from registered formulas and carry their input facts. This separates fluent writing from numerical authority.</p>
            <aside className={styles.note}><strong>Two different checks</strong><p>The submission gate establishes mechanical reproducibility. The verifier judges whether the prose is grounded, uncontradicted, correctly cited and within the retrieved evidence.</p></aside>
          </section>

          <section className={styles.section} id="limits">
            <p className={styles.sectionLabel}>07 · Honest limits</p>
            <h2>Absence from the graph is not proof of absence.</h2>
            <p>Coverage follows the records that were available, ingested and successfully linked for a specific date. Sources can lag, disagree or omit relationships. The interface exposes dates, warnings and provenance so a user can judge that boundary.</p>
            <div className={styles.limitList}>
              <div><strong>SEC 13F is not a complete portfolio.</strong><p>It covers certain reportable US equity securities at a quarterly date. It excludes shorts, many derivatives, non-US securities, private investments and positions below reporting thresholds.</p></div>
              <div><strong>A match score is not probability.</strong><p>It is a deterministic weighted signal whose contributions can be inspected. Decision thresholds and the runner-up gap determine whether the system resolves or abstains.</p></div>
              <div><strong>Relationship words are source-specific.</strong><p>Manager, beneficial owner, accounting parent and person with significant control answer different legal and regulatory questions.</p></div>
            </div>
          </section>

          <footer className={styles.footer}>
            <p>The useful test is not whether the platform can produce an answer. It is whether you can follow that answer back through the decision, fact, record and source.</p>
            <Link href="/">Try it with an institution <ArrowRight aria-hidden="true" /></Link>
          </footer>
        </div>
      </article>
    </main>
  );
}
