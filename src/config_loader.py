"""配置加载器

合并优先级（后者覆盖前者）：
  代码默认值 < profiles/*.yaml < config/config.yaml < .env < UI 面板
"""
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import ValidationError

from config.config_schema import AppConfig

# 项目根目录（config_loader.py 在 src/ 下，项目根在上上级）
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
PROFILES_DIR = PROJECT_ROOT / "profiles"


def load_env() -> dict:
    """加载 .env 文件，返回提取的关键变量"""
    load_dotenv(PROJECT_ROOT / ".env")

    return {
        "vault_path": os.getenv("OBSIDIAN_VAULT_PATH", ""),
        "llm_api_key": os.getenv("LLM_API_KEY", ""),
        "llm_provider": os.getenv("LLM_PROVIDER", "deepseek"),
        "profile": os.getenv("PROFILE", "default"),
    }


def load_profile(profile_name: str) -> dict:
    """加载 profiles/{name}.yaml，不存在则返回空"""
    profile_path = PROFILES_DIR / f"{profile_name}.yaml"
    if not profile_path.exists():
        print(f"[WARN] Profile '{profile_name}' not found, skipping.")
        return {}
    with open(profile_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_config_yaml() -> dict:
    """加载 config/config.yaml"""
    config_path = CONFIG_DIR / "config.yaml"
    if not config_path.exists():
        return {}
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def merge_configs(*dicts: dict) -> dict:
    """浅层合并：后面的覆盖前面的（嵌套字典递归合并）"""
    result: dict = {}
    for d in dicts:
        for key, value in d.items():
            if isinstance(value, dict) and isinstance(result.get(key), dict):
                result[key] = {**result[key], **value}
            else:
                result[key] = value
    return result


def load_app_config() -> AppConfig:
    """
    主入口：加载并合并所有配置源，返回校验后的 AppConfig。

    优先级：代码默认值 < profiles/*.yaml < config/config.yaml < .env < UI 面板
    """
    env = load_env()

    # 1. 代码默认值（AppConfig 的 Field(default=...)）
    defaults = AppConfig().model_dump()

    # 2. profiles/*.yaml（提取可覆盖的配置项）
    profile_raw = load_profile(env["profile"])
    profile_config = _extract_config_overrides(profile_raw)

    # 3. config/config.yaml
    config_yaml = load_config_yaml()

    # 4. .env（LLM model 和 provider 分开处理）
    env_config: dict = {}
    if env.get("llm_provider") and env["llm_provider"] != "deepseek":
        env_config["llm"] = {"model": env["llm_provider"]}

    # 合并
    merged = merge_configs(defaults, profile_config, config_yaml, env_config)

    # Pydantic 校验
    try:
        return AppConfig(**merged)
    except ValidationError as e:
        print(f"[ERROR] 配置校验失败:\n{e}")
        raise


def _extract_config_overrides(profile: dict) -> dict:
    """从 profile YAML 中提取可覆盖 AppConfig 的字段"""
    overrides: dict = {}

    # embedding 配置直接从 profile 映射
    if "embedding" in profile:
        emb = profile["embedding"]
        emb_override = {}
        if "model" in emb:
            emb_override["model"] = emb["model"]
        if "provider" in emb:
            emb_override["provider"] = emb["provider"]
        if emb_override:
            overrides["embedding"] = emb_override

    # llm model 从 profile 映射
    if "llm" in profile and "model" in profile["llm"]:
        overrides.setdefault("llm", {})["model"] = profile["llm"]["model"]

    return overrides


# 模块级单例（应用启动时加载一次）
_app_config: AppConfig | None = None


def get_config() -> AppConfig:
    """获取应用配置（懒加载）"""
    global _app_config
    if _app_config is None:
        _app_config = load_app_config()
    return _app_config


def reload_config() -> AppConfig:
    """重新加载配置（UI 修改参数后调用）"""
    global _app_config
    _app_config = load_app_config()
    return _app_config
