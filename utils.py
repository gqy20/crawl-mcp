#!/usr/bin/env python3
"""
工具模块
提供URL处理、文件命名等通用功能
"""

import re
from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime
from typing import Optional


class OutputPathGenerator:
    """输出路径生成器"""
    
    @staticmethod
    def sanitize_name(name: str) -> str:
        """
        清理名称，移除不安全字符
        
        Args:
            name: 原始名称
            
        Returns:
            清理后的安全名称
        """
        # 移除或替换不安全字符
        name = re.sub(r'[<>:"/\\|?*]', '_', name)
        # 移除多余的下划线
        name = re.sub(r'_+', '_', name)
        # 移除首尾下划线
        name = name.strip('_')
        # 限制长度
        return name[:100] if len(name) > 100 else name
    
    @staticmethod
    def extract_domain_info(url: str) -> tuple[str, str]:
        """
        从URL提取域名信息
        
        Args:
            url: 网页URL
            
        Returns:
            (domain, path) 元组
        """
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        path = parsed.path.strip('/')
        
        # 处理子域名
        if domain.startswith('www.'):
            domain = domain[4:]
        
        # 处理路径
        if not path:
            path = 'index'
        else:
            # 只取第一级路径作为标识
            path_parts = path.split('/')
            path = path_parts[0] if path_parts else 'index'
        
        return domain, path
    
    @classmethod
    def generate_output_dir(cls, url: str, crawl_type: str, 
                          base_dir: str = "output", 
                          include_timestamp: bool = False) -> Path:
        """
        生成输出目录路径
        
        Args:
            url: 目标URL
            crawl_type: 爬取类型 ('single' 或 'website')
            base_dir: 基础输出目录
            include_timestamp: 是否包含时间戳
            
        Returns:
            输出目录路径
        """
        domain, path = cls.extract_domain_info(url)
        
        # 构建目录名称
        dir_parts = [
            cls.sanitize_name(domain),
            cls.sanitize_name(path),
            crawl_type
        ]
        
        if include_timestamp:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            dir_parts.append(timestamp)
        
        dir_name = "_".join(dir_parts)
        return Path(base_dir) / dir_name
    
    @staticmethod
    def generate_filename(url: str, extension: str = ".md") -> str:
        """
        从URL生成文件名
        
        Args:
            url: 网页URL
            extension: 文件扩展名
            
        Returns:
            安全的文件名
        """
        parsed = urlparse(url)
        domain = parsed.netloc.replace(".", "_")
        path = parsed.path.replace("/", "_").replace(".", "_")
        
        if not path or path == "_":
            path = "index"
        
        filename = f"{domain}{path}"
        # 清理文件名
        filename = OutputPathGenerator.sanitize_name(filename)
        return f"{filename}{extension}"


class URLValidator:
    """URL验证器"""
    
    @staticmethod
    def is_valid_url(url: str) -> bool:
        """
        验证URL是否有效
        
        Args:
            url: 要验证的URL
            
        Returns:
            是否为有效URL
        """
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except Exception:
            return False
    
    @staticmethod
    def normalize_url(url: str) -> str:
        """
        标准化URL
        
        Args:
            url: 原始URL
            
        Returns:
            标准化后的URL
        """
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        parsed = urlparse(url)
        # 移除fragment
        normalized = parsed._replace(fragment='').geturl()
        return normalized


def create_output_directory(url: str, crawl_type: str, 
                          base_dir: str = "output",
                          include_timestamp: bool = False) -> Path:
    """
    创建输出目录的便捷函数
    
    Args:
        url: 目标URL
        crawl_type: 爬取类型
        base_dir: 基础目录
        include_timestamp: 是否包含时间戳
        
    Returns:
        创建的目录路径
    """
    output_dir = OutputPathGenerator.generate_output_dir(
        url, crawl_type, base_dir, include_timestamp
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir