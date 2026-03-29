"""TC-06 ~ TC-10: 서버 기동 검증"""
import inspect
from worklog_mcp.server import mcp
from worklog_mcp.tools.worklog import write_worklog, read_worklog
from worklog_mcp.tools.project_doc import (
    read_project_doc, create_project_doc, analyze_gaps, update_project_doc
)
from worklog_mcp.tools.notion import write_worklog_to_notion
from worklog_mcp.server import get_commits_since_update

EXPECTED_TOOLS = {
    "write_worklog", "read_worklog",
    "read_project_doc", "create_project_doc",
    "analyze_gaps", "update_project_doc",
    "write_worklog_to_notion", "get_commits_since_update",
}


def test_tc06_fastmcp_instance():
    """TC-06: FastMCP 인스턴스 생성 가능"""
    from mcp.server.fastmcp import FastMCP
    assert isinstance(mcp, FastMCP)


def test_tc07_tool_count():
    """TC-07: 서버에 8개 tool 등록됨"""
    tools = mcp._tool_manager.list_tools()
    assert len(tools) == 8, f"Expected 8 tools, got {len(tools)}: {[t.name for t in tools]}"


def test_tc08_tool_names():
    """TC-08: tool 이름 목록 정확"""
    tools = mcp._tool_manager.list_tools()
    names = {t.name for t in tools}
    assert names == EXPECTED_TOOLS, f"Tool names mismatch: {names}"


def test_tc09_tools_have_docstrings():
    """TC-09: 각 tool에 docstring 존재"""
    for fn in [write_worklog, read_worklog, read_project_doc,
               create_project_doc, analyze_gaps, update_project_doc,
               write_worklog_to_notion, get_commits_since_update]:
        assert fn.__doc__, f"{fn.__name__} has no docstring"


def test_tc10_tools_have_type_hints():
    """TC-10: 각 tool 인자에 type hint 존재"""
    for fn in [write_worklog, read_worklog, read_project_doc,
               create_project_doc, analyze_gaps, update_project_doc,
               write_worklog_to_notion, get_commits_since_update]:
        hints = fn.__annotations__
        sig = inspect.signature(fn)
        for param_name, param in sig.parameters.items():
            assert param.annotation != inspect.Parameter.empty, \
                f"{fn.__name__}.{param_name} has no type hint"
