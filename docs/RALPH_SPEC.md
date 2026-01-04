# Ralph Loop Integration Specification

## Executive Summary

This document specifies the integration of Ralph-style self-assessment loops into SpecFlow's execution pipeline. The goal is to enable agents to iteratively refine their work until genuinely complete, rather than relying on single-pass execution with fixed retry limits.

---

## Goals

1. **Self-Assessment** - Agents validate their own work quality before proceeding
2. **Iterative Refinement** - Continue until completion criteria are genuinely met
3. **Quality Assurance** - Explicit completion promises with verification
4. **Configurable Behavior** - Enable/disable per-agent or globally
5. **Safety Limits** - Maximum iterations to prevent infinite loops

---

## Architecture

### High-Level Design

```
┌─────────────────────────────────────────────────────────────┐
│                    SpecFlow Execution                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Task Queue                                                 │
│      │                                                      │
│      ▼                                                      │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              Ralph-Enabled Agent Execution            │  │
│  │  ┌────────────────────────────────────────────────┐  │  │
│  │  │                                                │  │  │
│  │  │  1. Build prompt with completion requirements  │  │  │
│  │  │           │                                    │  │  │
│  │  │           ▼                                    │  │  │
│  │  │  2. Execute agent (Claude Code)               │  │  │
│  │  │           │                                    │  │  │
│  │  │           ▼                                    │  │  │
│  │  │  3. Parse output for completion promise       │  │  │
│  │  │           │                                    │  │  │
│  │  │     ┌─────┴─────┐                             │  │  │
│  │  │     ▼           ▼                             │  │  │
│  │  │  Promise     No Promise                       │  │  │
│  │  │  Found       Found                            │  │  │
│  │  │     │           │                             │  │  │
│  │  │     ▼           ▼                             │  │  │
│  │  │  Verify     Check iteration limit             │  │  │
│  │  │  Promise         │                            │  │  │
│  │  │     │       ┌────┴────┐                       │  │  │
│  │  │     │       ▼         ▼                       │  │  │
│  │  │     │    Limit     Continue                   │  │  │
│  │  │     │    Reached   Loop (→ step 1)            │  │  │
│  │  │     │       │                                 │  │  │
│  │  │     ▼       ▼                                 │  │  │
│  │  │   EXIT    EXIT                                │  │  │
│  │  │ (success) (max iter)                          │  │  │
│  │  │                                                │  │  │
│  │  └────────────────────────────────────────────────┘  │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Components

#### 1. RalphLoop Class

New class to manage iterative execution:

```python
# src/specflow/orchestration/ralph.py

@dataclass
class RalphLoopConfig:
    """Configuration for Ralph-style loops."""
    enabled: bool = True
    max_iterations: int = 10
    completion_promise: str = "STAGE_COMPLETE"
    verify_promise: bool = True

@dataclass
class RalphLoopState:
    """State for an active Ralph loop."""
    task_id: str
    stage: str
    iteration: int
    max_iterations: int
    completion_promise: str
    started_at: datetime
    prompt: str

class RalphLoop:
    """Manages Ralph-style iterative agent execution."""

    def __init__(self, config: RalphLoopConfig, project: Project):
        self.config = config
        self.project = project
        self.state: RalphLoopState | None = None

    def start(self, task: Task, stage: PipelineStage, prompt: str) -> None:
        """Start a new Ralph loop for a task stage."""
        pass

    def should_continue(self, output: str) -> bool:
        """Check if loop should continue based on output."""
        pass

    def extract_promise(self, output: str) -> str | None:
        """Extract completion promise from output."""
        pass

    def verify_promise(self, promise: str, output: str) -> bool:
        """Verify the completion promise is genuine."""
        pass

    def increment(self) -> int:
        """Increment iteration counter, return new value."""
        pass

    def cancel(self) -> None:
        """Cancel the active loop."""
        pass
```

#### 2. Enhanced Agent Prompts

Add completion promise requirements to agent prompts:

```python
# In ExecutionPipeline._build_agent_prompt()

RALPH_PROMPT_SUFFIX = """
## Completion Requirements

When you have GENUINELY completed this stage, output:

<promise>{completion_promise}</promise>

IMPORTANT:
- Only output the promise when ALL requirements are met
- The promise must be completely and unequivocally TRUE
- Do NOT output a false promise to exit early
- If blocked, explain what's preventing completion

Your work will be verified. False promises will be detected.
"""
```

#### 3. Modified Execution Pipeline

Update `ExecutionPipeline._execute_stage()` to use Ralph loops:

```python
def _execute_stage(
    self, task: Task, stage: PipelineStage, worktree_path: Path, iteration: int
) -> ExecutionResult:
    """Execute a single pipeline stage with Ralph loop."""

    ralph_config = self._get_ralph_config(stage.agent_type)

    if not ralph_config.enabled:
        # Original single-pass execution
        return self._execute_stage_once(task, stage, worktree_path, iteration)

    # Ralph-enabled execution
    ralph = RalphLoop(ralph_config, self.project)
    ralph.start(task, stage, self._build_agent_prompt(task, stage, worktree_path, iteration))

    while True:
        result = self._execute_stage_once(task, stage, worktree_path, ralph.iteration)

        if not ralph.should_continue(result.output):
            return result

        if ralph.iteration >= ralph_config.max_iterations:
            result.success = False
            result.issues.append(f"Ralph loop exceeded {ralph_config.max_iterations} iterations")
            return result

        ralph.increment()
        # Loop continues with same prompt, Claude sees previous work in files
```

#### 4. Configuration Updates

Add Ralph configuration to `config.yaml`:

```yaml
# .specflow/config.yaml

ralph:
  enabled: true                    # Global enable/disable
  default_max_iterations: 10       # Default iteration limit
  verify_promises: true            # Verify completion promises

  # Per-agent configuration
  coder:
    enabled: true
    max_iterations: 15
    completion_promise: "IMPLEMENTATION_COMPLETE"

  reviewer:
    enabled: true
    max_iterations: 5
    completion_promise: "REVIEW_COMPLETE"

  tester:
    enabled: true
    max_iterations: 10
    completion_promise: "TESTS_COMPLETE"

  qa:
    enabled: true
    max_iterations: 5
    completion_promise: "QA_PASSED"
```

#### 5. Promise Verification

Implement verification beyond simple string matching:

```python
class PromiseVerifier:
    """Verifies completion promises are genuine."""

    def verify(self, promise: str, output: str, context: dict) -> tuple[bool, str]:
        """Verify a completion promise.

        Returns:
            Tuple of (is_valid, reason)
        """
        # 1. Check promise is present and correctly formatted
        if not self._check_format(promise, output):
            return False, "Promise not found or malformed"

        # 2. Check for contradiction indicators
        if self._has_contradictions(output):
            return False, "Output contains contradictions to promise"

        # 3. Stage-specific verification
        return self._verify_stage_specific(promise, output, context)

    def _has_contradictions(self, output: str) -> bool:
        """Check for phrases that contradict completion."""
        contradiction_patterns = [
            r"TODO:",
            r"FIXME:",
            r"not yet implemented",
            r"still need to",
            r"remaining work",
            r"blocked by",
            r"cannot complete",
            r"tests? fail",
        ]
        # ...

    def _verify_stage_specific(self, promise: str, output: str, context: dict) -> tuple[bool, str]:
        """Stage-specific verification logic."""
        stage = context.get("stage")

        if stage == "coder":
            # Check for commit in output
            if "committed" not in output.lower() and "commit" not in output.lower():
                return False, "No commit detected in coder output"

        elif stage == "tester":
            # Check for test results
            if "passed" not in output.lower() and "TESTS PASSED" not in output:
                return False, "No passing tests detected"

        elif stage == "reviewer":
            # Check for review completion
            if "REVIEW PASSED" not in output and "approved" not in output.lower():
                return False, "No review approval detected"

        return True, "Promise verified"
```

---

## Implementation Plan

### Phase 1: Core Infrastructure

**Files to create:**
- `src/specflow/orchestration/ralph.py` - RalphLoop class and utilities

**Files to modify:**
- `src/specflow/core/config.py` - Add Ralph configuration
- `src/specflow/orchestration/execution.py` - Integrate Ralph loops

**Tasks:**
1. Create `RalphLoopConfig` and `RalphLoopState` dataclasses
2. Implement `RalphLoop` class with basic iteration logic
3. Add Ralph configuration to `DEFAULT_CONFIG`
4. Update `Config` class to parse Ralph settings

### Phase 2: Execution Integration

**Tasks:**
1. Modify `ExecutionPipeline._execute_stage()` to use Ralph loops
2. Update agent prompts with completion promise requirements
3. Implement promise extraction from output
4. Add iteration tracking to execution logs

### Phase 3: Promise Verification

**Tasks:**
1. Create `PromiseVerifier` class
2. Implement contradiction detection
3. Add stage-specific verification rules
4. Integrate verification into Ralph loop

### Phase 4: CLI & TUI Integration

**Tasks:**
1. Add `specflow ralph-status` command to show active loops
2. Add `specflow ralph-cancel` command to cancel loops
3. Update TUI swimlanes to show iteration count
4. Add Ralph loop indicators to agent panel

### Phase 5: Testing & Documentation

**Tasks:**
1. Write unit tests for `RalphLoop` class
2. Write integration tests for Ralph-enabled execution
3. Update README with Ralph configuration docs
4. Add examples and best practices

---

## Detailed Specifications

### Prompt Format

Agent prompts will include completion requirements:

```markdown
## Task Information
- **Task ID**: TASK-001
- **Title**: Implement user authentication
- **Stage**: Implementation
- **Ralph Iteration**: 3/15

## Specification
[spec content]

## Completion Requirements

When you have GENUINELY completed this stage:

1. Ensure all requirements from the specification are implemented
2. Commit your changes with a descriptive message
3. Verify your implementation works correctly

Then output:

<promise>IMPLEMENTATION_COMPLETE</promise>

CRITICAL:
- Only output the promise when ALL requirements are truly met
- Your work will be verified - false promises are detected
- If blocked, explain what's preventing completion
- The loop will continue until genuine completion or max iterations
```

### Promise Tag Format

```xml
<promise>COMPLETION_TEXT</promise>
```

- Must be on its own line
- Text must match configured `completion_promise` exactly
- Case-sensitive matching

### State Persistence

Ralph loop state stored in task metadata:

```python
task.metadata["ralph"] = {
    "stage": "coder",
    "iteration": 3,
    "max_iterations": 15,
    "started_at": "2024-01-15T10:30:00Z",
    "completion_promise": "IMPLEMENTATION_COMPLETE",
}
```

### Execution Log Format

```json
{
  "task_id": "TASK-001",
  "stage": "coder",
  "ralph_iteration": 3,
  "ralph_max": 15,
  "promise_found": false,
  "continuing": true,
  "duration_ms": 45000
}
```

---

## Configuration Reference

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `ralph.enabled` | bool | true | Global enable/disable |
| `ralph.default_max_iterations` | int | 10 | Default iteration limit |
| `ralph.verify_promises` | bool | true | Enable promise verification |
| `ralph.<agent>.enabled` | bool | true | Per-agent enable/disable |
| `ralph.<agent>.max_iterations` | int | varies | Per-agent iteration limit |
| `ralph.<agent>.completion_promise` | str | varies | Per-agent completion text |

### Default Agent Settings

| Agent | Max Iterations | Completion Promise |
|-------|---------------|-------------------|
| coder | 15 | IMPLEMENTATION_COMPLETE |
| reviewer | 5 | REVIEW_COMPLETE |
| tester | 10 | TESTS_COMPLETE |
| qa | 5 | QA_PASSED |

---

## CLI Commands

### `specflow ralph-status`

Show status of active Ralph loops:

```bash
$ specflow ralph-status
Active Ralph Loops:
  TASK-001 (coder): iteration 3/15, started 5m ago
  TASK-002 (tester): iteration 7/10, started 12m ago
```

### `specflow ralph-cancel <task-id>`

Cancel an active Ralph loop:

```bash
$ specflow ralph-cancel TASK-001
Cancelled Ralph loop for TASK-001 at iteration 3/15
```

---

## TUI Integration

### Swimlane Board

Show Ralph iteration in task cards:

```
┌─────────────────────────────┐
│ TASK-001                    │
│ Implement authentication    │
│ ────────────────────────────│
│ 🔄 Coder (3/15)            │
└─────────────────────────────┘
```

### Agent Panel

Show Ralph status in agent slots:

```
┌─────────────────────────────────┐
│ Slot 1: coder                   │
│   Task: TASK-001                │
│   Ralph: iteration 3/15         │
│   Running: 5m 23s               │
└─────────────────────────────────┘
```

---

## Error Handling

### Max Iterations Reached

When max iterations reached without completion:

1. Log failure reason
2. Set task status to `todo` (for retry)
3. Store failure metadata:
   ```python
   task.metadata["ralph_failure"] = {
       "stage": "coder",
       "iterations_used": 15,
       "last_output": "...",
       "reason": "Max iterations reached without completion promise"
   }
   ```

### Invalid Promise Detected

When promise verification fails:

1. Log verification failure
2. Continue loop (don't trust the promise)
3. Store verification result for debugging

### Agent Timeout

When agent times out during Ralph loop:

1. Count as failed iteration
2. Continue loop if under max iterations
3. Include timeout in execution log

---

## Security Considerations

### Infinite Loop Prevention

- **Hard limit**: Always enforce `max_iterations`
- **Timeout**: Each iteration has execution timeout
- **Cost tracking**: Log API costs per iteration
- **Circuit breaker**: Stop if costs exceed threshold

### Promise Manipulation

- Verify promises with contradiction detection
- Stage-specific verification rules
- Log all promise attempts for audit

---

## Future Enhancements

1. **Adaptive Iterations** - Adjust max based on task complexity
2. **Learning from History** - Use past iterations to improve prompts
3. **Parallel Ralph Loops** - Run multiple loops concurrently
4. **Checkpoint/Resume** - Save state for long-running loops
5. **Cost Budgets** - Stop loops when cost threshold reached
