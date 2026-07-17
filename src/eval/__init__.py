"""金标数据集管理

格式（YAML）：
  queries:
    - query: "Agent落地有哪些关键原则"
      relevant_docs:
        - "Agent 落地12条.md"
      relevant_chunks:        # 可选，更精细的标注
        - "chunk_hash_xxx"
      description: "应召回Agent 落地12条"
"""
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class GoldenQuery:
    query: str
    relevant_docs: list[str] = field(default_factory=list)
    relevant_chunks: list[str] = field(default_factory=list)
    description: str = ""

    @property
    def has_chunk_labels(self) -> bool:
        return len(self.relevant_chunks) > 0


@dataclass
class GoldenDataset:
    name: str
    queries: list[GoldenQuery]

    def __len__(self):
        return len(self.queries)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "GoldenDataset":
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        queries = []
        for item in data.get("queries", []):
            queries.append(GoldenQuery(
                query=item["query"],
                relevant_docs=item.get("relevant_docs", []),
                relevant_chunks=item.get("relevant_chunks", []),
                description=item.get("description", ""),
            ))

        return cls(
            name=data.get("name", Path(path).stem),
            queries=queries,
        )

    @classmethod
    def from_dict(cls, name: str, query_list: list[dict]) -> "GoldenDataset":
        queries = []
        for item in query_list:
            queries.append(GoldenQuery(
                query=item["query"],
                relevant_docs=item.get("relevant_docs", []),
                relevant_chunks=item.get("relevant_chunks", []),
                description=item.get("description", ""),
            ))
        return cls(name=name, queries=queries)
