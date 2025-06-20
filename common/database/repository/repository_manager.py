"""
Repository管理器
控制Repository访问权限，禁止直接访问
作者: lx
日期: 2025-06-20
"""
import inspect
from typing import Dict, Any, Optional, Type

class RepositoryManager:
    """Repository管理器 - 单例模式，控制访问权限"""
    
    _instance: Optional['RepositoryManager'] = None
    _repositories: Dict[str, object] = {}
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, redis_client=None, mongo_client=None):
        """初始化仓库管理器"""
        # 防止重复初始化
        if hasattr(self, '_initialized'):
            return
            
        self.redis_client = redis_client
        self.mongo_client = mongo_client
        self._initialized = True
        
    async def initialize(self, operation_logger):
        """初始化仓库"""
        self.operation_logger = operation_logger
        
    def register_repository(self, name: str, repository: object):
        """
        注册Repository（仅内部使用）
        
        Args:
            name: Repository名称
            repository: Repository实例
            
        Raises:
            PermissionError: 如果调用者不是来自services包
        """
        # 检查调用者是否来自services包
        caller_frame = inspect.currentframe().f_back
        caller_module = inspect.getmodule(caller_frame)
        
        if caller_module and not caller_module.__name__.startswith('services.'):
            raise PermissionError(
                f"Repository can only be registered by services packages. "
                f"Called from: {caller_module.__name__}"
            )
        
        self._repositories[name] = repository
    
    def get_repository(self, name: str) -> object:
        """
        获取Repository（仅内部使用）
        
        Args:
            name: Repository名称
            
        Returns:
            Repository实例
            
        Raises:
            PermissionError: 如果调用者不是来自services包
        """
        # 检查调用者是否来自services包或common.database包（用于向后兼容）
        caller_frame = inspect.currentframe().f_back
        caller_module = inspect.getmodule(caller_frame)
        
        if caller_module:
            module_name = caller_module.__name__
            # 允许services包和common.database包访问
            if not (module_name.startswith('services.') or 
                   module_name.startswith('common.database.')):
                raise PermissionError(
                    f"Repository can only be accessed by services packages. "
                    f"Called from: {module_name}"
                )
        
        # 如果Repository不存在，尝试创建（向后兼容）
        if name not in self._repositories:
            if name == "players" or name == "player":
                if self.redis_client and self.mongo_client:
                    # 延迟导入避免循环依赖
                    from ..repositories.player_repository import PlayerRepository
                    self._repositories[name] = PlayerRepository(
                        self.redis_client, 
                        self.mongo_client
                    )
                else:
                    raise ValueError(f"Cannot create repository '{name}': missing database clients")
            else:
                raise ValueError(f"Unknown repository type: {name}")
                
        return self._repositories[name]
    
    def _get_repository_unsafe(self, name: str) -> object:
        """
        不安全的Repository访问（仅用于内部测试和迁移）
        
        Args:
            name: Repository名称
            
        Returns:
            Repository实例
        """
        return self._repositories.get(name)
    
    def list_repositories(self) -> Dict[str, str]:
        """
        列出所有已注册的Repository
        
        Returns:
            Repository名称和类型的字典
        """
        return {
            name: type(repo).__name__ 
            for name, repo in self._repositories.items()
        }
    
    def health_check(self) -> Dict[str, bool]:
        """
        检查所有Repository的健康状态
        
        Returns:
            健康状态字典
        """
        health_status = {}
        for name, repo in self._repositories.items():
            try:
                # 检查Repository是否有健康检查方法
                if hasattr(repo, 'health_check'):
                    health_status[name] = repo.health_check()
                else:
                    # 简单检查Repository是否可用
                    health_status[name] = repo is not None
            except Exception:
                health_status[name] = False
        
        return health_status

# 全局Repository管理器实例获取函数
def get_repository_manager() -> RepositoryManager:
    """
    获取全局Repository管理器实例
    
    Returns:
        Repository管理器实例
    """
    return RepositoryManager()