---
name: specflow.tasks
description: Decompose plan into executable tasks with dependencies
---

Break technical plan into atomic, executable tasks.

## Arguments

$ARGUMENTS - Spec ID to create tasks for

## Prerequisites

- plan.md must exist
- Spec status: planned

## Execution Flow

1. **Load Context**
   - Read specs/{id}/plan.md
   - Read specs/{id}/spec.md
   - Understand architecture decisions

2. **Delegate to Architect**
   - Continue with @specflow-architect agent
   - Request task decomposition

3. **Task Decomposition**
   - Break plan into atomic tasks
   - Identify dependencies between tasks
   - Assign priorities
   - Mark parallelizable tasks
   - Estimate complexity

4. **Create tasks.md**
   - List all tasks with metadata:
     - ID, title, description
     - Priority (1-10)
     - Dependencies (list of task IDs)
     - Assignee type (coder/reviewer/tester)
     - Complexity (low/medium/high)
     - Parallelizable (yes/no)
   - Dependency graph (Mermaid diagram)

5. **Populate Database**
   - Insert all tasks into SQLite
   - Set initial status: pending
   - Mark dependency relationships

6. **Update Spec Status**
   - Set status to: ready
   - Ready for implementation

## Task Format

Each task in tasks.md:

```markdown
## Task: task-001
- **Title**: Setup database schema
- **Description**: Create SQLite schema for user management
- **Priority**: 10
- **Dependencies**: []
- **Complexity**: low
- **Assignee**: coder
- **Parallelizable**: no
- **Acceptance Criteria**:
  - Users table created
  - Indexes defined
  - Migration script exists
```

## Output

- Confirmation of tasks.md created
- Total task count
- Ready task count (no dependencies)
- Dependency graph visualization
- Prompt to proceed with /specflow.implement

## AUTONOMOUS

No human approval needed.
Architect decomposes based on approved spec and plan.
