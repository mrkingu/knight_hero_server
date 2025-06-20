"""
敏感词过滤器
Sensitive Word Filter

作者: lx
日期: 2025-06-18
描述: 使用AC自动机算法实现高效的敏感词过滤功能
"""
from typing import List, Dict, Set, Tuple, Optional
import logging
import asyncio
from collections import deque, defaultdict
import aiofiles
import re


class ACAutomaton:
    """AC自动机算法实现"""
    
    class TrieNode:
        """字典树节点"""
        
        def __init__(self):
            self.children: Dict[str, 'ACAutomaton.TrieNode'] = {}
            self.failure: Optional['ACAutomaton.TrieNode'] = None
            self.output: List[str] = []  # 匹配到的敏感词
            self.is_end: bool = False
    
    def __init__(self):
        """初始化AC自动机"""
        self.root = self.TrieNode()
        self._compiled = False
        
    def add_word(self, word: str) -> None:
        """
        添加敏感词
        
        Args:
            word: 敏感词
        """
        if not word:
            return
            
        node = self.root
        for char in word:
            if char not in node.children:
                node.children[char] = self.TrieNode()
            node = node.children[char]
        
        node.is_end = True
        node.output.append(word)
        self._compiled = False
    
    def build_failure_links(self) -> None:
        """构建失败指针"""
        # BFS构建失败指针
        queue = deque()
        
        # 第一层节点的失败指针指向根节点
        for child in self.root.children.values():
            child.failure = self.root
            queue.append(child)
        
        while queue:
            current = queue.popleft()
            
            for char, child in current.children.items():
                queue.append(child)
                
                # 查找失败指针
                failure = current.failure
                while failure is not None and char not in failure.children:
                    failure = failure.failure
                
                if failure is not None:
                    child.failure = failure.children[char]
                else:
                    child.failure = self.root
                
                # 继承失败指针的输出
                child.output.extend(child.failure.output)
        
        self._compiled = True
    
    def search(self, text: str) -> List[Tuple[int, str]]:
        """
        搜索文本中的敏感词
        
        Args:
            text: 待搜索的文本
            
        Returns:
            匹配结果列表，每个元素为(位置, 敏感词)
        """
        if not self._compiled:
            self.build_failure_links()
        
        results = []
        node = self.root
        
        for i, char in enumerate(text):
            # 查找包含当前字符的节点
            while node is not None and char not in node.children:
                node = node.failure
            
            if node is None:
                node = self.root
                continue
            
            node = node.children[char]
            
            # 输出所有匹配的敏感词
            for word in node.output:
                start_pos = i - len(word) + 1
                results.append((start_pos, word))
        
        return results


class WordFilter:
    """敏感词过滤器"""
    
    def __init__(self, 
                 default_words: Optional[List[str]] = None,
                 replacement_char: str = "*"):
        """
        初始化敏感词过滤器
        
        Args:
            default_words: 默认敏感词列表
            replacement_char: 替换字符
        """
        self._automaton = ACAutomaton()
        self._replacement_char = replacement_char
        self._word_sets: Dict[str, Set[str]] = defaultdict(set)  # 分类敏感词
        self._logger = logging.getLogger(__name__)
        
        # 添加默认敏感词
        if default_words:
            self.add_words(default_words)
    
    def add_word(self, word: str, category: str = "default") -> None:
        """
        添加单个敏感词
        
        Args:
            word: 敏感词
            category: 分类名称
        """
        if not word:
            return
            
        word = word.strip().lower()
        if word:
            self._automaton.add_word(word)
            self._word_sets[category].add(word)
    
    def add_words(self, words: List[str], category: str = "default") -> None:
        """
        批量添加敏感词
        
        Args:
            words: 敏感词列表
            category: 分类名称
        """
        for word in words:
            self.add_word(word, category)
    
    def remove_word(self, word: str, category: str = "default") -> bool:
        """
        移除敏感词
        
        Args:
            word: 敏感词
            category: 分类名称
            
        Returns:
            是否移除成功
        """
        word = word.strip().lower()
        if word in self._word_sets[category]:
            self._word_sets[category].remove(word)
            # 重建自动机
            self._rebuild_automaton()
            return True
        return False
    
    def filter_text(self, text: str) -> Tuple[str, List[str]]:
        """
        过滤文本中的敏感词
        
        Args:
            text: 原始文本
            
        Returns:
            (过滤后的文本, 检测到的敏感词列表)
        """
        if not text:
            return text, []
        
        # 搜索敏感词
        matches = self._automaton.search(text.lower())
        
        if not matches:
            return text, []
        
        # 按位置排序并合并重叠的匹配
        matches.sort(key=lambda x: x[0])
        merged_matches = self._merge_overlapping_matches(matches)
        
        # 替换敏感词
        filtered_text = self._replace_words(text, merged_matches)
        
        # 收集检测到的敏感词
        detected_words = [word for _, word in merged_matches]
        
        return filtered_text, detected_words
    
    def contains_sensitive_word(self, text: str) -> bool:
        """
        检查文本是否包含敏感词
        
        Args:
            text: 待检查的文本
            
        Returns:
            是否包含敏感词
        """
        if not text:
            return False
        
        matches = self._automaton.search(text.lower())
        return len(matches) > 0
    
    def get_sensitive_words(self, text: str) -> List[str]:
        """
        获取文本中的所有敏感词
        
        Args:
            text: 待检查的文本
            
        Returns:
            敏感词列表
        """
        if not text:
            return []
        
        matches = self._automaton.search(text.lower())
        return list(set(word for _, word in matches))
    
    async def load_words_from_file(self, 
                                   file_path: str, 
                                   category: str = "file", 
                                   encoding: str = "utf-8") -> bool:
        """
        从文件加载敏感词
        
        Args:
            file_path: 文件路径
            category: 分类名称
            encoding: 文件编码
            
        Returns:
            加载是否成功
        """
        try:
            async with aiofiles.open(file_path, 'r', encoding=encoding) as f:
                content = await f.read()
                
            # 按行分割敏感词
            words = []
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith('#'):  # 忽略注释行
                    words.append(line)
            
            if words:
                self.add_words(words, category)
                self._logger.info(f"从文件 {file_path} 加载了 {len(words)} 个敏感词")
                return True
            
        except Exception as e:
            self._logger.error(f"加载敏感词文件失败: {e}, file: {file_path}")
        
        return False
    
    async def save_words_to_file(self, 
                                file_path: str, 
                                category: str = "all",
                                encoding: str = "utf-8") -> bool:
        """
        保存敏感词到文件
        
        Args:
            file_path: 文件路径
            category: 分类名称，"all" 表示所有分类
            encoding: 文件编码
            
        Returns:
            保存是否成功
        """
        try:
            words = set()
            
            if category == "all":
                for word_set in self._word_sets.values():
                    words.update(word_set)
            else:
                words = self._word_sets[category]
            
            if words:
                content = '\n'.join(sorted(words))
                async with aiofiles.open(file_path, 'w', encoding=encoding) as f:
                    await f.write(content)
                    
                self._logger.info(f"保存了 {len(words)} 个敏感词到文件 {file_path}")
                return True
                
        except Exception as e:
            self._logger.error(f"保存敏感词文件失败: {e}, file: {file_path}")
        
        return False
    
    def get_statistics(self) -> Dict[str, int]:
        """
        获取过滤器统计信息
        
        Returns:
            统计信息字典
        """
        stats = {
            "total_words": sum(len(words) for words in self._word_sets.values()),
            "categories": len(self._word_sets)
        }
        
        for category, words in self._word_sets.items():
            stats[f"category_{category}"] = len(words)
        
        return stats
    
    def clear_category(self, category: str) -> bool:
        """
        清空指定分类的敏感词
        
        Args:
            category: 分类名称
            
        Returns:
            是否清空成功
        """
        if category in self._word_sets:
            del self._word_sets[category]
            self._rebuild_automaton()
            return True
        return False
    
    def clear_all(self) -> None:
        """清空所有敏感词"""
        self._word_sets.clear()
        self._automaton = ACAutomaton()
    
    # ========== 私有方法 ==========
    
    def _rebuild_automaton(self) -> None:
        """重建AC自动机"""
        self._automaton = ACAutomaton()
        
        # 重新添加所有敏感词
        for word_set in self._word_sets.values():
            for word in word_set:
                self._automaton.add_word(word)
    
    def _merge_overlapping_matches(self, 
                                  matches: List[Tuple[int, str]]) -> List[Tuple[int, str]]:
        """
        合并重叠的匹配结果，保留最长的匹配
        
        Args:
            matches: 匹配结果列表
            
        Returns:
            合并后的匹配结果
        """
        if not matches:
            return []
        
        # 按位置和长度排序
        matches.sort(key=lambda x: (x[0], -len(x[1])))
        
        merged = []
        current_end = -1
        
        for pos, word in matches:
            word_end = pos + len(word) - 1
            
            # 如果当前匹配不与之前的重叠，则添加
            if pos > current_end:
                merged.append((pos, word))
                current_end = word_end
            # 如果重叠但当前匹配更长，则替换
            elif word_end > current_end and len(word) > len(merged[-1][1]):
                merged[-1] = (pos, word)
                current_end = word_end
        
        return merged
    
    def _replace_words(self, text: str, matches: List[Tuple[int, str]]) -> str:
        """
        替换文本中的敏感词
        
        Args:
            text: 原始文本
            matches: 匹配结果列表
            
        Returns:
            替换后的文本
        """
        if not matches:
            return text
        
        # 从后往前替换，避免位置偏移
        matches.sort(key=lambda x: x[0], reverse=True)
        
        result = list(text)
        
        for pos, word in matches:
            word_len = len(word)
            replacement = self._replacement_char * word_len
            
            # 替换对应位置的字符
            for i in range(word_len):
                if pos + i < len(result):
                    result[pos + i] = replacement[i]
        
        return ''.join(result)


# 默认敏感词列表
DEFAULT_SENSITIVE_WORDS = [
    # 政治敏感词
    "法轮功", "天安门", "六四", "达赖",
    
    # 色情词汇
    "性交", "做爱", "色情", "裸体",
    
    # 暴力词汇
    "杀死", "自杀", "爆炸", "恐怖主义",
    
    # 赌博词汇
    "赌博", "博彩", "彩票", "下注",
    
    # 辱骂词汇
    "傻逼", "fuck", "shit", "操你妈",
    
    # 广告词汇
    "加微信", "扫码", "代练", "外挂"
]


# 全局过滤器实例
_word_filter: Optional[WordFilter] = None


def get_word_filter() -> WordFilter:
    """获取敏感词过滤器实例"""
    global _word_filter
    if _word_filter is None:
        _word_filter = WordFilter(default_words=DEFAULT_SENSITIVE_WORDS)
    return _word_filter


async def initialize_word_filter(custom_words_file: Optional[str] = None) -> WordFilter:
    """
    初始化敏感词过滤器
    
    Args:
        custom_words_file: 自定义敏感词文件路径
        
    Returns:
        过滤器实例
    """
    filter_instance = get_word_filter()
    
    # 加载自定义敏感词文件
    if custom_words_file:
        await filter_instance.load_words_from_file(custom_words_file, "custom")
    
    return filter_instance