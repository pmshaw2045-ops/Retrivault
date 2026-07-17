"""测试配置加载器"""
import pytest
from pydantic import ValidationError

from config.config_schema import LLMConfig, RAGConfig, SearchConfig
from src.config_loader import AppConfig


class TestAppConfig:
    """测试 AppConfig 默认值和校验"""

    def test_default_values(self):
        """默认值合理性"""
        cfg = AppConfig()
        assert cfg.rag.chunk_size == 512
        assert cfg.rag.top_k == 5
        assert cfg.llm.temperature == 0.3

    def test_custom_values(self):
        """自定义字段覆盖"""
        cfg = AppConfig(
            rag=RAGConfig(chunk_size=256),
            llm=LLMConfig(model="gpt-4o"),
        )
        assert cfg.rag.chunk_size == 256
        assert cfg.llm.model == "gpt-4o"

    def test_validation(self):
        """非法值应该被拒绝或修正"""
        with pytest.raises((ValueError, ValidationError)):
            AppConfig(rag=RAGConfig(chunk_size=50))

        cfg = AppConfig(llm=LLMConfig(model="test", temperature=5.0))
        assert cfg.llm.temperature == 2.0
        cfg2 = AppConfig(llm=LLMConfig(model="test", temperature=-1.0))
        assert cfg2.llm.temperature == 0.0

    def test_search_mode_enum(self):
        """搜索模式只能是 vector 或 hybrid"""
        cfg = AppConfig(search=SearchConfig(mode="vector"))
        assert cfg.search.mode == "vector"

        with pytest.raises((ValueError, ValidationError)):
            SearchConfig(mode="invalid")


class TestMergeConfigs:
    """测试配置合并逻辑"""

    def test_shallow_merge(self):
        """浅层合并：后面的覆盖前面的"""
        from src.config_loader import merge_configs

        base = {"rag": {"chunk_size": 512}}
        override = {"rag": {"chunk_size": 1024}}
        merged = merge_configs(base, override)
        assert merged["rag"]["chunk_size"] == 1024

    def test_nested_merge(self):
        """嵌套字典深层合并"""
        from src.config_loader import merge_configs

        base = {"rag": {"chunk_size": 512, "top_k": 5}}
        override = {"rag": {"top_k": 10}}
        merged = merge_configs(base, override)
        assert merged["rag"]["chunk_size"] == 512
        assert merged["rag"]["top_k"] == 10

    def test_three_way_merge(self):
        """三层优先级合并"""
        from src.config_loader import merge_configs

        merged = merge_configs(
            {"rag": {"chunk_size": 512}},
            {"rag": {"chunk_size": 256}},
            {"llm": {"temperature": 0.5}},
        )
        assert merged["rag"]["chunk_size"] == 256
        assert merged["llm"]["temperature"] == 0.5
