"""测试 ObsidianScanner — vault 扫描 + 排除规则"""

import pytest

from src.pipeline.scanner import ObsidianScanner, ScannedDocument


class TestScannerBasic:
    """基础扫描功能"""

    def test_scan_finds_md_files(self, sample_vault):
        """扫描应该发现所有 .md 文件"""
        scanner = ObsidianScanner()
        docs = scanner.scan(str(sample_vault))
        assert len(docs) == 3  # sample_vault 有 3 个 MD

    def test_scan_returns_scanned_documents(self, sample_vault):
        """返回 ScannedDocument 列表"""
        scanner = ObsidianScanner()
        docs = scanner.scan(str(sample_vault))
        for doc in docs:
            assert isinstance(doc, ScannedDocument)
            assert doc.file_path.endswith(".md")
            assert len(doc.content) > 0

    def test_scan_reads_file_content(self, sample_vault):
        """读取文件内容非空"""
        scanner = ObsidianScanner()
        docs = scanner.scan(str(sample_vault))
        agent_doc = [d for d in docs if "agent-architecture" in d.file_path][0]
        assert "Agent 架构选型" in agent_doc.content
        assert "LanceDB" in agent_doc.content

    def test_scan_empty_directory(self, tmp_path):
        """空目录返回空列表"""
        scanner = ObsidianScanner()
        docs = scanner.scan(str(tmp_path))
        assert docs == []

    def test_scan_nonexistent_path(self):
        """不存在的路径报错"""
        scanner = ObsidianScanner()
        with pytest.raises(FileNotFoundError):
            scanner.scan("/nonexistent/path/12345")


class TestExclusionRules:
    """排除规则测试"""

    def test_excludes_excalidraw(self, tmp_path):
        """排除 *.excalidraw.md"""
        vault = tmp_path / "test_vault"
        vault.mkdir()
        (vault / "note.md").write_text("# Note\nContent")
        (vault / "drawing.excalidraw.md").write_text('{"type":"excalidraw"}')
        (vault / "another.excalidraw.md").write_text('{"type":"excalidraw"}')

        scanner = ObsidianScanner()
        docs = scanner.scan(str(vault))
        assert len(docs) == 1
        assert docs[0].file_path.endswith("note.md")

    def test_excludes_trash(self, tmp_path):
        """排除 .trash/ 目录"""
        vault = tmp_path / "test_vault"
        vault.mkdir()
        trash = vault / ".trash"
        trash.mkdir()
        (vault / "good.md").write_text("# Good")
        (trash / "deleted.md").write_text("# Deleted")

        scanner = ObsidianScanner()
        docs = scanner.scan(str(vault))
        assert len(docs) == 1
        assert docs[0].file_path.endswith("good.md")

    def test_excludes_obsidian_workspace_files(self, tmp_path):
        """排除 .obsidian/workspace*.json"""
        vault = tmp_path / "test_vault"
        vault.mkdir()
        obsidian_dir = vault / ".obsidian"
        obsidian_dir.mkdir()
        (vault / "note.md").write_text("# Note")
        (obsidian_dir / "workspace.json").write_text("{}")
        (obsidian_dir / "workspace-mobile.json").write_text("{}")
        (obsidian_dir / "app.json").write_text("{}")  # 这个不应被排除，但 scanner 不扫 .json

        scanner = ObsidianScanner()
        docs = scanner.scan(str(vault))
        # 只扫 .md 文件，.json 不会被扫到
        assert len(docs) == 1

    def test_excludes_dotfiles(self, tmp_path):
        """排除 . 开头的文件/目录（.obsidian, .trash 除外——它们已有专门规则）"""
        vault = tmp_path / "test_vault"
        vault.mkdir()
        (vault / "good.md").write_text("# Good")
        (vault / ".hidden").mkdir()
        (vault / ".hidden" / "hidden.md").write_text("# Hidden")

        scanner = ObsidianScanner()
        docs = scanner.scan(str(vault))
        assert len(docs) == 1
        assert docs[0].file_path.endswith("good.md")

    def test_skips_binary_and_images(self, tmp_path):
        """跳过图片/二进制文件——只扫 .md"""
        vault = tmp_path / "test_vault"
        vault.mkdir()
        (vault / "note.md").write_text("# Note")
        (vault / "image.png").write_bytes(b"\x89PNG")
        (vault / "photo.jpg").write_bytes(b"\xff\xd8")

        scanner = ObsidianScanner()
        docs = scanner.scan(str(vault))
        assert len(docs) == 1


class TestFrontmatterExtraction:
    """Scanner 应提取 frontmatter"""

    def test_extracts_frontmatter(self, sample_vault):
        """提取 YAML frontmatter"""
        scanner = ObsidianScanner()
        docs = scanner.scan(str(sample_vault))
        rag_doc = [d for d in docs if "rag-basics" in d.file_path][0]
        assert rag_doc.frontmatter is not None
        assert "title" in rag_doc.frontmatter
        assert rag_doc.frontmatter["title"] == "RAG 基础知识"

    def test_no_frontmatter_returns_none(self, tmp_path):
        """无 frontmatter 返回 None"""
        vault = tmp_path / "test_vault"
        vault.mkdir()
        (vault / "no_fm.md").write_text("# No frontmatter\nJust content")

        scanner = ObsidianScanner()
        docs = scanner.scan(str(vault))
        assert docs[0].frontmatter is None
