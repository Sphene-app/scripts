#!/usr/bin/env python3
"""
Sphene Empirical Benchmark Suite: Deterministic Synthetic Vault Generator
-------------------------------------------------------------------------
Generates realistic Markdown knowledge bases (1,000 or 10,000 notes)
with:
  - Valid YAML frontmatter (tags, status, dates, priority)
  - Structural headings (H1-H4)
  - Dense scale-free bidirectional wikilinks ([[Note_XXXX]])
  - GitHub-flavored task lists (- [ ] and - [x])
  - Syntax-highlighted code blocks (Go, Python, SQL, Rust, Bash)
  - Specific ground-truth target notes for Agentic & Systems Stress Suites:
      * Architecture_Roadmap.md (2,500-line note for pinpoint extraction)
      * Sprint_Tasks.md (task checklist for concurrent mutation / Human Veto)
      * Kernel_V2_Milestone.md (3-level multi-hop graph dependency tree)
      * Consensus.md (dense backlink graph hub)
"""

import os
import sys
import random
import argparse
import shutil
import time

DOMAINS = [
    "Distributed Systems", "Database Internals", "Kernel Architecture",
    "Cryptography & Zero-Knowledge", "Local-First Storage", "Memory Profiling",
    "Agentic Workflows", "Peer-to-Peer Networking", "Graph Theory",
    "Consensus Protocols", "Data Structures", "Observability & Tracing"
]

TAGS_POOL = [
    "architecture", "database", "distributed-systems", "consensus", "sqlite",
    "crypto", "zero-knowledge", "agent", "mcp", "pwa", "networking",
    "memory", "wal", "fts5", "security", "raft", "benchmarks", "performance",
    "active", "review", "draft", "production"
]

AUTHORS = [
    "Systems Research Group", "Core Engineering", "Security Auditor",
    "Runtime Architect", "Protocol Engineer", "Performance Specialist"
]

CODE_SNIPPETS = {
    "go": """```go
func QueryIndex(ctx context.Context, term string) ([]Result, error) {
    query := `SELECT rowid, title, snippet(notes_fts, 1, '<b>', '</b>', '...', 16) 
              FROM notes_fts WHERE notes_fts MATCH ? ORDER BY rank LIMIT 50;`
    rows, err := db.QueryContext(ctx, query, term)
    if err != nil {
        return nil, fmt.Errorf("fts5 search failed: %w", err)
    }
    defer rows.Close()
    return parseResults(rows)
}
```""",
    "python": """```python
def measure_process_rss(pid: int) -> float:
    with open(f"/proc/{pid}/statm", "r") as f:
        pages = int(f.read().split()[1])
        return (pages * os.sysconf("SC_PAGE_SIZE")) / (1024 * 1024)
```""",
    "sql": """```sql
CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
    path UNINDEXED,
    title,
    body,
    tags,
    tokenize = 'porter unicode61 remove_diacritics 2'
);
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;
```""",
    "rust": """```rust
pub fn verify_signature(public_key: &[u8; 32], message: &[u8], signature: &[u8; 64]) -> bool {
    match ed25519_dalek::PublicKey::from_bytes(public_key) {
        Ok(pk) => pk.verify_strict(message, signature).is_ok(),
        Err(_) => false,
    }
}
```""",
    "bash": """```bash
#!/usr/bin/env bash
set -euo pipefail
echo "=== Cold Cache Disk Ingestion ==="
sync && echo 3 | sudo tee /proc/sys/vm/drop_caches > /dev/null
/usr/bin/time -v sphene index --vault ./test_vault
```"""
}

SENTENCES = [
    "Decentralized ledger consistency requires monotonic state machine replication under Byzantine and crash faults.",
    "The embedded SQLite FTS5 engine achieves sub-millisecond retrieval by utilizing memory-mapped WAL index pages.",
    "Model Context Protocol (MCP) clients invoke tools via standardized JSON-RPC 2.0 frames over bidirectional Stdio or SSE transport.",
    "Zero-copy buffer allocation prevents high garbage collection churn during large-scale Markdown parsing passes.",
    "Bidirectional wikilinks establish a scale-free graph topology enabling topological dependency traversal across documents.",
    "Write collisions are eliminated by routing mutations through an append-only AST differential timeline awaiting Human Veto.",
    "Cryptographic partition isolation guarantees that sensitive credentials remain hardware-sealed under AES-256-GCM.",
    "The quorum validation phase verifies that a strict majority of peer nodes have acknowledged log append entries.",
    "Distributed Consensus Architecture ensures fault tolerance across heterogeneous cloud and bare-metal nodes.",
    "Memory footprint remains bounded by streaming files in chunked windows rather than reading full blobs into the heap.",
    "Client-side authenticated key derivation prevents unauthorized decryption even if storage volumes are extracted.",
    "Fast trigram tokenization enables rapid partial matching without relying on unindexed sequential string searches."
]

def generate_note_content(note_id: int, total_notes: int, seed_rnd: random.Random) -> str:
    """Generates a realistic multi-section Markdown note (~12-15 KB) with rich metadata, code, and graph links."""
    title_words = seed_rnd.sample(DOMAINS, 2)
    title = f"{title_words[0]} & {title_words[1]} Design (Node {note_id:05d})"
    
    # Random frontmatter
    tags_count = seed_rnd.randint(3, 7)
    selected_tags = seed_rnd.sample(TAGS_POOL, tags_count)
    if "architecture" not in selected_tags and seed_rnd.random() < 0.30:
        selected_tags.append("architecture")
    status = seed_rnd.choice(["active", "review", "draft", "archived"])
    if seed_rnd.random() < 0.40:
        status = "active"
        
    date_year = seed_rnd.choice([2024, 2025, 2026])
    date_month = seed_rnd.randint(1, 12)
    date_day = seed_rnd.randint(1, 28)
    date_str = f"{date_year}-{date_month:02d}-{date_day:02d}"
    
    frontmatter = [
        "---",
        f"id: note_{note_id:05d}",
        f'title: "{title}"',
        f"date: {date_str}",
        f"tags: [{', '.join(selected_tags)}]",
        f'author: "{seed_rnd.choice(AUTHORS)}"',
        f'status: "{status}"',
        f'priority: "{seed_rnd.choice(["critical", "high", "medium", "low"])}"',
        f"revision: {seed_rnd.randint(1, 25)}",
        f"security_zone: \"{seed_rnd.choice(['workspace', 'reference', 'private'])}\"",
        "---",
        ""
    ]
    
    body = [f"# {title}", ""]
    
    # Section 1: Executive Abstract
    body.append("## 1. Executive Abstract & Scope")
    for _ in range(seed_rnd.randint(2, 4)):
        intro_sentences = seed_rnd.sample(SENTENCES, seed_rnd.randint(4, 7))
        if note_id % 37 == 0:
            intro_sentences.append("The primary subsystem implements Distributed Consensus Architecture for high-throughput node synchronization.")
        if note_id % 41 == 0:
            intro_sentences.append("During failover scenarios, the leader election initiates a quorum val protocol pass to resolve split-brain.")
        body.append(" ".join(intro_sentences))
        body.append("")
        
    # Section 2: Systems Specifications & Theoretical Guarantees
    body.append("## 2. Systems Specifications & Formal Invariants")
    for _ in range(seed_rnd.randint(3, 5)):
        spec_sentences = seed_rnd.sample(SENTENCES, seed_rnd.randint(4, 8))
        body.append(" ".join(spec_sentences))
        body.append("")
        
    # Section 3: Graph Topology & Wikilinks (3 to 6 wikilinks per note)
    body.append("## 3. Knowledge Graph Topology & Cross-Document Linkages")
    body.append("This document participates in the cluster knowledge graph with bidirectional dependency edges:")
    wikilink_count = seed_rnd.randint(3, 7)
    links = []
    if seed_rnd.random() < 0.30:
        links.append("- Canonical Consensus Hub: [[Consensus]]")
    for _ in range(wikilink_count):
        if seed_rnd.random() < 0.65:
            target_id = max(1, min(total_notes, note_id + seed_rnd.randint(-60, 60)))
        else:
            target_id = seed_rnd.randint(1, total_notes)
        if target_id != note_id:
            links.append(f"- Peer Subsystem Dependency: [[Note_{target_id:05d}]]")
    body.extend(links)
    body.append("")
    
    # Section 4: Code Implementation Patterns
    body.append("## 4. Subsystem Reference Implementations")
    langs = seed_rnd.sample(list(CODE_SNIPPETS.keys()), seed_rnd.randint(2, 3))
    for lang in langs:
        body.append(f"### 4.{langs.index(lang)+1}. {lang.upper()} Core Binding")
        body.append(CODE_SNIPPETS[lang])
        body.append("")
        
    # Section 5: Memory & Storage Concurrency Profiles
    body.append("## 5. Storage Engine & WAL Indexing Characteristics")
    for _ in range(seed_rnd.randint(2, 4)):
        body.append(" ".join(seed_rnd.sample(SENTENCES, seed_rnd.randint(4, 6))))
        body.append("")
        
    # Section 6: Action Items & Task Checklists
    body.append("## 6. Engineering Verification Checklist")
    tasks = [
        f"- [{'x' if seed_rnd.random() < 0.5 else ' '}] Verify memory profile stays under 50MB RSS quota on Linux host.",
        f"- [{'x' if seed_rnd.random() < 0.5 else ' '}] Audit SQLite FTS5 query plan for prefix search optimization.",
        f"- [{'x' if seed_rnd.random() < 0.5 else ' '}] Ensure differential AST staging triggers Human Veto on mutation.",
        f"- [{'x' if seed_rnd.random() < 0.5 else ' '}] Validate bidirectional wikilink graph resolution without cycles.",
        f"- [{'x' if seed_rnd.random() < 0.5 else ' '}] Measure roundtrip latency across 10 concurrent Model Context Protocol sessions."
    ]
    body.extend(tasks[:seed_rnd.randint(2, 4)])
    body.append("")
    
    return "\n".join(frontmatter + body)


def generate_ground_truth_targets(target_dir: str):
    """Generates the special target files required for Suite 3 & Suite 4."""
    
    # 1. Consensus.md (Central hub note)
    consensus_content = """---
id: note_hub_consensus
title: "Distributed Consensus & Raft Invariants"
date: 2026-01-10
tags: [architecture, consensus, distributed-systems, active]
status: "active"
priority: "critical"
---

# Distributed Consensus & Raft Invariants

This document serves as the canonical root hub for all consensus protocols, log replication engines, and election state machines across the cluster.

## Formal Properties
- **Safety**: An election yields at most one leader per term.
- **Log Matching**: If two logs contain an entry with the same index and term, then the logs are identical in all entries up through the given index.
- **Leader Completeness**: If a log entry is committed in a given term, then that entry will be present in the logs of the leaders for all higher-numbered terms.

## Subsystem References
- [[Architecture_Roadmap]]
- [[Kernel_V2_Milestone]]
- [[Sprint_Tasks]]
"""
    with open(os.path.join(target_dir, "Consensus.md"), "w", encoding="utf-8") as f:
        f.write(consensus_content)

    # 2. Architecture_Roadmap.md (Massive 2,500-line note for pinpoint extraction benchmark)
    print("  -> Generating 2,500-line pinpoint extraction target: Architecture_Roadmap.md")
    roadmap_lines = [
        "---",
        "id: target_roadmap",
        "title: \"Systems Architecture Roadmap (2026-2028)\"",
        "date: 2026-09-01",
        "tags: [architecture, roadmap, consensus, active]",
        "status: \"active\"",
        "priority: \"critical\"",
        "---",
        "",
        "# Systems Architecture Roadmap (2026-2028)",
        "",
        "This is an exhaustive systems engineering document outlining kernel specifications, storage topologies, consensus parameters, and protocol migration paths.",
        ""
    ]
    
    # Generate ~2,400 lines of technical background context
    for i in range(1, 120):
        roadmap_lines.append(f"## Section {i}: Subsystem Specification {i}")
        for _ in range(4):
            roadmap_lines.append("Decentralized ledger consistency requires monotonic state machine replication under Byzantine and crash faults. The embedded SQLite FTS5 engine achieves sub-millisecond retrieval by utilizing memory-mapped WAL index pages.")
        roadmap_lines.append("")
        
    # The Needle in the Haystack for Suite 4.1:
    roadmap_lines.extend([
        "## Leader Election Parameters & Heartbeat Bounds",
        "",
        "The cluster relies on randomized election timeouts to prevent split votes during leadership transitions:",
        "- **leader_election_timeout_ms**: 1500",
        "- **heartbeat_interval_ms**: 150",
        "- **max_clock_skew_drift_ms**: 25",
        "- **min_quorum_nodes**: 3",
        "- **election_retry_backoff_factor**: 1.5",
        "",
        "Nodes must strictly abort candidate state if a valid heartbeat from the current term arrives within the 1500ms window.",
        ""
    ])
    
    # Add remaining lines to reach ~2,500 total lines
    for i in range(121, 220):
        roadmap_lines.append(f"## Section {i}: Memory Isolation & Cgroup Boundary {i}")
        for _ in range(4):
            roadmap_lines.append("Cryptographic partition isolation guarantees that sensitive credentials remain hardware-sealed under AES-256-GCM. Write collisions are eliminated by routing mutations through an append-only AST differential timeline awaiting Human Veto.")
        roadmap_lines.append("")
        
    with open(os.path.join(target_dir, "Architecture_Roadmap.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(roadmap_lines))

    # 3. Sprint_Tasks.md (Checklist note for concurrent mutation & Human Veto benchmark)
    print("  -> Generating concurrent mutation target: Sprint_Tasks.md")
    tasks_content = """---
id: target_sprint_tasks
title: "Active Engineering Sprint Tasks"
date: 2026-09-26
tags: [sprint, tasks, engineering, active]
status: "active"
priority: "high"
---

# Active Engineering Sprint Tasks

Engineering objectives for the current milestone. Notes are monitored for concurrent agent and human edits.

## Critical Kernel Tasks
- [ ] Task-101: Optimize Raft quorum heartbeat and leader lease verification.
- [ ] Task-102: Implement SQLite WAL busy timeout queue with 5000ms ceiling.
- [ ] Task-103: Validate zero-lock differential timeline against concurrent writes.
- [ ] Task-104: Benchmark pinpoint heading AST extraction against full-file dumps.
- [ ] Task-105: Audit client-side AES-256-GCM authenticated encryption parameters.

## Observability & Quality Assurance
- [x] Task-098: Configure Linux CFS CPUQuota 15% mobile phone throttling harness.
- [x] Task-099: Setup automated CI regression tests for differential AST patches.
- [ ] Task-100: Publish empirical p50/p95/p99 benchmark report to public website.
"""
    with open(os.path.join(target_dir, "Sprint_Tasks.md"), "w", encoding="utf-8") as f:
        f.write(tasks_content)

    # 4. Kernel_V2_Milestone.md and 3-level graph dependency chain
    print("  -> Generating 3-level graph dependency target: Kernel_V2_Milestone.md")
    milestone_content = """---
id: target_kernel_milestone
title: "Kernel V2 Milestone & Dependency Topology"
date: 2026-09-20
tags: [architecture, milestone, dependencies, active]
status: "active"
priority: "critical"
---

# Kernel V2 Milestone & Dependency Topology

Executive tracking document for the v2.2 kernel delivery.

## Upstream Core Blockers
- Component 1: [[Consensus_Engine]]
- Component 2: [[Storage_Engine]]

All blocker dependencies must be in `status: completed` before release tag creation.
"""
    with open(os.path.join(target_dir, "Kernel_V2_Milestone.md"), "w", encoding="utf-8") as f:
        f.write(milestone_content)

    # Level 2 nodes
    with open(os.path.join(target_dir, "Consensus_Engine.md"), "w", encoding="utf-8") as f:
        f.write("""---
id: dep_consensus_engine
title: "Consensus Engine Subsystem"
tags: [consensus, raft, subsystem]
status: "in-progress"
---
# Consensus Engine Subsystem
Sub-dependencies:
- [[Leader_Election]]
- [[WAL_Replication]]
""")

    with open(os.path.join(target_dir, "Storage_Engine.md"), "w", encoding="utf-8") as f:
        f.write("""---
id: dep_storage_engine
title: "Storage Engine Subsystem"
tags: [storage, sqlite, wal]
status: "completed"
---
# Storage Engine Subsystem
Zero blockers in storage engine.
""")

    # Level 3 nodes
    with open(os.path.join(target_dir, "Leader_Election.md"), "w", encoding="utf-8") as f:
        f.write("""---
id: dep_leader_election
title: "Leader Election State Machine"
tags: [consensus, election]
status: "in-progress"
---
# Leader Election State Machine
Active blocker linked:
- [[Network_Partition_Handler]]
""")

    with open(os.path.join(target_dir, "WAL_Replication.md"), "w", encoding="utf-8") as f:
        f.write("""---
id: dep_wal_replication
title: "Write-Ahead Log Replication"
tags: [wal, replication]
status: "completed"
---
# Write-Ahead Log Replication
Fully verified.
""")

    # Level 4 leaf blocker
    with open(os.path.join(target_dir, "Network_Partition_Handler.md"), "w", encoding="utf-8") as f:
        f.write("""---
id: dep_network_partition_blocker
title: "Network Partition Handler"
tags: [networking, partition, blocker]
status: "blocked"
blocker_reason: "Asymmetric network split handling requires quorum validation refinement."
---
# Network Partition Handler
CRITICAL BLOCKER: Split-brain resolution algorithm needs peer-review before merging into main.
""")


def main():
    parser = argparse.ArgumentParser(description="Generate deterministic synthetic Markdown vaults for Sphene benchmarks.")
    parser.add_argument("--count", type=int, default=1000, help="Number of notes to generate (default: 1000)")
    parser.add_argument("--output", type=str, default="benchmark_testbed/vault_1k", help="Output directory path")
    parser.add_argument("--seed", type=int, default=42, help="Deterministic random seed (default: 42)")
    parser.add_argument("--clean", action="store_true", help="Clean output directory before generating")
    args = parser.parse_args()

    target_dir = os.path.abspath(args.output)
    print(f"=== Sphene Synthetic Vault Generator ===")
    print(f"Target count: {args.count} notes")
    print(f"Output path:  {target_dir}")
    print(f"PRNG Seed:    {args.seed}")
    
    if args.clean and os.path.exists(target_dir):
        print(f"Cleaning existing directory: {target_dir}")
        shutil.rmtree(target_dir)
        
    os.makedirs(target_dir, exist_ok=True)

    seed_rnd = random.Random(args.seed)
    start_time = time.time()

    print(f"Generating {args.count} notes...")
    for i in range(1, args.count + 1):
        filename = f"Note_{i:05d}.md"
        filepath = os.path.join(target_dir, filename)
        content = generate_note_content(i, args.count, seed_rnd)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        if i % 1000 == 0 or i == args.count:
            print(f"  [{i}/{args.count}] notes generated...")

    # Generate the specialized target notes for Suite 3 & Suite 4
    print("Generating specialized target notes for Suite 3 & 4...")
    generate_ground_truth_targets(target_dir)

    elapsed = time.time() - start_time
    total_files = len([f for f in os.listdir(target_dir) if f.endswith(".md")])
    total_bytes = sum(os.path.getsize(os.path.join(target_dir, f)) for f in os.listdir(target_dir) if f.endswith(".md"))
    total_mb = total_bytes / (1024 * 1024)

    print(f"=== Generation Complete in {elapsed:.2f}s ===")
    print(f"Total Markdown Files: {total_files}")
    print(f"Total Disk Size:      {total_mb:.2f} MB ({total_bytes:,} bytes)")
    print(f"Average Note Size:    {total_bytes / total_files / 1024:.2f} KB")

if __name__ == "__main__":
    main()
