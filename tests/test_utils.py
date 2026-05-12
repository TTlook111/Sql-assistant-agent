"""工具函数测试"""
import pytest
from sql_assistant_agent.main import _contains_chinese, _is_data_catalog_question


class TestContainsChinese:
    """测试中文检测"""

    def test_chinese_text(self):
        assert _contains_chinese("你好世界") is True

    def test_english_text(self):
        assert _contains_chinese("hello world") is False

    def test_mixed_text(self):
        assert _contains_chinese("hello 你好") is True

    def test_empty_string(self):
        assert _contains_chinese("") is False

    def test_none(self):
        assert _contains_chinese(None) is False


class TestIsDataCatalogQuestion:
    """测试数据目录问题检测"""

    def test_can_query_data(self):
        assert _is_data_catalog_question("可以查询哪些数据") is True

    def test_what_data(self):
        assert _is_data_catalog_question("有哪些数据可以查") is True

    def test_normal_query(self):
        assert _is_data_catalog_question("查询所有用户") is False

    def test_empty_message(self):
        assert _is_data_catalog_question("") is False
