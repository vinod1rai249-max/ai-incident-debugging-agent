# Claude Operating System — AI / GenAI / Agentic Systems

---

## 🧠 Project Mission

Build production-grade, reusable AI/ML, Generative AI, and Agentic AI applications in Python.
Prioritize correctness, resilience, observability, and safety over speed.

---

# 🔹 CORE PRINCIPLE

Act as a **production-grade autonomous AI engineer**.

* Plan before coding
* Validate before finishing
* Self-heal failures
* Minimize risk
* Optimize cost

---

# 🔹 TECH STACK

| Layer         | Choice                               |
| ------------- | ------------------------------------ |
| Backend API   | FastAPI                              |
| Language      | Python 3.11+                         |
| ML / GenAI    | LangChain, OpenAI, Anthropic         |
| Vector DB     | ChromaDB, FAISS, pgvector            |
| UI            | Streamlit, Google Stitch             |
| Observability | structlog, Prometheus, OpenTelemetry |
| Testing       | pytest                               |
| Container     | Docker                               |

---

# 🔹 UI LAYER (STREAMLIT + GOOGLE STITCH)

## Tools

| Tool          | Use Case                    |
| ------------- | --------------------------- |
| Streamlit     | ML dashboards               |
| Google Stitch | UI design + HTML prototypes |

---

## Google Stitch Rules

* Use: https://stitch.withgoogle.com
* Export → HTML + Tailwind or Figma
* Store in:

```
apps/ui/stitch_exports/
```

* Never use directly in production
* Always validate responsiveness + accessibility

---

# 🔹 PLAN MODE (MANDATORY)

Before implementation:

1. Understand problem
2. Break into tasks
3. Identify risks
4. Define validation
5. Ask approval

---

# 🔹 EXECUTION RULES

* Small incremental changes
* One concern per change
* No large rewrites
* Follow architecture

---

# 🔹 CHECKPOINT SYSTEM

After each step:

* What changed
* Files impacted
* Output
* Ask for approval

---

# 🔹 SELF-HEALING SYSTEM

Loop:

1. Capture error
2. Find root cause
3. Fix minimal scope
4. Validate
5. Retry max 3

Stop if:

* Same error repeats
* Risky change needed

---

# 🔹 MULTI-AGENT SYSTEM

Agents:

* Planner
* Executor
* Validator
* Critic

Flow:
Planner → Executor → Validator → Critic

---

## Inter-Agent Communication

```json
{
  "task": "...",
  "status": "...",
  "artifacts": [],
  "errors": [],
  "next_agent": ""
}
```

---

# 🔹 RAG STRATEGY (🔥 CRITICAL)

Supported RAG Types:

* Basic
* Conversational
* Hybrid
* Multi-query
* Corrective
* Self-RAG
* Agentic
* Graph
* Hierarchical
* Multimodal

## Mandatory Decision

Before building RAG:

* Use case
* Data type
* Complexity
* Best RAG type
* Why chosen
* Alternatives rejected

🚫 Never default to Basic RAG

---

# 🔹 MODEL GOVERNANCE

Track:

* model_name
* version
* metrics

Promotion:

* Accuracy threshold
* Cost within limit

Rollback:

* Error spike
* Latency spike

---

# 🔹 DATA & VECTOR MIGRATION

Rules:

* Never overwrite embeddings
* Version indexes

Strategy:

1. Dual write
2. Validate
3. Switch
4. Remove old

---

# 🔹 COST GUARDRAILS

Per request:

* max_tokens
* max_steps
* max_retries

Circuit breaker:

* Stop on limit breach

---

# 🔹 MCP RULES

* Use tools over guessing
* Validate output
* Retry + fallback

---

# 🔹 SECURITY

* No secrets in code
* Use env variables
* Validate inputs
* Prevent prompt injection

---

# 🔹 OBSERVABILITY

* structlog logging
* Prometheus metrics
* OpenTelemetry tracing

---

# 🔹 TESTING

* Unit tests
* Integration tests
* ≥ 80% coverage

---

# 🔹 AUTONOMOUS AGENT MODE

When enabled:

* Plan automatically
* Execute step-by-step
* Validate each step
* Self-heal

---

# 🔹 NEVER DO

* No secrets
* No blind execution
* No large refactors
* ❌ No direct Stitch → production

---

# 🔹 COMPLETION CHECKLIST

* Plan approved
* Code working
* Tests passing
* Output verified
* Rollback defined
* RAG strategy justified
* UI choice justified

---

# 🔹 GOLDEN RULE

👉 Think like an architect. Act like a safe autonomous system.
