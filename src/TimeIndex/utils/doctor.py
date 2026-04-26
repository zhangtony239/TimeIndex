"""
utils/doctor.py - 环境自检与依赖检查

类似 openclaw doctor 的效果，检查：
- WMI 权限
- Ollama 服务连通性
- 模型(gemma4)是否已拉取
- LanceDB 目录读写权限
"""

import sys
import ctypes
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# 检查结果状态
class CheckStatus:
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"


class DoctorCheck:
    """单个检查项"""
    name: str
    status: str
    message: str
    
    def __init__(self, name: str, status: str, message: str):
        self.name = name
        self.status = status
        self.message = message
    
    def __str__(self) -> str:
        icon = {
            CheckStatus.OK: "✓",
            CheckStatus.WARNING: "⚠",
            CheckStatus.ERROR: "✗"
        }.get(self.status, "?")
        return f"  [{icon}] {self.name}: {self.message}"


class Doctor:
    """
    环境自检工具
    
    检查项目:
    - WMI 权限
    - Ollama 服务连通性
    - 模型是否已拉取
    - LanceDB 目录读写权限
    - Python 版本
    - 依赖包是否安装
    """
    
    def __init__(self):
        self._results: List[DoctorCheck] = []
    
    def run_all(self) -> List[DoctorCheck]:
        """运行所有检查"""
        self._results = []
        
        self._check_python_version()
        self._check_dependencies()
        self._check_wmi_permission()
        self._check_ollama_connectivity()
        self._check_model_available()
        self._check_embedding_model_available()
        self._check_lancedb_path()
        
        return self._results
    
    def _check_python_version(self):
        """检查 Python 版本"""
        try:
            version = sys.version_info
            if version.major >= 3 and version.minor >= 12:
                self._results.append(DoctorCheck(
                    "Python 版本",
                    CheckStatus.OK,
                    f"{version.major}.{version.minor}.{version.micro} (>= 3.12)"
                ))
            else:
                self._results.append(DoctorCheck(
                    "Python 版本",
                    CheckStatus.WARNING,
                    f"{version.major}.{version.minor}.{version.micro} (推荐 >= 3.12)"
                ))
        except Exception as e:
            self._results.append(DoctorCheck(
                "Python 版本",
                CheckStatus.ERROR,
                f"检查失败: {e}"
            ))
    
    def _check_dependencies(self):
        """检查依赖包是否安装"""
        required_packages = [
            "lancedb",
            "openai",
            "pandas",
            "psutil",
            "wmi",
            "yaml",
        ]
        
        missing = []
        for package in required_packages:
            try:
                __import__(package.replace("-", "_"))
            except ImportError:
                missing.append(package)
        
        if missing:
            self._results.append(DoctorCheck(
                "依赖包",
                CheckStatus.ERROR,
                f"缺少: {', '.join(missing)} (运行 'pip install {' '.join(missing)}')"
            ))
        else:
            self._results.append(DoctorCheck(
                "依赖包",
                CheckStatus.OK,
                f"全部已安装 ({len(required_packages)} 个)"
            ))
    
    def _check_wmi_permission(self):
        """检查 WMI 权限"""
        try:
            is_admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
            if is_admin:
                self._results.append(DoctorCheck(
                    "WMI 权限",
                    CheckStatus.OK,
                    "管理员权限"
                ))
            else:
                self._results.append(DoctorCheck(
                    "WMI 权限",
                    CheckStatus.WARNING,
                    "非管理员权限，部分 WMI 功能可能不可用"
                ))
        except Exception as e:
            self._results.append(DoctorCheck(
                "WMI 权限",
                CheckStatus.ERROR,
                f"检查失败: {e}"
            ))
    
    def _check_ollama_connectivity(self):
        """检查 Ollama 服务连通性"""
        try:
            from ..utils.config import config
            from openai import OpenAI
            
            base_url = config.llm_base_url
            api_key = config.llm_api_key
            
            client = OpenAI(
                base_url=base_url,
                api_key=api_key
            )
            
            # 使用 models.list() 检测连通性（更轻量）
            models = client.models.list()
            model_ids = [m.id for m in models.data] if models.data else []
            
            if model_ids:
                self._results.append(DoctorCheck(
                    "LLM 服务",
                    CheckStatus.OK,
                    f"连通 (URL: {base_url}, 模型数: {len(model_ids)})"
                ))
            else:
                self._results.append(DoctorCheck(
                    "LLM 服务",
                    CheckStatus.WARNING,
                    f"连通但无可用模型 (URL: {base_url})"
                ))
                
        except Exception as e:
            self._results.append(DoctorCheck(
                "LLM 服务",
                CheckStatus.ERROR,
                f"不可达: {e}"
            ))
    
    def _check_model_available(self):
        """检查模型是否已拉取"""
        model_name = "unknown"
        try:
            from ..utils.config import config
            from openai import OpenAI
            
            model_name = config.llm_model
            base_url = config.llm_base_url
            api_key = config.llm_api_key
            
            client = OpenAI(
                base_url=base_url,
                api_key=api_key
            )
            
            # 列出可用模型
            models = client.models.list()
            model_ids = [m.id for m in models.data] if models.data else []
            
            # 检查目标模型是否存在（支持子串匹配）
            if any(model_name in m or m in model_name for m in model_ids):
                self._results.append(DoctorCheck(
                    f"模型 ({model_name})",
                    CheckStatus.OK,
                    "已加载"
                ))
            else:
                self._results.append(DoctorCheck(
                    f"模型 ({model_name})",
                    CheckStatus.WARNING,
                    f"未找到，可用模型: {', '.join(model_ids[:5]) if model_ids else '无'}"
                ))
                
        except Exception as e:
            self._results.append(DoctorCheck(
                f"模型 ({model_name})",
                CheckStatus.WARNING,
                f"无法检查: {e}"
            ))
    
    def _check_embedding_model_available(self):
        """检查 Embedding 模型是否已拉取"""
        model_name = "unknown"
        try:
            from ..utils.config import config
            from openai import OpenAI
            
            model_name = config.embedding_model
            base_url = config.llm_base_url
            api_key = config.llm_api_key
            
            client = OpenAI(
                base_url=base_url,
                api_key=api_key
            )
            
            # 列出可用模型
            models = client.models.list()
            model_ids = [m.id for m in models.data] if models.data else []
            
            # 检查目标模型是否存在
            if any(model_name in m or m in model_name for m in model_ids):
                self._results.append(DoctorCheck(
                    f"Embedding 模型 ({model_name})",
                    CheckStatus.OK,
                    "已加载"
                ))
            else:
                self._results.append(DoctorCheck(
                    f"Embedding 模型 ({model_name})",
                    CheckStatus.WARNING,
                    f"未找到，可用模型: {', '.join(model_ids[:5]) if model_ids else '无'}"
                ))
                
        except Exception as e:
            self._results.append(DoctorCheck(
                f"Embedding 模型 ({model_name})",
                CheckStatus.WARNING,
                f"无法检查: {e}"
            ))

    def _check_lancedb_path(self):
        """检查 LanceDB 目录读写权限"""
        try:
            from ..db.vector_store import DEFAULT_LANCEDB_PATH
            
            db_path = Path(DEFAULT_LANCEDB_PATH)
            
            # 检查目录是否存在
            if not db_path.exists():
                # 尝试创建
                try:
                    db_path.mkdir(parents=True, exist_ok=True)
                    self._results.append(DoctorCheck(
                        "LanceDB 目录",
                        CheckStatus.OK,
                        f"已创建: {db_path}"
                    ))
                except Exception as e:
                    self._results.append(DoctorCheck(
                        "LanceDB 目录",
                        CheckStatus.ERROR,
                        f"无法创建: {db_path} ({e})"
                    ))
                    return
            
            # 检查读写权限
            test_file = db_path / ".doctor_test"
            try:
                # 写测试
                test_file.write_text("test")
                # 读测试
                content = test_file.read_text()
                # 清理
                test_file.unlink()
                
                if content == "test":
                    self._results.append(DoctorCheck(
                        "LanceDB 目录",
                        CheckStatus.OK,
                        f"读写权限正常: {db_path}"
                    ))
                else:
                    self._results.append(DoctorCheck(
                        "LanceDB 目录",
                        CheckStatus.ERROR,
                        f"读取测试失败: {db_path}"
                    ))
            except PermissionError:
                self._results.append(DoctorCheck(
                    "LanceDB 目录",
                    CheckStatus.ERROR,
                    f"无读写权限: {db_path}"
                ))
            except Exception as e:
                self._results.append(DoctorCheck(
                    "LanceDB 目录",
                    CheckStatus.ERROR,
                    f"检查失败: {e}"
                ))
                
        except Exception as e:
            self._results.append(DoctorCheck(
                "LanceDB 目录",
                CheckStatus.ERROR,
                f"检查失败: {e}"
            ))
    
    def print_report(self):
        """打印检查报告"""
        print("\n" + "=" * 50)
        print("TimeIndex 环境自检报告")
        print("=" * 50)
        
        for result in self._results:
            print(result)
        
        # 统计
        ok_count = sum(1 for r in self._results if r.status == CheckStatus.OK)
        warn_count = sum(1 for r in self._results if r.status == CheckStatus.WARNING)
        error_count = sum(1 for r in self._results if r.status == CheckStatus.ERROR)
        
        print("-" * 50)
        print(f"总计: {ok_count} 通过, {warn_count} 警告, {error_count} 错误")
        
        if error_count > 0:
            print("\n存在错误，请修复后再运行。")
        elif warn_count > 0:
            print("\n存在警告，部分功能可能受限。")
        else:
            print("\n所有检查通过！")
        
        print("=" * 50 + "\n")
    
    def is_healthy(self) -> bool:
        """检查是否所有关键项都通过"""
        return all(r.status != CheckStatus.ERROR for r in self._results)


def run_doctor() -> Doctor:
    """运行自检并返回 Doctor 实例"""
    doctor = Doctor()
    doctor.run_all()
    doctor.print_report()
    return doctor


if __name__ == "__main__":
    run_doctor()
