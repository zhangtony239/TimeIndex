"""
db/embedding_provider.py - Embedding 提供者

对接 OpenAI 兼容的 v1/embeddings 接口，为活动记录提供向量化支持。
"""

import logging
from typing import List, Optional
from openai import OpenAI
from ..utils.config import config

logger = logging.getLogger(__name__)

class EmbeddingProvider:
    """
    Embedding 提供者，负责调用远程接口获取文本向量
    """
    
    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None
    ):
        """
        初始化 Embedding 提供者
        
        Args:
            base_url: API 地址
            api_key: API 密钥
            model: 使用的 Embedding 模型名称
        """
        self.base_url = base_url or config.llm_base_url
        self.api_key = api_key or config.llm_api_key
        self.model = model or config.embedding_model
        
        # 初始化 OpenAI 客户端
        self.client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key
        )
        
        logger.info(f"EmbeddingProvider initialized with base_url={self.base_url}, model={self.model}")

    def get_embedding(self, text: str) -> List[float]:
        """
        获取单个文本的向量
        
        Args:
            text: 待向量化的文本
            
        Returns:
            向量列表
        """
        if not text:
            return []
            
        try:
            response = self.client.embeddings.create(
                input=text,
                model=self.model
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Error getting embedding: {e}")
            return []

    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        批量获取文本向量
        
        Args:
            texts: 待向量化的文本列表
            
        Returns:
            向量列表的列表
        """
        if not texts:
            return []
            
        try:
            response = self.client.embeddings.create(
                input=texts,
                model=self.model
            )
            # 保持顺序
            embeddings = [item.embedding for item in response.data]
            return embeddings
        except Exception as e:
            logger.error(f"Error getting batch embeddings: {e}")
            return [[] for _ in texts]

# 全局 Embedding 提供者实例
embedding_provider = EmbeddingProvider()
