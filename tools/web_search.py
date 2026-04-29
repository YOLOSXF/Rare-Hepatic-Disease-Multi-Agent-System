"""
网络搜索工具
参考 DeepRare 的 web_search.py 实现
"""

from typing import List, Dict, Optional
import requests
from loguru import logger


class WebSearchTool:
    """
    网络搜索工具
    
    支持多种搜索引擎：
    - DuckDuckGo
    - Bing
    - Google (需要 API key)
    """
    
    def __init__(self, search_engine: str = "duckduckgo", api_key: Optional[str] = None):
        """
        初始化搜索工具
        
        Args:
            search_engine: 搜索引擎类型
            api_key: API 密钥（如需要）
        """
        self.search_engine = search_engine
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def search(self, query: str, return_num: int = 5, read_content: bool = False) -> List[str]:
        """
        执行网络搜索
        
        Args:
            query: 搜索查询
            return_num: 返回结果数量
            read_content: 是否读取并总结网页内容
        
        Returns:
            搜索结果列表
        """
        try:
            if self.search_engine == "duckduckgo":
                results = self._duckduckgo_search(query, return_num)
            elif self.search_engine == "bing":
                results = self._bing_search(query, return_num)
            else:
                results = self._duckduckgo_search(query, return_num)
            
            if read_content:
                results = self._fetch_and_summarize(results[:3])
            
            return results
            
        except Exception as e:
            logger.error(f"Web search failed: {e}")
            return []
    
    def _duckduckgo_search(self, query: str, num: int) -> List[str]:
        """DuckDuckGo 搜索"""
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=num))
                return [f"{r['title']}: {r['body']}" for r in results]
        except ImportError:
            logger.warning("duckduckgo_search not installed, using fallback")
            return self._fallback_search(query, num)
        except Exception as e:
            logger.error(f"DuckDuckGo search error: {e}")
            return []
    
    def _bing_search(self, query: str, num: int) -> List[str]:
        """Bing 搜索（需要 API key）"""
        if not self.api_key:
            logger.warning("Bing API key not provided")
            return self._fallback_search(query, num)
        
        try:
            endpoint = "https://api.bing.microsoft.com/v7.0/search"
            params = {"q": query, "count": num}
            headers = {"Ocp-Apim-Subscription-Key": self.api_key}
            
            response = self.session.get(endpoint, params=params, headers=headers)
            data = response.json()
            
            results = []
            for result in data.get("webPages", {}).get("value", []):
                results.append(f"{result['name']}: {result['snippet']}")
            
            return results
            
        except Exception as e:
            logger.error(f"Bing search error: {e}")
            return []
    
    def _fallback_search(self, query: str, num: int) -> List[str]:
        """备用搜索（使用公开 API）"""
        try:
            # 使用 DuckDuckGo HTML 搜索（无需 API）
            url = "https://html.duckduckgo.com/html/"
            data = {"q": query}
            headers = {
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://duckduckgo.com/"
            }
            
            response = self.session.post(url, data=data, headers=headers)
            
            # 简单解析（实际应该用 BeautifulSoup）
            results = []
            if response.status_code == 200:
                # 这里简化处理，实际应该解析 HTML
                results.append(f"Search results for: {query}")
            
            return results[:num]
            
        except Exception as e:
            logger.error(f"Fallback search error: {e}")
            return [f"Search failed for: {query}"]
    
    def _fetch_and_summarize(self, results: List[str]) -> List[str]:
        """获取网页内容并总结"""
        # 实际实现应该：
        # 1. 从结果中提取 URL
        # 2. 使用 page_fetch 工具获取内容
        # 3. 使用 LLM 总结内容
        # 这里简化实现
        return results
