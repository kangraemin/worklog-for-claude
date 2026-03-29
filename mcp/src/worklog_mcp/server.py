from mcp.server.fastmcp import FastMCP
from worklog_mcp.tools.worklog import write_worklog, read_worklog
from worklog_mcp.tools.project_doc import (
    read_project_doc,
    create_project_doc,
    analyze_gaps,
    update_project_doc,
)
from worklog_mcp.tools.notion import write_worklog_to_notion
from worklog_mcp.utils.git import get_commits_since_file_update


def get_commits_since_update(project_path: str = ".") -> int:
    """PROJECT.md 마지막 수정 이후 커밋 수 반환. hook에서 빠르게 호출하는 용도.

    Args:
        project_path: 프로젝트 루트 디렉토리 경로 (기본값: 현재 디렉토리)
    """
    return get_commits_since_file_update(project_path, "PROJECT.md")


mcp = FastMCP("worklog-mcp")

mcp.tool()(write_worklog)
mcp.tool()(read_worklog)
mcp.tool()(read_project_doc)
mcp.tool()(create_project_doc)
mcp.tool()(analyze_gaps)
mcp.tool()(update_project_doc)
mcp.tool()(write_worklog_to_notion)
mcp.tool()(get_commits_since_update)


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
