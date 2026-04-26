"""
utils/config.py - 配置加载器

负责解析 config.yaml 文件，提供全局配置加载功能。
"""

import os
import logging
from typing import List, Dict, Any, Optional
import yaml
from ruamel.yaml import YAML

logger = logging.getLogger(__name__)

class Config:
    """
    全局配置加载器
    
    从 config.yaml 文件加载配置。
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化配置加载器
        
        Args:
            config_path: config.yaml 文件路径
        """
        if config_path is None:
            # 优先查找用户目录下的 ~/.timeindex/config.yaml
            user_config_path = os.path.join(os.path.expanduser("~"), ".timeindex", "config.yaml")
            if os.path.exists(user_config_path):
                config_path = user_config_path
            else:
                # 备选查找 src/TimeIndex/config.yaml (与 entry.py 同级)
                current_dir = os.path.abspath(os.path.dirname(__file__))
                config_path = os.path.join(current_dir, "..", "config.yaml")
        
        self._config_path = config_path
        self._config: Dict[str, Any] = {}
        
        self._load()
    
    def _load(self):
        """加载 config.yaml 文件"""
        if not os.path.exists(self._config_path):
            logger.warning(f"config.yaml not found at {self._config_path}, using defaults")
            self._setup_logging()
            return
        
        try:
            with open(self._config_path, 'r', encoding='utf-8') as f:
                yaml_config = yaml.safe_load(f)
                if yaml_config and isinstance(yaml_config, dict):
                    # 更新配置，保持默认值如果 yaml 中没有
                    for key, value in yaml_config.items():
                        self._config[key] = value
            logger.info(f"Config loaded from {self._config_path}")
        except Exception as e:
            logger.error(f"Failed to load config.yaml: {e}")
        
        self._setup_logging()
    
    def _setup_logging(self):
        """根据 USER_DEBUG 配置日志"""
        user_debug = self._config.get("USER_DEBUG", False)
        level = logging.DEBUG if user_debug else logging.ERROR
        
        handlers: List[logging.Handler] = [logging.StreamHandler()]
        
        if user_debug:
            # 生成 log 文件在系统桌面上
            try:
                desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
                log_file = os.path.join(desktop_path, "timeindex_debug.log")
                handlers.append(logging.FileHandler(log_file, encoding='utf-8'))
            except Exception as e:
                print(f"Failed to create desktop log file: {e}")

        # 清除之前的 handler 重新配置
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)

        logging.basicConfig(
            level=level,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            handlers=handlers
        )

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        return self._config.get(key, default)
    
    @property
    def global_blacklist(self) -> List[str]:
        """全局进程黑名单"""
        return self._config.get("global_blacklist", [])
    
    @property
    def retag_rules(self) -> Dict[str, Any]:
        """重打标规则"""
        return self._config.get("retag_rules", {})
    
    @property
    def rag_keepalive(self) -> str:
        """RAG 日志生命周期模式"""
        return self._config.get("rag_keepalive", "auto")
    
    @property
    def rag_timeout(self) -> Optional[int]:
        """RAG 日志超时阈值（天）"""
        return self._config.get("rag_timeout")
    
    @property
    def retag_mode(self) -> int:
        """重打标 CPU 空闲阈值"""
        return self._config.get("retag_mode", 20)
    
    @property
    def cpu_performance_weight(self) -> Optional[List[int]]:
        """CPU 异构权重"""
        return self._config.get("cpu_performance_weight")
    
    @property
    def llm_base_url(self) -> str:
        """LLM API 地址"""
        return self._config.get("LLM_BASE_URL", "http://localhost:11434/v1")
    
    @property
    def llm_api_key(self) -> str:
        """LLM API 密钥"""
        return self._config.get("LLM_API_KEY", "ollama")
    
    @property
    def llm_model(self) -> str:
        """LLM 模型名称"""
        return self._config.get("LLM_MODEL", "gemma-4-e4b")
    
    @property
    def embedding_model(self) -> str:
        """Embedding 模型名称"""
        return self._config.get("EMBEDDING_MODEL", "text-embedding-embeddinggemma-300m")

    @property
    def user_debug(self) -> bool:
        """Debug 模式开关"""
        return self._config.get("USER_DEBUG", False)
    
    def reload(self):
        """重新加载配置"""
        self._load()
        logger.info("Config reloaded")

    def update_value(self, key: str, value: str):
        """
        靶向更新配置项并保留注释
        
        Args:
            key: 配置项键名
            value: 配置项值（字符串形式，将尝试转换类型）
        """
        if not os.path.exists(self._config_path):
            logger.error(f"Cannot update config: {self._config_path} not found")
            return

        # 尝试转换类型
        try:
            import ast
            typed_value = ast.literal_eval(value)
        except (ValueError, SyntaxError):
            typed_value = value

        ryaml = YAML()
        ryaml.preserve_quotes = True
        ryaml.indent(mapping=2, sequence=4, offset=2)

        try:
            with open(self._config_path, 'r', encoding='utf-8') as f:
                data = ryaml.load(f)
            
            if data is None:
                data = {}
            
            data[key] = typed_value
            
            with open(self._config_path, 'w', encoding='utf-8') as f:
                ryaml.dump(data, f)
            
            logger.info(f"Config key '{key}' updated to '{typed_value}' in {self._config_path}")
            self.reload()
        except Exception as e:
            logger.error(f"Failed to update config file: {e}")


# 全局配置实例
config = Config()
