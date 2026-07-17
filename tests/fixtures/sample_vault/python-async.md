---
title: Python 异步编程
tags: [python, async]
created: 2026-05-10
---

# Python 异步编程

## asyncio 基础

Python 3.10+ 的 `asyncio` 模块提供了完整的异步编程支持。

## FastAPI 中的异步

FastAPI 是异步框架，但调用同步库时需要特殊处理：

```python
import asyncio

# 错误：同步调用会阻塞事件循环
result = lance_table.search(vector).to_list()

# 正确：丢到线程池
result = await asyncio.to_thread(lance_table.search(vector).to_list)
```

> [!warning] 注意
> `asyncio.to_thread()` 需要 Python 3.9+。

#python/async
