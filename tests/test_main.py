"""核心功能测试"""
import pytest
from sql_assistant_agent.main import (
    _is_readonly_sql,
    _is_retryable_review_failure,
    _review_answer_satisfaction,
    _safe_upload_filename,
    _summarize_query_result,
)


class TestIsReadonlySql:
    """测试SQL只读检查函数"""

    def test_select_query(self):
        assert _is_readonly_sql("SELECT * FROM users") is True

    def test_show_databases(self):
        assert _is_readonly_sql("SHOW DATABASES") is True

    def test_describe_table(self):
        assert _is_readonly_sql("DESCRIBE users") is True

    def test_explain_query(self):
        assert _is_readonly_sql("EXPLAIN SELECT * FROM users") is True

    def test_with_query(self):
        assert _is_readonly_sql("WITH cte AS (SELECT 1) SELECT * FROM cte") is True

    def test_insert_blocked(self):
        assert _is_readonly_sql("INSERT INTO users VALUES (1)") is False

    def test_update_blocked(self):
        assert _is_readonly_sql("UPDATE users SET name='test'") is False

    def test_delete_blocked(self):
        assert _is_readonly_sql("DELETE FROM users") is False

    def test_drop_blocked(self):
        assert _is_readonly_sql("DROP TABLE users") is False

    def test_semicolon_blocked(self):
        assert _is_readonly_sql("SELECT 1; DROP TABLE users") is False

    def test_injection_blocked(self):
        assert _is_readonly_sql("SELECT 1; DELETE FROM users") is False

    def test_union_injection(self):
        # UNION注入仍然以SELECT开头，但包含分号会被拦截
        assert _is_readonly_sql("SELECT 1 UNION SELECT 2") is True

    def test_empty_string(self):
        assert _is_readonly_sql("") is False

    def test_whitespace_only(self):
        assert _is_readonly_sql("   ") is False


class TestSafeUploadFilename:
    """测试文件名安全处理"""

    def test_normal_filename(self):
        assert _safe_upload_filename("skills.md") == "skills.md"

    def test_path_traversal(self):
        result = _safe_upload_filename("../../etc/passwd.md")
        assert ".." not in result
        assert "/" not in result

    def test_special_characters(self):
        result = _safe_upload_filename("my skills (1).md")
        assert " " not in result
        assert "(" not in result

    def test_empty_filename(self):
        assert _safe_upload_filename("") == "skills.md"

    def test_none_filename(self):
        assert _safe_upload_filename(None) == "skills.md"

    def test_long_filename(self):
        long_name = "a" * 200 + ".md"
        result = _safe_upload_filename(long_name)
        assert len(result) <= 120


class TestAnswerReviewHelpers:
    """测试答案自检辅助函数"""

    def test_summarize_query_result(self):
        summary = _summarize_query_result(
            data=[{"name": "张三"}, {"name": "李四"}],
            columns=["name"],
            error="",
            truncated=False,
        )

        assert '"row_count": 2' in summary
        assert '"columns": ["name"]' in summary
        assert "张三" in summary

    def test_review_fails_on_execution_error(self):
        review = _review_answer_satisfaction(
            user_message="查询老师",
            sql_query="SELECT name FROM teachers",
            answer="查询执行失败",
            data=[],
            columns=[],
            error="Unknown column 'name'",
            truncated=False,
        )

        assert review["passed"] is False
        assert "SQL 执行失败" in review["feedback"]

    def test_review_fails_without_sql(self):
        review = _review_answer_satisfaction(
            user_message="查询老师",
            sql_query="",
            answer="未获取到助手回复。",
            data=[],
            columns=[],
            error="",
            truncated=False,
        )

        assert review["passed"] is False
        assert "没有生成可执行 SQL" in review["feedback"]

    def test_retryable_review_failure(self):
        assert _is_retryable_review_failure("", "") is True
        assert _is_retryable_review_failure("SELECT bad_col FROM t", "Unknown column") is True
        assert _is_retryable_review_failure("SELECT 1", "") is True
        assert _is_retryable_review_failure("SELECT 1", "数据库未连接") is False
        assert _is_retryable_review_failure("SELECT 1", "获取数据库连接失败") is False
