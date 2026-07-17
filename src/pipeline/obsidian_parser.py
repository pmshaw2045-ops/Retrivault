"""Obsidian 语法解析器

解析 Obsidian vault 中 .md 文件的特有语法：
  - [[wikilink]]                 跨文档链接
  - ![[embed]]                   嵌入引用
  - #tag / #nested/tag           标签
  - ---\nfrontmatter\n---         YAML 元数据
  - > [!type] callout            语义块
"""
import re
from dataclasses import dataclass, field

import yaml


@dataclass
class ParsedDocument:
    """解析后的文档——比 ScannedDocument 多了结构化语法提取"""
    file_path: str
    file_name: str
    content: str                   # 原始全文
    frontmatter: dict | None = None
    wikilinks: list[str] = field(default_factory=list)    # 去重后的链接目标列表
    tags: list[str] = field(default_factory=list)          # 去重后的标签列表
    callouts: list[dict] = field(default_factory=list)     # [{type, title, content, foldable}]
    embeds: list[dict] = field(default_factory=list)       # [{target, heading?}]
    dataview_blocks: int = 0       # dataview 代码块计数


class ObsidianParser:
    """
    Obsidian .md 语法解析器。

    所有语法提取都通过正则实现，不依赖外部 Markov 解析器。
    解析结果用于 chunk metadata，增强 RAG 检索质量。
    """

    # ============================================================
    # Frontmatter
    # ============================================================
    FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)

    # ============================================================
    # Wikilinks: [[目标]]、[[目标|别名]]、[[目标#章节]]、[[目标#章节|别名]]
    # ============================================================
    # 捕获组 1: 链接目标（不含 | 和 # 后的部分）
    WIKILINK_RE = re.compile(
        r"\[\["                          # 开头 [[
        r"([^\]|#]+)"                    # 捕获组1: 目标文件名（到 |、# 或 ]] 为止）
        r"(?:[|#][^\]]+)?"               # 可选: |别名 或 #章节 或 #章节|别名
        r"\]\]"                          # 结尾 ]]
    )

    # ============================================================
    # Embeds: ![[目标]] 或 ![[目标#章节]]
    # ============================================================
    EMBED_RE = re.compile(
        r"!\[\["
        r"([^\]|#]+)"                    # 捕获组1: 嵌入目标
        r"(?:#([^\]|]+))?"               # 可选捕获组2: 章节锚点
        r"(?:\|[^\]]+)?"                 # 可选: 别名
        r"\]\]"
    )

    # ============================================================
    # Tags: #tag、#nested/tag、#中文/标签
    # ============================================================
    TAG_RE = re.compile(
        r"(?<!\S)"                       # 前面是空白或行首（不在单词中间）
        r"#"
        r"([a-zA-Z\u4e00-\u9fa5]"        # 首字符：字母或中文
        r"[\w\u4e00-\u9fa5/-]*)"         # 后续：字母/数字/中文/下划线/连字符/斜杠
    )

    # ============================================================
    # Callouts: > [!TYPE]+ 标题\n> 内容
    # ============================================================
    CALLOUT_RE = re.compile(
        r">\s*\[!(\w+)\]([+-]?)\s*(.*?)\n"   # > [!TYPE][+/-] 标题
        r"((?:>\s*[^\n]*\n?)+)"               # callout 内容（连续 > 行）
    )

    IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".bmp", ".webp", ".ico"}

    def parse(self, content: str, file_path: str = "unknown.md") -> ParsedDocument:
        """
        解析 .md 内容，提取所有 Obsidian 特有语法要素。

        Args:
            content: Markdown 全文
            file_path: 文件路径（用于 metadata）

        Returns:
            ParsedDocument 实例
        """
        file_name = file_path.split("/")[-1]
        embeds = self._extract_embeds(content)
        wikilinks = self._extract_wikilinks(content)
        tags = self._extract_tags(content)

        # 将图像嵌入的文件名注入正文（提升图片文件名可搜索性）
        image_refs = self._extract_image_refs(embeds)
        if image_refs:
            content = content + "\n\n" + " ".join(f"[图片: {ref}]" for ref in image_refs)

        return ParsedDocument(
            file_path=file_path,
            file_name=file_name,
            content=content,
            frontmatter=self._extract_frontmatter(content),
            wikilinks=wikilinks,
            tags=tags,
            callouts=self._extract_callouts(content),
            embeds=embeds,
            dataview_blocks=self._count_dataview_blocks(content),
        )

    # ---------- Frontmatter ----------

    @staticmethod
    def _extract_frontmatter(content: str) -> dict | None:
        """提取 YAML frontmatter"""
        if not content.startswith("---"):
            return None
        match = ObsidianParser.FRONTMATTER_RE.match(content)
        if not match:
            return None
        try:
            fm = yaml.safe_load(match.group(1))
            if isinstance(fm, dict):
                # 标准化 tags: 字符串 → [字符串]
                if "tags" in fm:
                    if isinstance(fm["tags"], str):
                        fm["tags"] = [fm["tags"]]
                return fm
            return None
        except yaml.YAMLError:
            return None

    # ---------- Wikilinks ----------

    @staticmethod
    def _extract_wikilinks(content: str) -> list[str]:
        """提取所有 wikilink 目标（去重，保持出现顺序）"""
        matches = ObsidianParser.WIKILINK_RE.findall(content)
        seen: set[str] = set()
        result: list[str] = []
        for target in matches:
            target = target.strip()
            if target and target not in seen:
                seen.add(target)
                result.append(target)
        return result

    # ---------- Tags ----------

    @staticmethod
    def _extract_tags(content: str) -> list[str]:
        """提取所有 #tag（排除代码块和 URL 中的）"""
        # 先移除代码块（```...``` 和 `...`）
        clean = re.sub(r"```[\s\S]*?```", "", content)  # 移除围栏代码块
        clean = re.sub(r"`[^`]+`", "", clean)            # 移除行内代码

        # 移除 URL（http... 中的 # 不是 tag）
        clean = re.sub(r"https?://\S+", "", clean)

        matches = ObsidianParser.TAG_RE.findall(clean)
        seen: set[str] = set()
        result: list[str] = []
        for tag in matches:
            tag = f"#{tag}"
            if tag not in seen:
                seen.add(tag)
                result.append(tag)
        return result

    # ---------- Callouts ----------

    @staticmethod
    def _extract_callouts(content: str) -> list[dict]:
        """提取所有 callout"""
        callouts: list[dict] = []
        for match in ObsidianParser.CALLOUT_RE.finditer(content):
            callout_type = match.group(1).lower()
            foldable = match.group(2) == "+"
            title = match.group(3).strip()
            body = match.group(4).strip()
            # 去掉每行的 > 前缀
            body = re.sub(r"^>\s?", "", body, flags=re.MULTILINE)
            callouts.append({
                "type": callout_type,
                "title": title,
                "content": body,
                "foldable": foldable,
            })
        return callouts

    # ---------- Embeds ----------

    @staticmethod
    def _extract_embeds(content: str) -> list[dict]:
        """提取所有 ![[embed]]"""
        embeds: list[dict] = []
        for match in ObsidianParser.EMBED_RE.finditer(content):
            emb = {"target": match.group(1).strip()}
            if match.group(2):
                emb["heading"] = match.group(2).strip()
            embeds.append(emb)
        return embeds

    @staticmethod
    def _extract_image_refs(embeds: list[dict]) -> list[str]:
        """从 embeds 中提取图片引用（去除扩展名，保留文件名）

        如 ![[架构图.png]] → "架构图"
        """
        refs: list[str] = []
        seen: set[str] = set()
        for emb in embeds:
            target = emb.get("target", "")
            # 检查是否是已知图片扩展名
            dot = target.rfind(".")
            if dot == -1:
                continue
            ext = target[dot:].lower()
            if ext in ObsidianParser.IMAGE_EXTENSIONS:
                name = target[:dot]
                if name and name not in seen:
                    seen.add(name)
                    refs.append(name)
        return refs

    # ---------- Dataview ----------

    @staticmethod
    def _count_dataview_blocks(content: str) -> int:
        """统计 dataview 代码块数量"""
        return len(re.findall(r"```dataview", content, re.IGNORECASE))
