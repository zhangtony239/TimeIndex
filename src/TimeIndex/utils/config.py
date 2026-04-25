"""
utils/config.py - 配置加载器

负责解析 .env 文件，提供全局配置加载功能。
"""

import os
import ast
import logging
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# 默认配置值
DEFAULT_CONFIG = {
    "global_blacklist": [],
    "retag_rules": {},
    "rag_keepalive": "auto",
    "rag_timeout": None,
    "retag_mode": 20,
    "cpu_performance_weight": None,
    "LLM_BASE_URL": "http://localhost:11434/v1",
    "LLM_API_KEY": "ollama",
    "LLM_MODEL": "gemma-4-e4b",
    "USER_DEBUG": False
}


class Config:
    """
    全局配置加载器
    
    从 .env 文件加载配置，并提供类型安全的访问接口。
    """
    
    def __init__(self, env_path: Optional[str] = None):
        """
        初始化配置加载器
        
        Args:
            env_path: .env 文件路径，默认为项目根目录下的 .env
        """
        if env_path is None:
            # 默认查找项目根目录的 .env (src/TimeIndex/utils/config.py -> ../../../.env)
            env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))
        
        self._env_path = env_path
        self._config: Dict[str, Any] = dict(DEFAULT_CONFIG)
        
        self._load()
    
    def _load(self):
        """加载 .env 文件并解析配置"""
        if not os.path.exists(self._env_path):
            logger.warning(f".env file not found at {self._env_path}, using defaults")
            return
        
        # 手动解析 .env 文件以支持多行值
        env_vars = self._parse_env_file(self._env_path)
        
        # 解析特定配置
        self._config["global_blacklist"] = self._parse_list(
            env_vars.get("global_blacklist", "[]")
        )
        
        self._config["retag_rules"] = self._parse_dict(
            env_vars.get("retag_rules", "{}")
        )
        
        self._config["rag_keepalive"] = env_vars.get("rag_keepalive", "auto").strip("'\"")
        
        rag_timeout = env_vars.get("rag_timeout")
        self._config["rag_timeout"] = int(rag_timeout) if rag_timeout else None
        
        retag_mode = env_vars.get("retag_mode")
        self._config["retag_mode"] = int(retag_mode) if retag_mode else 20
        
        cpu_weight = env_vars.get("cpu_performace_weight")  # 注意：.env 中是 cpu_performace_weight (拼写错误)
        if cpu_weight:
            self._config["cpu_performance_weight"] = self._parse_list(cpu_weight)
        
        self._config["LLM_BASE_URL"] = env_vars.get("LLM_BASE_URL", "http://localhost:11434/v1").strip("'\"")
        self._config["LLM_API_KEY"] = env_vars.get("LLM_API_KEY", "ollama").strip("'\"")

        self._config["LLM_MODEL"] = env_vars.get("LLM_MODEL", "gemma-4-e4b").strip("'\"")
        
        user_debug = env_vars.get("USER_DEBUG", "false").lower()
        self._config["USER_DEBUG"] = user_debug == "true"
        
        self._setup_logging()
        logger.info(f"Config loaded from {self._env_path}")
    
    def _parse_env_file(self, env_path: str) -> Dict[str, str]:
        """手动解析 .env 文件以支持多行值"""
        env_vars: Dict[str, str] = {}
        current_key = None
        current_value_lines = []
        
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.rstrip()
                
                # 跳过空行和注释
                if not line or line.startswith('#'):
                    continue
                
                # 检查是否是新键值对
                if '=' in line and not line.startswith((' ', '\t')):
                    # 保存之前的多行值
                    if current_key is not None:
                        env_vars[current_key] = '\n'.join(current_value_lines)
                    
                    key, _, value = line.partition('=')
                    current_key = key.strip()
                    current_value_lines = [value.strip()]
                elif current_key is not None:
                    # 多行值的延续
                    current_value_lines.append(line)
            
            # 保存最后一个键值对
            if current_key is not None:
                env_vars[current_key] = '\n'.join(current_value_lines)
        
        return env_vars
    
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

    def _parse_list(self, value: str) -> List[str]:
        """安全地解析列表字符串"""
        try:
            result = ast.literal_eval(value)
            if isinstance(result, list):
                return [str(x) for x in result]
            return []
        except (ValueError, SyntaxError):
            logger.warning(f"Failed to parse list value: {value}")
            return []
    
    def _parse_dict(self, value: str) -> Dict[str, Any]:
        """安全地解析字典字符串"""
        try:
            result = ast.literal_eval(value)
            if isinstance(result, dict):
                return result
            return {}
        except (ValueError, SyntaxError):
            logger.warning(f"Failed to parse dict value: {value}")
            return {}
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        return self._config.get(key, default)
    
    @property
    def global_blacklist(self) -> List[str]:
        """全局进程黑名单"""
        return self._config["global_blacklist"]
    
    @property
    def retag_rules(self) -> Dict[str, Any]:
        """重打标规则"""
        return self._config["retag_rules"]
    
    @property
    def rag_keepalive(self) -> str:
        """RAG 日志生命周期模式"""
        return self._config["rag_keepalive"]
    
    @property
    def rag_timeout(self) -> Optional[int]:
        """RAG 日志超时阈值（天）"""
        return self._config["rag_timeout"]
    
    @property
    def retag_mode(self) -> int:
        """重打标 CPU 空闲阈值"""
        return self._config["retag_mode"]
    
    @property
    def cpu_performance_weight(self) -> Optional[List[int]]:
        """CPU 异构权重"""
        return self._config["cpu_performance_weight"]
    
    @property
    def llm_base_url(self) -> str:
        """LLM API 地址"""
        return self._config["LLM_BASE_URL"]
    
    @property
    def llm_api_key(self) -> str:
        """LLM API 密钥"""
        return self._config["LLM_API_KEY"]
    
    @property
    def llm_model(self) -> str:
        """LLM 模型名称"""
        return self._config["LLM_MODEL"]
    
    @property
    def user_debug(self) -> bool:
        """Debug 模式开关"""
        return self._config["USER_DEBUG"]
    
    def reload(self):
        """重新加载配置"""
        self._load()
        logger.info("Config reloaded")


# 全局配置实例
config = Config()
