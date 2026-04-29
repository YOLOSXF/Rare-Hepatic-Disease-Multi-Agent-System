"""
PubMed 搜索工具
参考 DeepRare 的 search_pubmed.py 实现
"""

from typing import List, Dict, Optional
import requests
from loguru import logger


class PubMedSearchTool:
    """
    PubMed 文献搜索工具
    
    使用 NCBI E-utilities API 搜索生物医学文献
    """
    
    def __init__(self, email: str = "medical-agent@example.com", api_key: Optional[str] = None):
        """
        初始化工具
        
        Args:
            email: NCBI 要求的邮箱地址
            api_key: NCBI API key（可选，提高请求限制）
        """
        self.email = email
        self.api_key = api_key
        self.base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
        self.session = requests.Session()
    
    def search(self, query: str, max_results: int = 10) -> List[Dict]:
        """
        搜索 PubMed 文献
        
        Args:
            query: 搜索查询
            max_results: 最大返回结果数
        
        Returns:
            文献列表
        """
        try:
            # 1. 搜索获取 PMIDs
            pmids = self._search_pmids(query, max_results)
            
            if not pmids:
                logger.warning(f"No PubMed results for: {query}")
                return []
            
            # 2. 获取文献详情
            articles = self._fetch_articles(pmids)
            
            return articles
            
        except Exception as e:
            logger.error(f"PubMed search failed: {e}")
            return []
    
    def _search_pmids(self, query: str, max_results: int) -> List[str]:
        """搜索获取 PMID 列表"""
        try:
            url = f"{self.base_url}/esearch.fcgi"
            params = {
                "db": "pubmed",
                "term": query,
                "retmax": max_results,
                "retmode": "json",
                "email": self.email
            }
            
            if self.api_key:
                params["api_key"] = self.api_key
            
            response = self.session.get(url, params=params)
            data = response.json()
            
            pmids = data.get("esearchresult", {}).get("idlist", [])
            return [str(pmid) for pmid in pmids]
            
        except Exception as e:
            logger.error(f"PMID search failed: {e}")
            return []
    
    def _fetch_articles(self, pmids: List[str]) -> List[Dict]:
        """获取文献详情"""
        if not pmids:
            return []
        
        try:
            url = f"{self.base_url}/esummary.fcgi"
            params = {
                "db": "pubmed",
                "id": ",".join(pmids),
                "retmode": "json",
                "email": self.email
            }
            
            if self.api_key:
                params["api_key"] = self.api_key
            
            response = self.session.get(url, params=params)
            data = response.json()
            
            articles = []
            result = data.get("result", {})
            
            for pmid in pmids:
                if pmid in result:
                    article = result[pmid]
                    articles.append({
                        "pmid": pmid,
                        "title": article.get("title", ""),
                        "authors": [author.get("name", "") for author in article.get("authors", [])],
                        "journal": article.get("fulljournalname", ""),
                        "pubdate": article.get("pubdate", ""),
                        "doi": article.get("doi", ""),
                        "abstract": self._get_abstract(pmid)
                    })
            
            return articles
            
        except Exception as e:
            logger.error(f"Article fetch failed: {e}")
            return []
    
    def _get_abstract(self, pmid: str) -> str:
        """获取摘要"""
        try:
            url = f"{self.base_url}/efetch.fcgi"
            params = {
                "db": "pubmed",
                "id": pmid,
                "rettype": "abstract",
                "retmode": "text",
                "email": self.email
            }
            
            response = self.session.get(url, params=params)
            return response.text[:500]  # 限制长度
            
        except Exception as e:
            logger.error(f"Abstract fetch failed: {e}")
            return ""
    
    def search_with_summary(self, query: str, max_results: int = 5) -> List[str]:
        """
        搜索并生成总结
        
        Args:
            query: 搜索查询
            max_results: 最大结果数
        
        Returns:
            格式化的文献信息列表
        """
        articles = self.search(query, max_results)
        
        summaries = []
        for article in articles:
            summary = (
                f"Title: {article['title']}\n"
                f"Authors: {', '.join(article['authors'][:3])}{' et al.' if len(article['authors']) > 3 else ''}\n"
                f"Journal: {article['journal']}\n"
                f"Year: {article['pubdate']}\n"
                f"PMID: {article['pmid']}\n"
                f"Abstract: {article['abstract'][:300]}..."
            )
            summaries.append(summary)
        
        return summaries
