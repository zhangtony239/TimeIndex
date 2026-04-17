"""
db/vector_store.py - 向量存储与 RAG 层

封装 LanceDB SDK，处理带时间戳的向量化日志存储、RAG 查询和生命周期管理。

功能:
- 存储带时间戳的向量化日志
- 语义搜索与 RAG 查询
- 时间范围查询
- 根据 rag_keepalive 和 rag_timeout 自动清理过期日志
- 支持重打标记录的读写
"""

import os
import logging
import threading
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from pathlib import Path

import lancedb
import pyarrow as pa
from lancedb.table import Table

from utils.config import config

logger = logging.getLogger(__name__)

# LanceDB 表结构定义
# 包含: id, timestamp, summary, tags, confidence, primary_app,
#       active_windows, process_events, hardware,
#       refined_tags, refined_summary, cluster_id, vector
TIMEINDEX_SCHEMA = pa.schema([
    pa.field("id", pa.string()),
    pa.field("timestamp", pa.string()),
    pa.field("summary", pa.string()),
    pa.field("tags", pa.list_(pa.string())),
    pa.field("confidence", pa.float32()),
    pa.field("primary_app", pa.string()),
    pa.field("active_windows", pa.list_(pa.string())),
    pa.field("process_events", pa.list_(pa.string())),
    pa.field("hardware", pa.string()),  # JSON 字符串
    pa.field("refined_tags", pa.list_(pa.string())),
    pa.field("refined_summary", pa.string()),
    pa.field("cluster_id", pa.string()),
    pa.field("vector", pa.list_(pa.float32(), 384)),  # 默认 384 维向量 (all-MiniLM-L6-v2)
])

# 默认 LanceDB 存储路径
DEFAULT_LANCEDB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".lancedb")


class VectorStore:
    """
    LanceDB 向量存储封装类
    
    提供基础的向量数据库操作，包括插入、查询、删除等。
    """
    
    def __init__(self, db_path: Optional[str] = None, vector_dim: int = 384):
        """
        初始化向量存储
        
        Args:
            db_path: LanceDB 数据库路径
            vector_dim: 向量维度 (需与嵌入模型匹配)
        """
        self._db_path = db_path or DEFAULT_LANCEDB_PATH
        self._vector_dim = vector_dim
        self._db: Optional[lancedb.DBConnection] = None
        self._table: Optional[Table] = None
        self._lock = threading.Lock()
        
        # 确保目录存在
        Path(self._db_path).mkdir(parents=True, exist_ok=True)
        
        logger.info(f"VectorStore initialized with path={self._db_path}, dim={self._vector_dim}")
    
    def connect(self) -> lancedb.DBConnection:
        """连接到 LanceDB 数据库"""
        if self._db is None:
            self._db = lancedb.connect(self._db_path)
        return self._db
    
    def get_table(self, table_name: str = "timeindex") -> Table:
        """
        获取或创建表
        
        Args:
            table_name: 表名
            
        Returns:
            LanceDB Table 对象
        """
        if self._table is not None:
            return self._table
        
        db = self.connect()
        table_names = db.table_names()
        
        if table_name in table_names:
            self._table = db.open_table(table_name)
            logger.info(f"Opened existing table: {table_name}")
        else:
            # 创建新表
            self._table = db.create_table(
                table_name,
                schema=TIMEINDEX_SCHEMA,
                mode="create"
            )
            logger.info(f"Created new table: {table_name}")
        
        return self._table
    
    def add(self, record: Dict[str, Any], table_name: str = "timeindex") -> str:
        """
        添加单条记录
        
        Args:
            record: 记录字典
            table_name: 表名
            
        Returns:
            记录 ID
        """
        with self._lock:
            table = self.get_table(table_name)
            
            # 准备数据
            data = self._prepare_record(record)
            
            # 插入
            table.add([data])
            
            logger.debug(f"Added record {data['id']} to table {table_name}")
            return data["id"]
    
    def add_batch(self, records: List[Dict[str, Any]], table_name: str = "timeindex") -> int:
        """
        批量添加记录
        
        Args:
            records: 记录列表
            table_name: 表名
            
        Returns:
            添加的记录数
        """
        if not records:
            return 0
        
        with self._lock:
            table = self.get_table(table_name)
            
            # 准备数据
            data = [self._prepare_record(r) for r in records]
            
            # 批量插入
            table.add(data)
            
            logger.info(f"Added {len(data)} records to table {table_name}")
            return len(data)
    
    def update(self, record: Dict[str, Any], table_name: str = "timeindex") -> bool:
        """
        更新记录
        
        Args:
            record: 记录字典 (必须包含 id)
            table_name: 表名
            
        Returns:
            是否更新成功
        """
        record_id = record.get("id")
        if not record_id:
            logger.warning("Cannot update record without id")
            return False
        
        with self._lock:
            table = self.get_table(table_name)
            
            # 构建更新数据
            update_data = self._prepare_record(record)
            
            # LanceDB 更新: 先删除再插入
            table.delete(f"id = '{record_id}'")
            table.add([update_data])
            
            logger.debug(f"Updated record {record_id}")
            return True
    
    def update_batch(self, records: List[Dict[str, Any]], table_name: str = "timeindex") -> int:
        """
        批量更新记录
        
        Args:
            records: 记录列表
            table_name: 表名
            
        Returns:
            更新的记录数
        """
        count = 0
        for record in records:
            if self.update(record, table_name):
                count += 1
        return count
    
    def query_by_time_range(
        self,
        start_time: datetime,
        end_time: datetime,
        limit: int = 100,
        table_name: str = "timeindex"
    ) -> List[Dict[str, Any]]:
        """
        按时间范围查询记录
        
        Args:
            start_time: 开始时间
            end_time: 结束时间
            limit: 返回记录数限制
            table_name: 表名
            
        Returns:
            记录列表
        """
        table = self.get_table(table_name)
        
        start_str = start_time.isoformat()
        end_str = end_time.isoformat()
        
        # 查询并过滤
        results = table.search().to_pandas()
        results = results[
            (results["timestamp"] >= start_str) & 
            (results["timestamp"] <= end_str)
        ]
        results = results.head(limit)
        
        return self._results_to_records(results)
    
    def query_by_tags(
        self,
        tags: List[str],
        limit: int = 50,
        table_name: str = "timeindex"
    ) -> List[Dict[str, Any]]:
        """
        按标签查询记录
        
        Args:
            tags: 标签列表
            limit: 返回记录数限制
            table_name: 表名
            
        Returns:
            记录列表
        """
        table = self.get_table(table_name)
        
        results = table.search().to_pandas()
        
        # 过滤包含任一标签的记录
        mask = results["tags"].apply(
            lambda x: any(tag in x for tag in tags) if x else False
        )
        results = results[mask]
        results = results.head(limit)
        
        return self._results_to_records(results)
    
    def query_by_app(
        self,
        app_name: str,
        limit: int = 50,
        table_name: str = "timeindex"
    ) -> List[Dict[str, Any]]:
        """
        按应用名称查询记录
        
        Args:
            app_name: 应用名称
            limit: 返回记录数限制
            table_name: 表名
            
        Returns:
            记录列表
        """
        table = self.get_table(table_name)
        
        results = table.search().to_pandas()
        results = results[results["primary_app"] == app_name]
        results = results.head(limit)
        
        return self._results_to_records(results)
    
    def semantic_search(
        self,
        query: str,
        query_vector: Optional[List[float]] = None,
        limit: int = 10,
        table_name: str = "timeindex"
    ) -> List[Dict[str, Any]]:
        """
        语义搜索
        
        Args:
            query: 搜索查询文本
            query_vector: 查询向量 (如果为 None，需要外部提供嵌入)
            limit: 返回记录数限制
            table_name: 表名
            
        Returns:
            记录列表
        """
        table = self.get_table(table_name)
        
        if query_vector:
            results = table.search(query_vector).limit(limit).to_pandas()
        else:
            # 如果没有向量，回退到全文搜索
            results = table.search().to_pandas()
            results = results[results["summary"].str.contains(query, case=False, na=False)]
            results = results.head(limit)
        
        return self._results_to_records(results)
    
    def get_pending_retag_records(
        self,
        batch_size: int = 20,
        table_name: str = "timeindex"
    ) -> List[Dict[str, Any]]:
        """
        获取待重打标的记录
        
        条件: refined_tags 为 NULL 的记录
        
        Args:
            batch_size: 批次大小
            table_name: 表名
            
        Returns:
            待重打标记录列表
        """
        table = self.get_table(table_name)
        
        results = table.search().to_pandas()
        
        # 过滤未重打标的记录
        mask = results["refined_tags"].isna()
        results = results[mask]
        results = results.head(batch_size)
        
        return self._results_to_records(results)
    
    def delete_by_time_range(
        self,
        before_time: datetime,
        table_name: str = "timeindex"
    ) -> int:
        """
        删除指定时间之前的记录
        
        Args:
            before_time: 删除此时间之前的记录
            table_name: 表名
            
        Returns:
            删除的记录数
        """
        with self._lock:
            table = self.get_table(table_name)
            
            # 先查询
            results = table.search().to_pandas()
            before_str = before_time.isoformat()
            to_delete = results[results["timestamp"] < before_str]
            count = len(to_delete)
            
            if count > 0:
                # 删除
                ids = to_delete["id"].tolist()
                for record_id in ids:
                    table.delete(f"id = '{record_id}'")
                
                logger.info(f"Deleted {count} records before {before_time}")
            
            return count
    
    def get_record_count(self, table_name: str = "timeindex") -> int:
        """获取记录总数"""
        table = self.get_table(table_name)
        results = table.search().to_pandas()
        return len(results)
    
    def cleanup_expired_records(
        self,
        table_name: str = "timeindex"
    ) -> int:
        """
        清理过期记录
        
        根据 rag_keepalive 和 rag_timeout 配置自动清理
        
        Args:
            table_name: 表名
            
        Returns:
            清理的记录数
        """
        keepalive_mode = config.rag_keepalive
        timeout_days = config.rag_timeout
        
        if keepalive_mode == "forever":
            logger.info("RAG keepalive is 'forever', skipping cleanup")
            return 0
        
        if keepalive_mode == "auto" and timeout_days is None:
            # 自动模式默认保留 30 天
            timeout_days = 30
        
        if timeout_days is None:
            return 0
        
        cutoff_time = datetime.now() - timedelta(days=timeout_days)
        
        logger.info(f"Cleaning up records before {cutoff_time} (timeout: {timeout_days} days)")
        return self.delete_by_time_range(cutoff_time, table_name)
    
    def _prepare_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """
        准备记录用于插入
        
        Args:
            record: 原始记录
            
        Returns:
            处理后的记录
        """
        import json
        
        # 确保必要字段存在
        data = {
            "id": record.get("id", f"rec_{datetime.now().timestamp()}"),
            "timestamp": record.get("timestamp", datetime.now().isoformat()),
            "summary": record.get("summary", ""),
            "tags": record.get("tags", []),
            "confidence": float(record.get("confidence", 0.0)),
            "primary_app": record.get("primary_app", "unknown"),
            "active_windows": [
                json.dumps(w) if isinstance(w, dict) else str(w)
                for w in record.get("active_windows", [])
            ],
            "process_events": [
                json.dumps(e) if isinstance(e, dict) else str(e)
                for e in record.get("process_events", [])
            ],
            "hardware": json.dumps(record.get("hardware", {})),
            "refined_tags": record.get("refined_tags"),
            "refined_summary": record.get("refined_summary"),
            "cluster_id": record.get("cluster_id"),
            "vector": record.get("vector", [0.0] * self._vector_dim),
        }
        
        return data
    
    def _results_to_records(self, df) -> List[Dict[str, Any]]:
        """
        将 Pandas DataFrame 结果转换为记录列表
        
        Args:
            df: Pandas DataFrame
            
        Returns:
            记录列表
        """
        import json
        
        records = []
        for _, row in df.iterrows():
            record = {
                "id": row.get("id", ""),
                "timestamp": row.get("timestamp", ""),
                "summary": row.get("summary", ""),
                "tags": row.get("tags", []) if row.get("tags") is not None else [],
                "confidence": float(row.get("confidence", 0.0)),
                "primary_app": row.get("primary_app", "unknown"),
                "active_windows": row.get("active_windows", []),
                "process_events": row.get("process_events", []),
                "hardware": {},
                "refined_tags": row.get("refined_tags"),
                "refined_summary": row.get("refined_summary"),
                "cluster_id": row.get("cluster_id"),
            }
            
            # 解析 hardware JSON
            hw_str = row.get("hardware", "{}")
            if hw_str:
                try:
                    record["hardware"] = json.loads(hw_str)
                except json.JSONDecodeError:
                    record["hardware"] = {}
            
            records.append(record)
        
        return records
    
    def close(self):
        """关闭数据库连接"""
        self._db = None
        self._table = None
        logger.info("VectorStore connection closed")


class TimeIndexStore:
    """
    TimeIndex 专用存储接口
    
    提供更高级别的 API，专门用于 TimeIndex 的活动记录管理。
    内部使用 VectorStore 实现。
    """
    
    def __init__(self, db_path: Optional[str] = None):
        """
        初始化 TimeIndex 存储
        
        Args:
            db_path: LanceDB 数据库路径
        """
        self._store = VectorStore(db_path=db_path)
    
    @property
    def store(self) -> VectorStore:
        """获取底层 VectorStore 实例"""
        return self._store
    
    def add_activity_record(self, record: Dict[str, Any]) -> str:
        """
        添加活动记录
        
        Args:
            record: 活动记录字典
            
        Returns:
            记录 ID
        """
        return self._store.add(record)
    
    def add_activity_batch(self, records: List[Dict[str, Any]]) -> int:
        """
        批量添加活动记录
        
        Args:
            records: 活动记录列表
            
        Returns:
            添加的记录数
        """
        return self._store.add_batch(records)
    
    def get_activities_in_range(
        self,
        start_time: datetime,
        end_time: datetime,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        获取指定时间范围内的活动
        
        Args:
            start_time: 开始时间
            end_time: 结束时间
            limit: 返回记录数限制
            
        Returns:
            活动记录列表
        """
        return self._store.query_by_time_range(start_time, end_time, limit)
    
    def get_activities_by_tags(
        self,
        tags: List[str],
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        按标签获取活动
        
        Args:
            tags: 标签列表
            limit: 返回记录数限制
            
        Returns:
            活动记录列表
        """
        return self._store.query_by_tags(tags, limit)
    
    def get_activities_by_app(
        self,
        app_name: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        按应用获取活动
        
        Args:
            app_name: 应用名称
            limit: 返回记录数限制
            
        Returns:
            活动记录列表
        """
        return self._store.query_by_app(app_name, limit)
    
    def search_activities(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        搜索活动 (语义搜索)
        
        Args:
            query: 搜索查询
            limit: 返回记录数限制
            
        Returns:
            活动记录列表
        """
        return self._store.semantic_search(query, limit=limit)
    
    def get_pending_retag(self, batch_size: int = 20) -> List[Dict[str, Any]]:
        """
        获取待重打标的记录
        
        Args:
            batch_size: 批次大小
            
        Returns:
            待重打标记录列表
        """
        return self._store.get_pending_retag_records(batch_size)
    
    def update_retag_records(self, records: List[Dict[str, Any]]) -> int:
        """
        更新重打标后的记录
        
        Args:
            records: 重打标后的记录列表
            
        Returns:
            更新的记录数
        """
        return self._store.update_batch(records)
    
    def cleanup(self) -> int:
        """
        清理过期记录
        
        Returns:
            清理的记录数
        """
        return self._store.cleanup_expired_records()
    
    def get_count(self) -> int:
        """获取记录总数"""
        return self._store.get_record_count()
    
    def close(self):
        """关闭存储"""
        self._store.close()


# 全局存储实例
timeindex_store = TimeIndexStore()
