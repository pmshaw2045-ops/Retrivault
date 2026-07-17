"""Obsidian vault 扫描器

职责：
1. 递归扫描 vault 目录下所有 .md 文件
2. 应用排除规则（excalidraw / .trash / .obsidian 工作区 / 隐藏文件）
3. 读取文件全文 + 提取 frontmatter
"""
import os
import re
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class ScannedDocument:
    """扫描到的文档原始数据"""
    file_path: str           # 文件绝对路径
    file_name: str           # 文件名（不含路径）
    content: str             # 文件全文
    frontmatter: dict | None = None  # YAML frontmatter（解析后的 dict）
    file_mtime: float = 0.0  # 文件修改时间戳

    @property
    def relative_path(self) -> str:
        """相对于 vault 的路径"""
        return self.file_path


class ObsidianScanner:
    """
    Obsidian vault 扫描器。

    排除规则（硬编码，Phase 1 不接受用户配置）：
      - *.excalidraw.md    Excalidraw 绘图元数据（JSON，非 Markdown）
      - .trash/            Obsidian 回收站
      - .obsidian/         工作区配置（只扫 .md，不会扫 .json）
      - .开头的隐藏文件/目录
      - 非 .md 的二进制文件（图片/视频/音频）
    """

    # 文件名排除模式
    EXCLUDE_PATTERNS: list[str] = [
        r".*\.excalidraw\.md$",   # Excalidraw 元数据
    ]

    # 路径排除（相对于 vault 根目录的片段匹配）
    EXCLUDE_PATH_SEGMENTS: list[str] = [
        ".trash",
        ".obsidian",
        ".git",
        ".DS_Store",
    ]

    def scan(self, vault_path: str) -> list[ScannedDocument]:
        """
        扫描 vault 目录，返回 ScannedDocument 列表。

        Args:
            vault_path: Obsidian vault 绝对路径

        Returns:
            ScannedDocument 列表

        Raises:
            FileNotFoundError: vault_path 不存在
        """
        vault = Path(vault_path).expanduser().resolve()
        if not vault.exists():
            raise FileNotFoundError(f"Vault path does not exist: {vault_path}")
        if not vault.is_dir():
            raise NotADirectoryError(f"Vault path is not a directory: {vault_path}")

        documents: list[ScannedDocument] = []

        for root, dirs, files in os.walk(str(vault)):
            # 原地过滤不需要进入的目录
            dirs[:] = [d for d in dirs if not self._should_exclude_dir(d)]

            for file_name in files:
                file_path = Path(root) / file_name

                # 只处理 .md 文件
                if not file_name.endswith(".md"):
                    continue

                # 文件名排除
                if self._should_exclude_file(file_name):
                    continue

                # 路径排除
                rel_path = str(file_path.relative_to(vault))
                if self._should_exclude_path(rel_path):
                    continue

                # 读取文件
                try:
                    content = file_path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue  # 跳过无法按 UTF-8 读取的文件

                # 提取 frontmatter
                frontmatter = self._extract_frontmatter(content)

                documents.append(ScannedDocument(
                    file_path=str(file_path),
                    file_name=file_name,
                    content=content,
                    frontmatter=frontmatter,
                    file_mtime=file_path.stat().st_mtime,
                ))

        return documents

    def _should_exclude_file(self, file_name: str) -> bool:
        """检查文件名是否匹配排除模式"""
        for pattern in self.EXCLUDE_PATTERNS:
            if re.match(pattern, file_name):
                return True
        return False

    def _should_exclude_dir(self, dir_name: str) -> bool:
        """检查目录是否应被排除"""
        # . 开头的隐藏目录
        if dir_name.startswith("."):
            return True
        for segment in self.EXCLUDE_PATH_SEGMENTS:
            if segment in dir_name:
                return True
        return False

    def _should_exclude_path(self, rel_path: str) -> bool:
        """检查相对路径是否包含排除片段"""
        path_lower = rel_path.lower()
        for segment in self.EXCLUDE_PATH_SEGMENTS:
            if segment.lower() in path_lower:
                return True
        return False

    @staticmethod
    def _extract_frontmatter(content: str) -> dict | None:
        """
        提取 YAML frontmatter。

        Obsidian frontmatter 格式：
        ---
        title: 文档标题
        tags: [a, b]
        ---
        """
        # 必须以 --- 开头
        if not content.startswith("---"):
            return None

        # 找到第二个 ---
        match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
        if not match:
            return None

        yaml_str = match.group(1)
        try:
            fm = yaml.safe_load(yaml_str)
            if isinstance(fm, dict):
                # 标准化 tags 字段（可能是字符串或列表）
                if "tags" in fm:
                    if isinstance(fm["tags"], str):
                        fm["tags"] = [fm["tags"]]
                return fm
            return None
        except yaml.YAMLError:
            return None
