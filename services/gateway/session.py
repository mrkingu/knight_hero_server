"""
会话对象模块
Session Object Module

作者: lx
日期: 2025-06-18
描述: 负责管理WebSocket会话，包括Session对象定义、雪花算法生成ID、属性管理等
"""
import time
import asyncio
from typing import Dict, Any, Optional, TYPE_CHECKING
from dataclasses import dataclass, field
from enum import Enum

from common.utils import generate_id

if TYPE_CHECKING:
    from .connection import Connection


class SessionState(Enum):
    """会话状态枚举"""
    CONNECTING = "connecting"      # 连接中
    CONNECTED = "connected"        # 已连接
    AUTHENTICATED = "authenticated"  # 已认证
    DISCONNECTED = "disconnected"  # 已断开
    EXPIRED = "expired"           # 已过期


@dataclass
class SessionAttributes:
    """会话属性"""
    user_id: Optional[str] = None          # 用户ID
    player_id: Optional[str] = None        # 玩家ID
    device_id: Optional[str] = None        # 设备ID
    ip_address: Optional[str] = None       # IP地址
    user_agent: Optional[str] = None       # 用户代理
    platform: Optional[str] = None        # 平台类型
    version: Optional[str] = None          # 客户端版本
    language: Optional[str] = None         # 语言设置
    timezone: Optional[str] = None         # 时区
    metadata: Dict[str, Any] = field(default_factory=dict)  # 扩展元数据


class Session:
    """
    WebSocket会话对象
    
    管理单个WebSocket连接的会话信息，包括身份认证、权限控制、状态管理等
    """
    
    def __init__(self, connection: 'Connection'):
        """
        初始化会话对象
        
        Args:
            connection: WebSocket连接对象
        """
        # 基础信息
        self.id = generate_id()                    # 雪花算法生成的唯一ID
        self.connection = connection               # 关联的连接对象
        self.state = SessionState.CONNECTING       # 会话状态
        
        # 时间信息
        self.created_at = time.time()             # 创建时间
        self.last_activity = time.time()          # 最后活跃时间
        self.authenticated_at: Optional[float] = None  # 认证时间
        self.expires_at: Optional[float] = None   # 过期时间
        
        # 会话属性
        self.attributes = SessionAttributes()      # 会话属性
        
        # 权限信息
        self.permissions: set[str] = set()        # 权限集合
        self.roles: set[str] = set()              # 角色集合
        
        # 统计信息
        self.message_count = 0                    # 消息计数
        self.last_ping = 0.0                     # 最后ping时间
        self.last_pong = 0.0                     # 最后pong时间
        
        # 扩展数据
        self.data: Dict[str, Any] = {}           # 临时数据存储
        
        # 异步锁
        self._lock = asyncio.Lock()
    
    @property
    def is_authenticated(self) -> bool:
        """检查是否已认证"""
        return self.state == SessionState.AUTHENTICATED
    
    @property
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self.state in (SessionState.CONNECTED, SessionState.AUTHENTICATED)
    
    @property
    def is_expired(self) -> bool:
        """检查是否已过期"""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at
    
    @property
    def duration(self) -> float:
        """获取会话持续时间（秒）"""
        return time.time() - self.created_at
    
    @property
    def idle_time(self) -> float:
        """获取空闲时间（秒）"""
        return time.time() - self.last_activity
    
    async def authenticate(self, user_id: str, player_id: str = None, **kwargs) -> bool:
        """
        认证会话
        
        Args:
            user_id: 用户ID
            player_id: 玩家ID
            **kwargs: 其他认证信息
            
        Returns:
            认证是否成功
        """
        async with self._lock:
            try:
                # 更新认证信息
                self.attributes.user_id = user_id
                self.attributes.player_id = player_id or user_id
                self.authenticated_at = time.time()
                
                # 设置过期时间（30分钟）
                self.expires_at = time.time() + 30 * 60
                
                # 更新状态
                self.state = SessionState.AUTHENTICATED
                self.update_activity()
                
                # 更新其他属性
                for key, value in kwargs.items():
                    if hasattr(self.attributes, key):
                        setattr(self.attributes, key, value)
                    else:
                        self.attributes.metadata[key] = value
                
                return True
                
            except Exception as e:
                # 认证失败，记录错误
                self.data['auth_error'] = str(e)
                return False
    
    async def logout(self) -> None:
        """登出会话"""
        async with self._lock:
            self.state = SessionState.DISCONNECTED
            self.expires_at = time.time()  # 立即过期
            
            # 清理敏感信息
            self.attributes.user_id = None
            self.attributes.player_id = None
            self.permissions.clear()
            self.roles.clear()
    
    def update_activity(self) -> None:
        """更新活跃时间"""
        self.last_activity = time.time()
        self.message_count += 1
    
    def update_ping(self) -> None:
        """更新ping时间"""
        self.last_ping = time.time()
    
    def update_pong(self) -> None:
        """更新pong时间"""
        self.last_pong = time.time()
    
    async def renew(self, duration: int = 30 * 60) -> bool:
        """
        续期会话
        
        Args:
            duration: 续期时长（秒），默认30分钟
            
        Returns:
            续期是否成功
        """
        async with self._lock:
            if self.is_expired or not self.is_authenticated:
                return False
            
            # 更新过期时间
            self.expires_at = time.time() + duration
            self.update_activity()
            return True
    
    def add_permission(self, permission: str) -> None:
        """添加权限"""
        self.permissions.add(permission)
    
    def remove_permission(self, permission: str) -> None:
        """移除权限"""
        self.permissions.discard(permission)
    
    def has_permission(self, permission: str) -> bool:
        """检查是否有指定权限"""
        return permission in self.permissions
    
    def add_role(self, role: str) -> None:
        """添加角色"""
        self.roles.add(role)
    
    def remove_role(self, role: str) -> None:
        """移除角色"""
        self.roles.discard(role)
    
    def has_role(self, role: str) -> bool:
        """检查是否有指定角色"""
        return role in self.roles
    
    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典格式（用于序列化存储）
        
        Returns:
            会话信息字典
        """
        return {
            'id': str(self.id),
            'state': self.state.value,
            'created_at': self.created_at,
            'last_activity': self.last_activity,
            'authenticated_at': self.authenticated_at,
            'expires_at': self.expires_at,
            'attributes': {
                'user_id': self.attributes.user_id,
                'player_id': self.attributes.player_id,
                'device_id': self.attributes.device_id,
                'ip_address': self.attributes.ip_address,
                'user_agent': self.attributes.user_agent,
                'platform': self.attributes.platform,
                'version': self.attributes.version,
                'language': self.attributes.language,
                'timezone': self.attributes.timezone,
                'metadata': self.attributes.metadata
            },
            'permissions': list(self.permissions),
            'roles': list(self.roles),
            'message_count': self.message_count,
            'last_ping': self.last_ping,
            'last_pong': self.last_pong,
            'data': self.data
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any], connection: 'Connection') -> 'Session':
        """
        从字典创建会话对象（用于反序列化）
        
        Args:
            data: 会话信息字典
            connection: WebSocket连接对象
            
        Returns:
            会话对象
        """
        session = cls(connection)
        
        # 基础信息
        session.id = int(data['id'])
        session.state = SessionState(data['state'])
        session.created_at = data['created_at']
        session.last_activity = data['last_activity']
        session.authenticated_at = data.get('authenticated_at')
        session.expires_at = data.get('expires_at')
        
        # 属性信息
        attrs = data.get('attributes', {})
        session.attributes.user_id = attrs.get('user_id')
        session.attributes.player_id = attrs.get('player_id')
        session.attributes.device_id = attrs.get('device_id')
        session.attributes.ip_address = attrs.get('ip_address')
        session.attributes.user_agent = attrs.get('user_agent')
        session.attributes.platform = attrs.get('platform')
        session.attributes.version = attrs.get('version')
        session.attributes.language = attrs.get('language')
        session.attributes.timezone = attrs.get('timezone')
        session.attributes.metadata = attrs.get('metadata', {})
        
        # 权限信息
        session.permissions = set(data.get('permissions', []))
        session.roles = set(data.get('roles', []))
        
        # 统计信息
        session.message_count = data.get('message_count', 0)
        session.last_ping = data.get('last_ping', 0.0)
        session.last_pong = data.get('last_pong', 0.0)
        session.data = data.get('data', {})
        
        return session
    
    def __str__(self) -> str:
        """字符串表示"""
        return (f"Session(id={self.id}, state={self.state.value}, "
                f"user_id={self.attributes.user_id}, duration={self.duration:.2f}s)")
    
    def __repr__(self) -> str:
        """详细字符串表示"""
        return self.__str__()