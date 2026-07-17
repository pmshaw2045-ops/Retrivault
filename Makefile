.PHONY: help start test lint clean install setup-dev

help: ## 显示帮助信息
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## 安装依赖
	pip install -r requirements.txt
	pip install -e ".[dev]"

start: ## 一键启动 API + 打开浏览器前端
	python scripts/start.py

test: ## 运行所有测试
	python -m pytest tests/ -v

test-cov: ## 运行测试并生成覆盖率报告
	python -m pytest tests/ -v --cov=src --cov-report=html

lint: ## 代码检查
	ruff check src/ tests/
	mypy src/ --ignore-missing-imports

fix: ## 自动修复代码风格
	ruff check --fix src/ tests/

clean: ## 清理构建产物和缓存
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf htmlcov/ .coverage .mypy_cache/ 2>/dev/null || true

clean-data: ## 清理运行时数据（索引 + 数据库，源文件不受影响）
	rm -rf data/ 2>/dev/null || true

.PHONY: setup-dev
setup-dev: install ## 完整开发环境搭建
	pip install pre-commit
	pre-commit install
	@echo "✅ 开发环境就绪。运行 make start 开始。"
