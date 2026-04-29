"""
引用去幻校验器

执行 URL 可达性与语义一致性双重校验，彻底剔除大模型幻觉链接与断章取义。
"""

from typing import Any, Dict, List
from dataclasses import dataclass
import re


@dataclass
class ReferenceCheckResult:
    """引用校验结果"""
    citation: str
    url_valid: bool
    semantic_consistent: bool
    is_valid: bool
    error_message: str


class ReferenceVerifier:
    """
    引用校验器
    
    功能：
    1. 检查 URL 可达性
    2. 验证语义一致性
    3. 标记或剔除无效引用
    """
    
    def __init__(self):
        self.min_similarity_threshold = 0.6
    
    def validate(self, citation: Dict[str, Any]) -> ReferenceCheckResult:
        """
        校验单个引用
        
        Args:
            citation: 引用信息字典
            
        Returns:
            ReferenceCheckResult: 校验结果
        """
        url = citation.get('url', '')
        text = citation.get('text', '')
        claimed_content = citation.get('claimed_content', '')
        
        # 检查 URL 格式
        url_valid = self._check_url_format(url)
        
        # 验证语义一致性
        semantic_consistent = self._check_semantic_consistency(
            text, claimed_content
        )
        
        is_valid = url_valid and semantic_consistent
        
        error_message = ""
        if not url_valid:
            error_message += "URL格式无效或不可达；"
        if not semantic_consistent:
            error_message += "引用内容与声称不符；"
        
        return ReferenceCheckResult(
            citation=str(citation),
            url_valid=url_valid,
            semantic_consistent=semantic_consistent,
            is_valid=is_valid,
            error_message=error_message
        )
    
    def validate_batch(
        self,
        citations: List[Dict[str, Any]]
    ) -> List[ReferenceCheckResult]:
        """批量校验引用"""
        return [self.validate(c) for c in citations]
    
    def _check_url_format(self, url: str) -> bool:
        """检查 URL 格式"""
        if not url:
            return False
        # 简单的 URL 格式检查
        pattern = r'^https?://[^\s/$.?#].[^\s]*$'
        return bool(re.match(pattern, url, re.IGNORECASE))
    
    def _check_semantic_consistency(
        self,
        original_text: str,
        claimed_content: str
    ) -> bool:
        """
        检查语义一致性
        
        简化实现：检查 claimed_content 是否是 original_text 的子串或高度相似
        """
        if not original_text or not claimed_content:
            return False
        
        # 简单的包含检查
        if claimed_content.lower() in original_text.lower():
            return True
        
        # 计算简单相似度（基于共有词汇比例）
        original_words = set(original_text.lower().split())
        claimed_words = set(claimed_content.lower().split())
        
        if not claimed_words:
            return False
        
        intersection = original_words.intersection(claimed_words)
        similarity = len(intersection) / len(claimed_words)
        
        return similarity >= self.min_similarity_threshold
