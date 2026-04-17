"""
LLM 处理器 - 与 Ollama 交互，负责意图推测和聚类重打标

使用 OpenAI SDK 兼容的 API 连接本地 Ollama 服务。
"""

import logging
import json
import os
from typing import List, Dict, Any, Optional
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

from .wmi_monitor import SystemSnapshot, ProcessEvent, WindowInfo

logger = logging.getLogger(__name__)

# 加载 .env 配置
load_dotenv()


class LLMProcessor:
    """
    LLM 处理器，负责与 Ollama 交互
    
    功能:
    - 意图推测：对原始日志进行一句话/标签化总结
    - 聚类重打标：在闲时对数据进行优化
    """
    
    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: str = "gemma4"
    ):
        """
        初始化 LLM 处理器
        
        Args:
            base_url: Ollama API 地址 (从 LLM_BASE_URL 环境变量读取)
            api_key: API 密钥 (从 LLM_API_KEY 环境变量读取，可选)
            model: 使用的模型名称
        """
        self.base_url = base_url or os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
        self.api_key = api_key or os.getenv("LLM_API_KEY", "ollama")
        self.model = model
        
        # 初始化 OpenAI 客户端 (兼容 Ollama API)
        self.client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key
        )
        
        logger.info(f"LLMProcessor initialized with base_url={self.base_url}, model={self.model}")
    
    def infer_intent(self, snapshot: SystemSnapshot) -> Dict[str, Any]:
        """
        根据系统快照推测用户意图
        
        Args:
            snapshot: 系统状态快照
            
        Returns:
            意图推断结果，包含 summary, tags, confidence 等字段
        """
        # 构建提示词
        prompt = self._build_intent_prompt(snapshot)
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是一个个人活动分析助手。根据系统活动日志，推测用户当前的意图和活动。"
                            "请返回 JSON 格式，包含以下字段:\n"
                            "- summary: 一句话总结当前活动\n"
                            "- tags: 标签列表 (如 'coding', 'browsing', 'meeting')\n"
                            "- confidence: 置信度 (0-1)\n"
                            "- primary_app: 主要使用的应用程序\n"
                            "只返回 JSON，不要有其他内容。"
                        )
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=200
            )
            
            # 解析响应
            content = response.choices[0].message.content
            if content:
                result = self._parse_json_response(content)
                if isinstance(result, dict):
                    result["timestamp"] = snapshot.timestamp.isoformat()
                    return result
            logger.warning("LLM returned empty response")
            return self._default_intent(snapshot)
                
        except Exception as e:
            logger.error(f"Error inferring intent: {e}", exc_info=True)
            return self._default_intent(snapshot)
    
    def retag_cluster(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        对一批记录进行聚类重打标
        
        Args:
            records: 待重打标的记录列表
            
        Returns:
            重打标后的记录列表
        """
        if not records:
            return records
        
        # 构建提示词
        prompt = self._build_retag_prompt(records)
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是一个数据优化助手。请分析以下活动记录，进行聚类重打标。"
                            "请返回 JSON 数组，每个元素包含:\n"
                            "- id: 原始记录 ID\n"
                            "- refined_tags: 优化后的标签列表\n"
                            "- refined_summary: 优化后的摘要\n"
                            "- cluster_id: 所属聚类 ID\n"
                            "只返回 JSON，不要有其他内容。"
                        )
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=2000
            )
            
            # 解析响应
            content = response.choices[0].message.content
            if content:
                return self._parse_retag_response(content, records)
            else:
                logger.warning("LLM returned empty response for retag")
                return records
                
        except Exception as e:
            logger.error(f"Error retagging cluster: {e}", exc_info=True)
            return records
    
    def _build_intent_prompt(self, snapshot: SystemSnapshot) -> str:
        """构建意图推测的提示词"""
        lines = [f"时间: {snapshot.timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"]
        
        # 进程事件
        if snapshot.process_events:
            lines.append("进程事件:")
            for event in snapshot.process_events:
                lines.append(f"  - {event.event_type}: {event.process_name} (PID: {event.pid})")
        
        # 窗口信息
        if snapshot.windows:
            lines.append("\n活动窗口:")
            for win in snapshot.windows[:10]:  # 限制最多10个窗口
                lines.append(f"  - [{win.process_name}] {win.title}")
        
        # 硬件信息
        if snapshot.hardware:
            hw = snapshot.hardware
            lines.append(f"\nCPU 使用率: {hw.cpu_percent}%")
            lines.append(f"内存使用率: {hw.memory_percent}%")
        
        return "\n".join(lines)
    
    def _build_retag_prompt(self, records: List[Dict[str, Any]]) -> str:
        """构建重打标的提示词"""
        lines = ["请分析以下活动记录并进行聚类重打标:\n"]
        
        for i, record in enumerate(records[:50]):  # 限制最多50条
            lines.append(f"记录 {i+1} (ID: {record.get('id', 'N/A')})")
            lines.append(f"  时间: {record.get('timestamp', 'N/A')}")
            lines.append(f"  摘要: {record.get('summary', 'N/A')}")
            lines.append(f"  标签: {record.get('tags', [])}")
            lines.append(f"  应用: {record.get('primary_app', 'N/A')}")
            lines.append("")
        
        return "\n".join(lines)
    
    def _parse_json_response(self, content: str) -> Any:
        """解析 LLM 的 JSON 响应"""
        try:
            # 尝试直接解析
            return json.loads(content)
        except json.JSONDecodeError:
            # 尝试提取 JSON 块
            try:
                start = content.index('{')
                end = content.rindex('}') + 1
                json_str = content[start:end]
                return json.loads(json_str)
            except (ValueError, json.JSONDecodeError) as e:
                logger.error(f"Failed to parse JSON response: {e}")
                return {}
    
    def _parse_retag_response(self, content: str, original_records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """解析重打标响应"""
        try:
            retagged = self._parse_json_response(content)
            if isinstance(retagged, list):
                # 将重打标结果合并回原始记录
                retag_map: Dict[Any, Any] = {}
                for r in retagged:
                    if isinstance(r, dict) and 'id' in r:
                        retag_map[r['id']] = r
                
                for record in original_records:
                    record_id = record.get('id')
                    if record_id in retag_map:
                        retag_record = retag_map[record_id]
                        if isinstance(retag_record, dict):
                            record['refined_tags'] = retag_record.get('refined_tags', record.get('tags'))
                            record['refined_summary'] = retag_record.get('refined_summary', record.get('summary'))
                            record['cluster_id'] = retag_record.get('cluster_id')
                return original_records
        except Exception as e:
            logger.error(f"Error parsing retag response: {e}")
        
        return original_records
    
    def _default_intent(self, snapshot: SystemSnapshot) -> Dict[str, Any]:
        """返回默认意图（当 LLM 调用失败时）"""
        primary_app = "unknown"
        if snapshot.windows:
            primary_app = snapshot.windows[0].process_name
        
        return {
            "summary": f"系统活动: {len(snapshot.windows)} 个窗口活跃",
            "tags": ["unknown"],
            "confidence": 0.0,
            "primary_app": primary_app,
            "timestamp": snapshot.timestamp.isoformat(),
            "fallback": True
        }
    
    def is_available(self) -> bool:
        """检查 LLM 服务是否可用"""
        try:
            # 尝试发送一个简单的请求
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "test"}],
                max_tokens=10
            )
            return response is not None
        except Exception as e:
            logger.warning(f"LLM service not available: {e}")
            return False
