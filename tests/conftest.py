"""测试配置 + 共享 fixtures"""
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def project_root():
    """项目根目录"""
    return Path(__file__).resolve().parent.parent


@pytest.fixture
def fixture_dir(project_root):
    """测试 fixtures 目录"""
    return project_root / "tests" / "fixtures"


@pytest.fixture
def sample_vault(fixture_dir):
    """模拟 Obsidian vault 目录"""
    return fixture_dir / "sample_vault"


@pytest.fixture
def temp_config_dir():
    """临时配置目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        (tmp / "profiles").mkdir()
        (tmp / "config").mkdir()
        yield tmp


@pytest.fixture
def minimal_config_yaml():
    """最小可用的 config.yaml 内容"""
    return {
        "rag": {
            "chunk_size": 512,
            "chunk_overlap": 64,
            "top_k": 5,
            "similarity_threshold": 0.6
        },
        "llm": {
            "model": "deepseek-v4-pro",
            "temperature": 0.3,
            "max_tokens": 2048
        },
        "embedding": {
            "model": "BAAI/bge-m3",
            "batch_size": 32,
            "device": "cpu"
        },
        "search": {
            "mode": "vector",
            "rerank_enabled": False
        },
        "paths": {
            "lancedb_dir": "data/lancedb",
            "sqlite_db": "data/rag.db"
        }
    }


@pytest.fixture
def valid_env_content():
    """有效的 .env 内容"""
    return """
OBSIDIAN_VAULT_PATH=~/test-vault
LLM_API_KEY=sk-test-key
LLM_PROVIDER=deepseek
PROFILE=default
"""
