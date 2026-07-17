"""测试 LocalBGEEmbedder — batch、query instruction、model_name"""

from unittest.mock import patch

import numpy as np

from src.embedding_providers.local_bge_m3 import LocalBGEEmbedder


class TestEmbedderBasic:
    """基础属性"""

    def test_model_name(self):
        """model_name 返回模型标识"""
        embedder = LocalBGEEmbedder()
        assert embedder.model_name == "BAAI/bge-m3"

    def test_default_params(self):
        """默认参数"""
        embedder = LocalBGEEmbedder()
        assert embedder.batch_size == 32
        assert embedder.device == "cpu"

    def test_custom_params(self):
        """自定义参数"""
        embedder = LocalBGEEmbedder(model_name="BAAI/bge-small", device="mps", batch_size=16)
        assert embedder.model_name == "BAAI/bge-small"
        assert embedder.batch_size == 16


class TestQueryEmbedding:
    """查询向量化"""

    def test_query_adds_instruction_prefix(self):
        """embed_query 自动加 instruction prefix"""
        with patch.object(LocalBGEEmbedder, "model") as mock_model:
            mock_model.encode.return_value = np.zeros(1024)
            embedder = LocalBGEEmbedder()
            embedder.embed_query("测试查询")

            call_args = mock_model.encode.call_args[0][0]
            assert embedder.QUERY_INSTRUCTION in call_args
            assert "测试查询" in call_args

    def test_embed_query_returns_list(self):
        """返回 Python list，不是 numpy array"""
        with patch.object(LocalBGEEmbedder, "model") as mock_model:
            mock_model.encode.return_value = np.zeros(1024)
            embedder = LocalBGEEmbedder()
            result = embedder.embed_query("test")
            assert isinstance(result, list)
            assert len(result) == 1024


class TestDocumentEmbedding:
    """文档批量向量化"""

    def test_empty_texts(self):
        """空列表返回空列表"""
        embedder = LocalBGEEmbedder()
        result = embedder.embed_documents([])
        assert result == []

    def test_batch_splitting(self):
        """验证 batch 分片逻辑"""
        with patch.object(LocalBGEEmbedder, "model") as mock_model:
            # 模拟：每次 encode 返回 batch_size 个 1024 维向量
            def fake_encode(texts, **kwargs):
                return np.random.randn(len(texts), 1024).astype(np.float32)

            mock_model.encode.side_effect = fake_encode
            embedder = LocalBGEEmbedder(batch_size=2)

            texts = ["text1", "text2", "text3", "text4", "text5"]
            result = embedder.embed_documents(texts)

            assert len(result) == 5  # 5 个输入 → 5 个输出
            assert all(len(v) == 1024 for v in result)

            # encode 被调用多次（batch_size=2，5 个 texts → ceil(5/2)=3 次调用）
            assert mock_model.encode.call_count == 3

    def test_output_is_normalized(self):
        """输出应为归一化向量"""
        with patch.object(LocalBGEEmbedder, "model") as mock_model:
            mock_model.encode.return_value = np.zeros(1024)
            embedder = LocalBGEEmbedder()
            embedder.embed_documents(["text"])

            # 验证 normalize_embeddings=True 被传递
            call_kwargs = mock_model.encode.call_args[1]
            assert call_kwargs.get("normalize_embeddings") is True
