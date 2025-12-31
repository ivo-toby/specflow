"""Tests for execution pipeline."""

import json
import pytest
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, MagicMock

from specflow.core.database import Task, TaskStatus, Spec, SpecStatus
from specflow.core.project import Project
from specflow.orchestration.agent_pool import AgentPool, AgentType
from specflow.orchestration.execution import (
    ExecutionPipeline,
    PipelineStage,
    ExecutionResult,
    AGENT_TYPE_TO_NAME,
    AGENT_ALLOWED_TOOLS,
)


@pytest.fixture
def project(tmp_path):
    """Create a test project."""
    return Project.init(tmp_path)


@pytest.fixture
def agent_pool():
    """Create a test agent pool."""
    return AgentPool(max_agents=6)


@pytest.fixture
def pipeline(project, agent_pool):
    """Create a test execution pipeline."""
    return ExecutionPipeline(project, agent_pool)


@pytest.fixture
def sample_task(project):
    """Create a sample task."""
    # Create spec first (required for foreign key)
    from specflow.core.database import Spec, SpecStatus

    spec = Spec(
        id="spec-1",
        title="Test Spec",
        status=SpecStatus.APPROVED,
        source_type=None,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        metadata={},
    )
    project.db.create_spec(spec)

    task = Task(
        id="task-1",
        spec_id="spec-1",
        title="Test task",
        description="Test description",
        status=TaskStatus.TODO,
        priority=1,
        dependencies=[],
        assignee=None,
        worktree=None,
        metadata={},
        iteration=0,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    project.db.create_task(task)
    return task


def test_pipeline_creation(pipeline):
    """Test pipeline creation with default stages."""
    assert len(pipeline.pipeline) == 4
    assert pipeline.pipeline[0].name == "Implementation"
    assert pipeline.pipeline[1].name == "Code Review"
    assert pipeline.pipeline[2].name == "Testing"
    assert pipeline.pipeline[3].name == "QA Validation"


def test_pipeline_stage():
    """Test pipeline stage creation."""
    stage = PipelineStage("Test Stage", AgentType.CODER, max_iterations=3)

    assert stage.name == "Test Stage"
    assert stage.agent_type == AgentType.CODER
    assert stage.max_iterations == 3


def test_execution_result():
    """Test execution result."""
    result = ExecutionResult(
        success=True, iteration=1, output="Test output", duration_ms=1000, issues=[]
    )

    assert result.success is True
    assert result.iteration == 1
    assert result.output == "Test output"
    assert result.duration_ms == 1000
    assert result.issues == []


def test_get_stage_status(pipeline):
    """Test getting task status for agent type."""
    assert pipeline._get_stage_status(AgentType.CODER) == TaskStatus.IMPLEMENTING
    assert pipeline._get_stage_status(AgentType.REVIEWER) == TaskStatus.REVIEWING
    assert pipeline._get_stage_status(AgentType.TESTER) == TaskStatus.TESTING
    assert pipeline._get_stage_status(AgentType.QA) == TaskStatus.REVIEWING


def test_check_stage_success(pipeline):
    """Test checking stage success from output."""
    # Success indicators
    assert pipeline._check_stage_success(None, "Status: Success") is True
    assert pipeline._check_stage_success(None, "PASS") is True

    # Failure
    assert pipeline._check_stage_success(None, "Failed") is False


def test_extract_issues(pipeline):
    """Test extracting issues from output."""
    output = """
    Normal line
    ERROR: Something went wrong
    Another line
    FAIL: Test failed
    Issue: Found a problem
    """

    issues = pipeline._extract_issues(output)
    assert len(issues) == 3
    assert any("ERROR:" in issue for issue in issues)
    assert any("FAIL:" in issue for issue in issues)
    assert any("Issue:" in issue for issue in issues)


def test_extract_issues_none(pipeline):
    """Test extracting issues from clean output."""
    output = "Everything is fine\nNo problems here"

    issues = pipeline._extract_issues(output)
    assert len(issues) == 0


def test_get_pipeline_info(pipeline):
    """Test getting pipeline information."""
    info = pipeline.get_pipeline_info()

    assert "stages" in info
    assert "max_total_iterations" in info
    assert len(info["stages"]) == 4
    assert info["max_total_iterations"] == 10

    # Check first stage
    first_stage = info["stages"][0]
    assert first_stage["name"] == "Implementation"
    assert first_stage["agent_type"] == "coder"
    assert first_stage["max_iterations"] == 3


def test_default_pipeline_stages(pipeline):
    """Test default pipeline stage configuration."""
    stages = pipeline.pipeline

    # Check stage names
    assert stages[0].name == "Implementation"
    assert stages[1].name == "Code Review"
    assert stages[2].name == "Testing"
    assert stages[3].name == "QA Validation"

    # Check agent types
    assert stages[0].agent_type == AgentType.CODER
    assert stages[1].agent_type == AgentType.REVIEWER
    assert stages[2].agent_type == AgentType.TESTER
    assert stages[3].agent_type == AgentType.QA

    # Check iteration limits
    assert stages[0].max_iterations == 3
    assert stages[1].max_iterations == 2
    assert stages[2].max_iterations == 2
    assert stages[3].max_iterations == 10


def test_max_total_iterations(pipeline):
    """Test maximum total iterations limit."""
    assert pipeline.max_total_iterations == 10


def test_pipeline_project_integration(pipeline, project):
    """Test pipeline integration with project."""
    assert pipeline.project == project
    assert isinstance(pipeline.agent_pool, AgentPool)


def test_custom_pipeline():
    """Test creating custom pipeline stages."""
    custom_stages = [
        PipelineStage("Custom Stage 1", AgentType.CODER, max_iterations=5),
        PipelineStage("Custom Stage 2", AgentType.REVIEWER, max_iterations=1),
    ]

    assert len(custom_stages) == 2
    assert custom_stages[0].max_iterations == 5
    assert custom_stages[1].max_iterations == 1


def test_execution_result_with_issues():
    """Test execution result with issues."""
    issues = ["Issue 1", "Issue 2", "Issue 3"]
    result = ExecutionResult(
        success=False, iteration=2, output="Failed", duration_ms=500, issues=issues
    )

    assert result.success is False
    assert len(result.issues) == 3
    assert "Issue 1" in result.issues


def test_execution_result_with_session_id():
    """Test execution result with session ID."""
    result = ExecutionResult(
        success=True,
        iteration=1,
        output="Done",
        duration_ms=100,
        issues=[],
        session_id="session-123",
    )

    assert result.session_id == "session-123"


class TestAgentConstants:
    """Tests for agent type constants."""

    def test_agent_type_to_name(self):
        """Test agent type to name mapping."""
        assert AGENT_TYPE_TO_NAME[AgentType.ARCHITECT] == "specflow-architect"
        assert AGENT_TYPE_TO_NAME[AgentType.CODER] == "specflow-coder"
        assert AGENT_TYPE_TO_NAME[AgentType.REVIEWER] == "specflow-reviewer"
        assert AGENT_TYPE_TO_NAME[AgentType.TESTER] == "specflow-tester"
        assert AGENT_TYPE_TO_NAME[AgentType.QA] == "specflow-qa"

    def test_agent_allowed_tools(self):
        """Test agent allowed tools mapping."""
        assert "Read" in AGENT_ALLOWED_TOOLS[AgentType.CODER]
        assert "Write" in AGENT_ALLOWED_TOOLS[AgentType.CODER]
        assert "Bash" in AGENT_ALLOWED_TOOLS[AgentType.CODER]
        assert "Task" in AGENT_ALLOWED_TOOLS[AgentType.CODER]

        assert "Write" not in AGENT_ALLOWED_TOOLS[AgentType.REVIEWER]
        assert "Read" in AGENT_ALLOWED_TOOLS[AgentType.REVIEWER]


class TestReadFile:
    """Tests for _read_file method."""

    def test_read_existing_file(self, pipeline, tmp_path):
        """Test reading an existing file."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test Content")

        content = pipeline._read_file(test_file)
        assert content == "# Test Content"

    def test_read_nonexistent_file(self, pipeline, tmp_path):
        """Test reading a non-existent file."""
        content = pipeline._read_file(tmp_path / "nonexistent.md")
        assert content is None


class TestBuildAgentPrompt:
    """Tests for _build_agent_prompt method."""

    def test_build_coder_prompt(self, pipeline, sample_task):
        """Test building prompt for coder agent."""
        stage = PipelineStage("Implementation", AgentType.CODER, max_iterations=3)
        worktree_path = Path("/tmp/test-worktree")

        prompt = pipeline._build_agent_prompt(sample_task, stage, worktree_path, 1)

        assert "specflow-coder" in prompt
        assert sample_task.id in prompt
        assert sample_task.title in prompt
        assert "IMPLEMENTATION COMPLETE" in prompt
        assert "BLOCKED:" in prompt

    def test_build_reviewer_prompt(self, pipeline, sample_task):
        """Test building prompt for reviewer agent."""
        stage = PipelineStage("Code Review", AgentType.REVIEWER, max_iterations=2)
        worktree_path = Path("/tmp/test-worktree")

        prompt = pipeline._build_agent_prompt(sample_task, stage, worktree_path, 1)

        assert "specflow-reviewer" in prompt
        assert "REVIEW PASSED" in prompt
        assert "REVIEW FAILED" in prompt

    def test_build_tester_prompt(self, pipeline, sample_task):
        """Test building prompt for tester agent."""
        stage = PipelineStage("Testing", AgentType.TESTER, max_iterations=2)
        worktree_path = Path("/tmp/test-worktree")

        prompt = pipeline._build_agent_prompt(sample_task, stage, worktree_path, 1)

        assert "specflow-tester" in prompt
        assert "TESTS PASSED" in prompt
        assert "TESTS FAILED" in prompt

    def test_build_qa_prompt(self, pipeline, sample_task):
        """Test building prompt for QA agent."""
        stage = PipelineStage("QA Validation", AgentType.QA, max_iterations=10)
        worktree_path = Path("/tmp/test-worktree")

        prompt = pipeline._build_agent_prompt(sample_task, stage, worktree_path, 1)

        assert "specflow-qa" in prompt
        assert "QA PASSED" in prompt
        assert "QA FAILED" in prompt

    def test_prompt_includes_followup_instructions(self, pipeline, sample_task):
        """Test that prompt includes follow-up task instructions."""
        stage = PipelineStage("Implementation", AgentType.CODER, max_iterations=3)
        worktree_path = Path("/tmp/test-worktree")

        prompt = pipeline._build_agent_prompt(sample_task, stage, worktree_path, 1)

        assert "specflow task-followup" in prompt
        assert "PLACEHOLDER-" in prompt
        assert "TECH-DEBT-" in prompt
        assert "specflow list-tasks" in prompt


class TestRunClaudeHeadless:
    """Tests for _run_claude_headless method."""

    def test_run_success(self, pipeline):
        """Test successful Claude execution."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"result": "IMPLEMENTATION COMPLETE", "session_id": "sess-123"})
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            output, session_id, success = pipeline._run_claude_headless(
                prompt="Test prompt",
                working_dir=Path("/tmp"),
                allowed_tools="Read,Write",
                agent_type=AgentType.CODER,
            )

            assert success is True
            assert "IMPLEMENTATION COMPLETE" in output
            assert session_id == "sess-123"
            mock_run.assert_called_once()

    def test_run_with_model(self, pipeline):
        """Test Claude execution with model parameter."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Done"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            pipeline._run_claude_headless(
                prompt="Test",
                working_dir=Path("/tmp"),
                allowed_tools="Read",
                agent_type=AgentType.CODER,
                model="opus",
            )

            call_args = mock_run.call_args[0][0]
            assert "--model" in call_args
            assert "opus" in call_args

    def test_run_failure(self, pipeline):
        """Test failed Claude execution."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = "Error occurred"
        mock_result.stderr = "Something went wrong"

        with patch("subprocess.run", return_value=mock_result):
            output, session_id, success = pipeline._run_claude_headless(
                prompt="Test",
                working_dir=Path("/tmp"),
                allowed_tools="Read",
                agent_type=AgentType.CODER,
            )

            assert success is False
            assert "Something went wrong" in output

    def test_run_timeout(self, pipeline):
        """Test Claude execution timeout."""
        import subprocess

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("claude", 600)):
            output, session_id, success = pipeline._run_claude_headless(
                prompt="Test",
                working_dir=Path("/tmp"),
                allowed_tools="Read",
                agent_type=AgentType.CODER,
            )

            assert success is False
            assert "TIMEOUT" in output
            assert session_id is None

    def test_run_claude_not_found(self, pipeline):
        """Test Claude CLI not found."""
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            output, session_id, success = pipeline._run_claude_headless(
                prompt="Test",
                working_dir=Path("/tmp"),
                allowed_tools="Read",
                agent_type=AgentType.CODER,
            )

            assert success is False
            assert "not found" in output
            assert session_id is None

    def test_run_non_json_output(self, pipeline):
        """Test handling of non-JSON output from Claude."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Plain text output without JSON"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            output, session_id, success = pipeline._run_claude_headless(
                prompt="Test",
                working_dir=Path("/tmp"),
                allowed_tools="Read",
                agent_type=AgentType.CODER,
            )

            assert success is True
            assert output == "Plain text output without JSON"
            assert session_id is None


class TestExtractMemories:
    """Tests for _extract_memories method."""

    def test_extract_memories_called(self, pipeline, sample_task):
        """Test that memory extraction is called with correct parameters."""
        stage = PipelineStage("Implementation", AgentType.CODER)
        output = "Some output with decisions and patterns"

        with patch.object(pipeline.project.memory, "extract_from_text") as mock_extract:
            pipeline._extract_memories(sample_task, stage, output)

            mock_extract.assert_called_once()
            call_kwargs = mock_extract.call_args[1]
            assert call_kwargs["text"] == output
            assert "coder:" in call_kwargs["source"]
            assert sample_task.id in call_kwargs["source"]
            assert call_kwargs["spec_id"] == sample_task.spec_id


class TestExecuteStage:
    """Tests for _execute_stage method."""

    def test_execute_stage_success(self, pipeline, sample_task):
        """Test successful stage execution."""
        stage = PipelineStage("Implementation", AgentType.CODER, max_iterations=3)
        worktree_path = Path("/tmp/test-worktree")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"result": "IMPLEMENTATION COMPLETE"})
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = pipeline._execute_stage(sample_task, stage, worktree_path, 1)

            assert result.success is True
            assert result.iteration == 1
            assert len(result.issues) == 0

    def test_execute_stage_failure(self, pipeline, sample_task):
        """Test failed stage execution."""
        stage = PipelineStage("Code Review", AgentType.REVIEWER, max_iterations=2)
        worktree_path = Path("/tmp/test-worktree")

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = "REVIEW FAILED: Code quality issues"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = pipeline._execute_stage(sample_task, stage, worktree_path, 1)

            assert result.success is False
            assert len(result.issues) > 0


class TestExecuteTask:
    """Tests for execute_task method."""

    def test_execute_task_all_stages_pass(self, pipeline, sample_task, tmp_path):
        """Test executing a task where all stages pass."""
        worktree_path = tmp_path / "worktree"
        worktree_path.mkdir()

        # Create a mock that returns success for all stages
        def mock_run(*args, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stdout = json.dumps({"result": "PASS"})
            result.stderr = ""
            return result

        with patch("subprocess.run", side_effect=mock_run):
            success = pipeline.execute_task(sample_task, worktree_path)

        assert success is True
        # Verify task was updated to DONE
        task = pipeline.project.db.get_task(sample_task.id)
        assert task.status == TaskStatus.DONE

    def test_execute_task_stage_fails(self, pipeline, sample_task, tmp_path):
        """Test executing a task where a stage fails."""
        worktree_path = tmp_path / "worktree"
        worktree_path.mkdir()

        # Create a mock that always fails
        def mock_run(*args, **kwargs):
            result = MagicMock()
            result.returncode = 1
            result.stdout = "BLOCKED: Cannot proceed"
            result.stderr = ""
            return result

        with patch("subprocess.run", side_effect=mock_run):
            success = pipeline.execute_task(sample_task, worktree_path)

        assert success is False
        # Verify task was reset to TODO
        task = pipeline.project.db.get_task(sample_task.id)
        assert task.status == TaskStatus.TODO
        assert "failure_stage" in task.metadata

    def test_execute_task_registers_agent(self, pipeline, sample_task, tmp_path):
        """Test that agents are registered during execution."""
        worktree_path = tmp_path / "worktree"
        worktree_path.mkdir()

        # Track register/deregister calls
        register_calls = []
        deregister_calls = []

        original_register = pipeline.project.db.register_agent
        original_deregister = pipeline.project.db.deregister_agent

        def mock_register(*args, **kwargs):
            register_calls.append(kwargs)
            return original_register(*args, **kwargs)

        def mock_deregister(*args, **kwargs):
            deregister_calls.append(kwargs)
            return original_deregister(*args, **kwargs)

        pipeline.project.db.register_agent = mock_register
        pipeline.project.db.deregister_agent = mock_deregister

        # Make all stages pass quickly
        def mock_run(*args, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stdout = "PASS"
            result.stderr = ""
            return result

        with patch("subprocess.run", side_effect=mock_run):
            pipeline.execute_task(sample_task, worktree_path)

        # Each stage should register and deregister
        assert len(register_calls) == 4  # 4 stages
        assert len(deregister_calls) == 4

    def test_execute_task_logs_execution(self, pipeline, sample_task, tmp_path):
        """Test that execution is logged."""
        worktree_path = tmp_path / "worktree"
        worktree_path.mkdir()

        def mock_run(*args, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stdout = "PASS"
            result.stderr = ""
            return result

        with patch("subprocess.run", side_effect=mock_run):
            pipeline.execute_task(sample_task, worktree_path)

        # Check execution logs were created
        logs = pipeline.project.db.get_execution_logs(sample_task.id)
        assert len(logs) == 4  # One for each stage


class TestCheckStageSuccess:
    """Additional tests for _check_stage_success."""

    def test_success_indicators(self, pipeline):
        """Test all success indicators."""
        success_outputs = [
            "IMPLEMENTATION COMPLETE",
            "REVIEW PASSED",
            "TESTS PASSED",
            "QA PASSED",
            "Status: Success",
        ]

        for output in success_outputs:
            assert pipeline._check_stage_success(None, output) is True, f"Failed for: {output}"

    def test_failure_indicators(self, pipeline):
        """Test all failure indicators."""
        failure_outputs = [
            "BLOCKED: Something",
            "REVIEW FAILED: Issues",
            "TESTS FAILED",
            "QA FAILED",
            "ERROR: Something",
            "TIMEOUT: Exceeded",
        ]

        for output in failure_outputs:
            assert pipeline._check_stage_success(None, output) is False, f"Failed for: {output}"

    def test_ambiguous_output_substantial(self, pipeline):
        """Test that substantial output without errors is considered success."""
        output = "x" * 200  # More than 100 chars, no 'error' word
        assert pipeline._check_stage_success(None, output) is True

    def test_ambiguous_output_with_error(self, pipeline):
        """Test that output with 'error' word is considered failure."""
        output = "x" * 200 + " error occurred"
        assert pipeline._check_stage_success(None, output) is False

    def test_short_ambiguous_output(self, pipeline):
        """Test that short output without indicators is considered failure."""
        output = "short"
        assert pipeline._check_stage_success(None, output) is False
