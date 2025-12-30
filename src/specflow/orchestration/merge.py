"""Merge orchestrator with 3-tier conflict resolution."""

import json
import os
import subprocess
from pathlib import Path

from git import Repo


class MergeStrategy:
    """Base class for merge strategies."""

    def merge(self, repo: Repo, source_branch: str, target_branch: str) -> tuple[bool, str]:
        """
        Attempt to merge source branch into target.

        Returns:
            (success, message) tuple
        """
        raise NotImplementedError


class GitAutoMerge(MergeStrategy):
    """Tier 1: Automatic Git merge (no conflicts)."""

    def merge(self, repo: Repo, source_branch: str, target_branch: str) -> tuple[bool, str]:
        """Attempt automatic git merge."""
        try:
            # Checkout target branch
            repo.git.checkout(target_branch)

            # Attempt merge
            repo.git.merge(source_branch, "--no-ff", "-m", f"Merge {source_branch} into {target_branch}")

            return True, f"Successfully merged {source_branch} into {target_branch}"

        except Exception as e:
            error_msg = str(e)
            if "CONFLICT" in error_msg or "conflict" in error_msg:
                # Abort the merge
                try:
                    repo.git.merge("--abort")
                except Exception:
                    pass
                return False, f"Merge conflicts detected: {error_msg}"
            else:
                return False, f"Merge failed: {error_msg}"


class ConflictOnlyAIMerge(MergeStrategy):
    """Tier 2: AI resolves only conflicted sections."""

    def __init__(self, claude_path: str = "claude", timeout: int = 300):
        """Initialize with Claude Code configuration.

        Args:
            claude_path: Path to claude CLI (default: "claude")
            timeout: Timeout in seconds for AI resolution (default: 300)
        """
        self.claude_path = claude_path
        self.timeout = timeout

    def merge(self, repo: Repo, source_branch: str, target_branch: str) -> tuple[bool, str]:
        """Resolve conflicts using AI on conflicted sections only."""
        # Checkout target branch
        try:
            repo.git.checkout(target_branch)
        except Exception as e:
            return False, f"Failed to checkout {target_branch}: {e}"

        # Attempt merge (will fail with conflicts)
        try:
            repo.git.merge(source_branch, "--no-ff")
            return True, "No conflicts (unexpected in tier 2)"
        except Exception:
            pass  # Expected to fail with conflicts

        # Get list of conflicted files
        try:
            status = repo.git.status("--porcelain")
            conflicted_files = []
            for line in status.split("\n"):
                if line.startswith("UU "):  # Both modified (conflict)
                    conflicted_files.append(line[3:].strip())
        except Exception as e:
            repo.git.merge("--abort")
            return False, f"Failed to get conflict status: {e}"

        if not conflicted_files:
            # No conflicts, complete merge
            try:
                repo.git.commit("-m", f"Merge {source_branch} into {target_branch}")
                return True, "Merged successfully (no conflicts)"
            except Exception as e:
                repo.git.merge("--abort")
                return False, f"Failed to commit: {e}"

        # Resolve each conflicted file using AI
        working_dir = Path(repo.working_dir)
        resolved_count = 0
        failed_files = []

        for file_path in conflicted_files:
            full_path = working_dir / file_path
            success, error = self._resolve_file_conflicts(full_path, source_branch, target_branch)

            if success:
                # Stage the resolved file
                try:
                    repo.git.add(file_path)
                    resolved_count += 1
                except Exception as e:
                    failed_files.append(f"{file_path}: Failed to stage - {e}")
            else:
                failed_files.append(f"{file_path}: {error}")

        # If any files failed to resolve, abort
        if failed_files:
            try:
                repo.git.merge("--abort")
            except Exception:
                pass
            return False, f"AI resolution failed for {len(failed_files)} file(s): {'; '.join(failed_files[:3])}"

        # Complete the merge
        try:
            repo.git.commit("-m", f"Merge {source_branch} into {target_branch} (AI-resolved conflicts)")
            return True, f"AI resolved conflicts in {resolved_count} file(s)"
        except Exception as e:
            try:
                repo.git.merge("--abort")
            except Exception:
                pass
            return False, f"Failed to commit after resolution: {e}"

    def _resolve_file_conflicts(self, file_path: Path, source_branch: str, target_branch: str) -> tuple[bool, str]:
        """Resolve conflicts in a single file using Claude Code.

        Args:
            file_path: Path to the conflicted file
            source_branch: Name of source branch
            target_branch: Name of target branch

        Returns:
            (success, error_message) tuple
        """
        # Read the conflicted file content
        try:
            conflicted_content = file_path.read_text()
        except Exception as e:
            return False, f"Failed to read file: {e}"

        # Check if file actually has conflict markers
        if "<<<<<<< HEAD" not in conflicted_content:
            return True, "No conflict markers found"

        # Build prompt for Claude
        prompt = f"""You are resolving a git merge conflict. The file below contains conflict markers.

FILE: {file_path.name}
SOURCE BRANCH: {source_branch} (the incoming changes)
TARGET BRANCH: {target_branch} (HEAD, the current branch)

CONFLICT MARKERS EXPLAINED:
- `<<<<<<< HEAD` marks the start of the TARGET branch version
- `=======` separates the two versions
- `>>>>>>> {source_branch}` marks the end of the SOURCE branch version

YOUR TASK:
1. Analyze each conflict section
2. Decide how to merge the changes (keep one side, combine both, or create a new version)
3. Output ONLY the fully resolved file content with NO conflict markers
4. Do NOT include any explanation - output ONLY the resolved file content

CONFLICTED FILE CONTENT:
```
{conflicted_content}
```

OUTPUT the resolved file content below (no markdown code blocks, no explanations):"""

        # Run Claude to resolve
        resolved_content, error = self._run_claude_resolution(prompt, file_path.parent)

        if error:
            return False, error

        # Validate resolution (no conflict markers should remain)
        if "<<<<<<< " in resolved_content or "=======" in resolved_content or ">>>>>>> " in resolved_content:
            return False, "AI output still contains conflict markers"

        # Write resolved content
        try:
            file_path.write_text(resolved_content)
            return True, ""
        except Exception as e:
            return False, f"Failed to write resolved file: {e}"

    def _run_claude_resolution(self, prompt: str, working_dir: Path) -> tuple[str | None, str | None]:
        """Run Claude Code to resolve conflicts.

        Args:
            prompt: The prompt for conflict resolution
            working_dir: Working directory for Claude

        Returns:
            (resolved_content, error) tuple - one will be None
        """
        cmd = [
            self.claude_path,
            "-p", prompt,
            "--output-format", "json",
            "--allowedTools", "",  # No tools needed, just text output
        ]

        try:
            result = subprocess.run(
                cmd,
                cwd=working_dir,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env=os.environ.copy(),
            )

            if result.returncode != 0:
                return None, f"Claude returned error: {result.stderr or result.stdout}"

            # Parse JSON output
            output = result.stdout
            try:
                json_output = json.loads(output)
                resolved = json_output.get("result", output)
            except json.JSONDecodeError:
                # Not JSON, use raw output
                resolved = output

            # Clean up the output (remove any markdown code blocks if present)
            resolved = resolved.strip()
            if resolved.startswith("```") and resolved.endswith("```"):
                # Remove code block markers
                lines = resolved.split("\n")
                if len(lines) > 2:
                    resolved = "\n".join(lines[1:-1])

            return resolved, None

        except subprocess.TimeoutExpired:
            return None, f"AI resolution timed out after {self.timeout}s"
        except FileNotFoundError:
            return None, f"Claude CLI not found at '{self.claude_path}'"
        except Exception as e:
            return None, f"Failed to run Claude: {e}"


class FullFileAIMerge(MergeStrategy):
    """Tier 3: AI regenerates entire conflicted files."""

    def merge(self, repo: Repo, source_branch: str, target_branch: str) -> tuple[bool, str]:
        """Use AI to regenerate conflicted files from scratch."""
        # Placeholder implementation
        # In real implementation:
        # 1. Get list of all changed files
        # 2. For each conflicted file, provide both versions to AI
        # 3. Ask AI to generate a merged version
        # 4. Replace file with AI-generated version
        # 5. Commit the merge

        return False, "AI file regeneration not yet implemented"


class MergeOrchestrator:
    """Orchestrates merge operations with 3-tier strategy."""

    def __init__(self, repo_path: Path, claude_path: str = "claude", timeout: int = 300):
        """Initialize merge orchestrator.

        Args:
            repo_path: Path to the git repository
            claude_path: Path to claude CLI (default: "claude")
            timeout: Timeout in seconds for AI operations (default: 300)
        """
        self.repo = Repo(repo_path)
        self.claude_path = claude_path
        self.timeout = timeout
        self.strategies = [
            ("Auto-merge", GitAutoMerge()),
            ("AI conflict resolution", ConflictOnlyAIMerge(claude_path, timeout)),
            ("AI file regeneration", FullFileAIMerge()),
        ]

    def merge_task(self, task_id: str, target_branch: str = "main") -> tuple[bool, str]:
        """
        Merge a task branch into target using 3-tier strategy.

        Args:
            task_id: Task ID (branch will be task/{task_id})
            target_branch: Target branch to merge into

        Returns:
            (success, message) tuple
        """
        source_branch = f"task/{task_id}"

        # Verify source branch exists
        try:
            self.repo.git.rev_parse("--verify", source_branch)
        except Exception:
            return False, f"Source branch not found: {source_branch}"

        # Try each strategy in order
        for strategy_name, strategy in self.strategies:
            success, message = strategy.merge(self.repo, source_branch, target_branch)

            if success:
                return True, f"✓ Merged using {strategy_name}: {message}"

            # If this strategy failed, try next one
            # (unless it's the last strategy)
            if strategy == self.strategies[-1][1]:
                return False, f"✗ All merge strategies failed. Last error: {message}"

        return False, "No merge strategies available"

    def cleanup_branch(self, task_id: str) -> bool:
        """
        Delete a task branch after successful merge.

        Args:
            task_id: Task ID

        Returns:
            True if deleted successfully
        """
        branch_name = f"task/{task_id}"

        try:
            self.repo.git.branch("-D", branch_name)
            return True
        except Exception:
            return False

    def get_merge_status(self) -> dict[str, any]:
        """Get current merge status."""
        try:
            # Check if merge is in progress
            merge_head_path = Path(self.repo.working_dir) / ".git" / "MERGE_HEAD"
            in_progress = merge_head_path.exists()

            return {
                "in_progress": in_progress,
                "current_branch": self.repo.active_branch.name,
                "strategies_available": [name for name, _ in self.strategies],
            }
        except Exception as e:
            return {"error": str(e)}
