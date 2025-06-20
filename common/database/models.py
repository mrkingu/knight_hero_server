"""
数据模型定义
使用Beanie ODM定义MongoDB文档模型
作者: lx
日期: 2025-06-18
"""
from beanie import Document
from pydantic import Field, validator
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum


class VIPLevel(int, Enum):
    """VIP等级枚举"""
    V0 = 0
    V1 = 1
    V2 = 2
    V3 = 3
    V4 = 4
    V5 = 5
    V6 = 6
    V7 = 7
    V8 = 8
    V9 = 9
    V10 = 10


class Player(Document):
    """玩家数据模型"""
    player_id: str = Field(..., description="玩家ID", unique=True)
    nickname: str = Field(..., description="昵称", min_length=1, max_length=20)
    level: int = Field(1, description="等级", ge=1, le=999)
    exp: int = Field(0, description="经验值", ge=0)
    vip_level: VIPLevel = Field(VIPLevel.V0, description="VIP等级")
    vip_exp: int = Field(0, description="VIP经验", ge=0)
    
    # 资源
    diamond: int = Field(0, description="钻石", ge=0, le=999999999)
    gold: int = Field(0, description="金币", ge=0, le=999999999)
    energy: int = Field(100, description="体力", ge=0, le=999)
    
    # 背包
    items: Dict[str, int] = Field(default_factory=dict, description="道具背包")
    
    # 游戏进度
    current_stage: int = Field(1, description="当前关卡", ge=1)
    max_stage: int = Field(1, description="最高关卡", ge=1)
    
    # 时间戳
    create_time: datetime = Field(default_factory=datetime.now, description="创建时间")
    last_login: datetime = Field(default_factory=datetime.now, description="最后登录时间")
    last_save: datetime = Field(default_factory=datetime.now, description="最后保存时间")
    
    # 设备信息
    device_id: Optional[str] = Field(None, description="设备ID")
    platform: Optional[str] = Field(None, description="平台")
    
    @validator('nickname', pre=True)
    def validate_nickname(cls, v):
        """验证昵称"""
        if not v or not str(v).strip():
            raise ValueError('昵称不能为空')
        # 这里可以添加更多验证逻辑，如敏感词过滤
        return str(v).strip()
    
    @validator('max_stage', pre=True)
    def validate_max_stage(cls, v, values):
        """验证最高关卡不能小于当前关卡"""
        current_stage = values.get('current_stage', 1)
        if v < current_stage:
            return current_stage
        return v
    
    class Settings:
        name = "players"  # MongoDB集合名
        indexes = [
            "player_id",  # 单字段索引
            [("level", -1), ("player_id", 1)],  # 复合索引
            [("vip_level", -1), ("player_id", 1)],  # VIP排行榜索引
            [("last_login", -1)],  # 最后登录时间索引
            [("create_time", -1)],  # 创建时间索引
        ]
        
    class ConcurrentFields:
        """定义支持并发操作的字段"""
        fields = {
            "diamond": {
                "type": "number",
                "operations": ["incr", "decr"],
                "min": 0,
                "max": 999999999,
                "description": "钻石数量"
            },
            "gold": {
                "type": "number", 
                "operations": ["incr", "decr"],
                "min": 0,
                "max": 999999999,
                "description": "金币数量"
            },
            "exp": {
                "type": "number",
                "operations": ["incr"],
                "min": 0,
                "max": 999999999,
                "description": "经验值"
            },
            "vip_exp": {
                "type": "number",
                "operations": ["incr"],
                "min": 0,
                "max": 999999999,
                "description": "VIP经验"
            },
            "energy": {
                "type": "number",
                "operations": ["incr", "decr", "set"],
                "min": 0,
                "max": 999,
                "description": "体力值"
            },
            "items": {
                "type": "dict",
                "operations": ["incr", "decr", "set"],
                "description": "道具背包"
            },
            "current_stage": {
                "type": "number",
                "operations": ["incr", "set"],
                "min": 1,
                "max": 99999,
                "description": "当前关卡"
            },
            "max_stage": {
                "type": "number",
                "operations": ["incr", "set"],
                "min": 1,
                "max": 99999,
                "description": "最高关卡"
            }
        }


class Guild(Document):
    """公会数据模型"""
    guild_id: str = Field(..., description="公会ID", unique=True)
    name: str = Field(..., description="公会名称", min_length=1, max_length=20)
    leader_id: str = Field(..., description="会长ID")
    description: str = Field("", description="公会描述", max_length=200)
    level: int = Field(1, description="公会等级", ge=1, le=50)
    exp: int = Field(0, description="公会经验", ge=0)
    max_members: int = Field(20, description="最大成员数", ge=10, le=100)
    
    # 成员列表
    members: List[Dict[str, Any]] = Field(default_factory=list, description="成员列表")
    
    # 公会资源
    funds: int = Field(0, description="公会资金", ge=0)
    
    # 时间戳
    create_time: datetime = Field(default_factory=datetime.now, description="创建时间")
    last_active: datetime = Field(default_factory=datetime.now, description="最后活跃时间")
    
    class Settings:
        name = "guilds"
        indexes = [
            "guild_id",
            "leader_id",
            [("level", -1), ("exp", -1)],  # 公会排行榜
            [("last_active", -1)]
        ]
    
    class ConcurrentFields:
        """定义支持并发操作的字段"""
        fields = {
            "exp": {
                "type": "number",
                "operations": ["incr"],
                "min": 0,
                "max": 999999999,
                "description": "公会经验"
            },
            "funds": {
                "type": "number",
                "operations": ["incr", "decr"],
                "min": 0,
                "max": 999999999,
                "description": "公会资金"
            },
            "members": {
                "type": "list",
                "operations": ["append", "remove"],
                "description": "成员列表"
            }
        }


class GameConfig(Document):
    """游戏配置模型"""
    config_id: str = Field(..., description="配置ID", unique=True)
    config_type: str = Field(..., description="配置类型")
    name: str = Field(..., description="配置名称")
    description: str = Field("", description="配置描述")
    data: Dict[str, Any] = Field(..., description="配置数据")
    version: int = Field(1, description="版本号")
    is_active: bool = Field(True, description="是否激活")
    
    # 时间戳
    create_time: datetime = Field(default_factory=datetime.now)
    update_time: datetime = Field(default_factory=datetime.now)
    
    class Settings:
        name = "game_configs"
        indexes = [
            "config_id",
            "config_type",
            [("config_type", 1), ("is_active", 1)],
            [("update_time", -1)]
        ]


class OperationLog(Document):
    """操作日志模型"""
    log_id: str = Field(..., description="日志ID", unique=True)
    entity_type: str = Field(..., description="实体类型")
    entity_id: str = Field(..., description="实体ID")
    operation_type: str = Field(..., description="操作类型")
    field_name: str = Field(..., description="字段名")
    old_value: Any = Field(None, description="旧值")
    new_value: Any = Field(None, description="新值")
    source: str = Field(..., description="操作来源")
    reason: str = Field("", description="操作原因")
    operator_id: Optional[str] = Field(None, description="操作者ID")
    
    # 元数据
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")
    
    # 时间戳
    timestamp: datetime = Field(default_factory=datetime.now, description="操作时间")
    
    class Settings:
        name = "operation_logs"
        indexes = [
            "log_id",
            [("entity_type", 1), ("entity_id", 1)],
            [("timestamp", -1)],
            [("operation_type", 1), ("timestamp", -1)],
            [("source", 1), ("timestamp", -1)]
        ]


class PaymentOrder(Document):
    """支付订单模型"""
    order_id: str = Field(..., description="订单ID", unique=True)
    player_id: str = Field(..., description="玩家ID")
    product_id: str = Field(..., description="商品ID")
    product_name: str = Field(..., description="商品名称")
    amount: float = Field(..., description="支付金额", gt=0)
    currency: str = Field("USD", description="货币类型")
    platform: str = Field(..., description="支付平台")
    platform_order_id: str = Field("", description="平台订单ID")
    
    # 奖励内容
    rewards: Dict[str, int] = Field(..., description="奖励内容")
    
    # 订单状态
    status: str = Field("pending", description="订单状态")  # pending, success, failed, refunded
    
    # 时间戳
    create_time: datetime = Field(default_factory=datetime.now)
    pay_time: Optional[datetime] = Field(None, description="支付完成时间")
    process_time: Optional[datetime] = Field(None, description="处理完成时间")
    
    class Settings:
        name = "payment_orders"
        indexes = [
            "order_id",
            "player_id",
            [("status", 1), ("create_time", -1)],
            [("platform", 1), ("platform_order_id", 1)],
            [("pay_time", -1)]
        ]


class ScheduledTask(Document):
    """定时任务模型"""
    task_id: str = Field(..., description="任务ID", unique=True)
    task_type: str = Field(..., description="任务类型")
    title: str = Field(..., description="任务标题")
    description: str = Field("", description="任务描述")
    
    # 奖励配置
    rewards: Dict[str, int] = Field(..., description="奖励配置")
    
    # 目标玩家
    target_players: List[str] = Field(default_factory=list, description="目标玩家列表")
    target_conditions: Dict[str, Any] = Field(default_factory=dict, description="目标条件")
    
    # 时间配置
    start_time: datetime = Field(..., description="开始时间")
    end_time: datetime = Field(..., description="结束时间")
    
    # 任务状态
    status: str = Field("pending", description="任务状态")  # pending, running, completed, cancelled
    
    # 执行统计
    total_targets: int = Field(0, description="目标总数")
    completed_count: int = Field(0, description="完成数量")
    
    # 时间戳
    create_time: datetime = Field(default_factory=datetime.now)
    update_time: datetime = Field(default_factory=datetime.now)
    
    class Settings:
        name = "scheduled_tasks"
        indexes = [
            "task_id",
            "task_type",
            [("status", 1), ("start_time", 1)],
            [("end_time", 1)],
            [("create_time", -1)]
        ]


class RewardRecord(Document):
    """奖励发放记录模型"""
    record_id: str = Field(..., description="记录ID", unique=True)
    player_id: str = Field(..., description="玩家ID")
    source_type: str = Field(..., description="来源类型")  # payment, schedule, activity, gm
    source_id: str = Field(..., description="来源ID")
    
    # 奖励内容
    rewards: Dict[str, int] = Field(..., description="奖励内容")
    
    # 状态
    status: str = Field("success", description="发放状态")  # success, failed, reverted
    
    # 时间戳
    create_time: datetime = Field(default_factory=datetime.now)
    
    class Settings:
        name = "reward_records"
        indexes = [
            "record_id",
            [("player_id", 1), ("create_time", -1)],
            [("source_type", 1), ("source_id", 1)],
            [("status", 1), ("create_time", -1)]
        ]


# 导出所有文档模型
ALL_DOCUMENT_MODELS = [
    Player,
    Guild,
    GameConfig,
    OperationLog,
    PaymentOrder,
    ScheduledTask,
    RewardRecord
]


def get_concurrent_fields(model_class: type) -> Dict[str, Dict[str, Any]]:
    """获取模型的并发字段配置"""
    if hasattr(model_class, 'ConcurrentFields') and hasattr(model_class.ConcurrentFields, 'fields'):
        return model_class.ConcurrentFields.fields
    return {}


def get_model_indexes(model_class: type) -> List:
    """获取模型的索引配置"""
    if hasattr(model_class, 'Settings') and hasattr(model_class.Settings, 'indexes'):
        return model_class.Settings.indexes
    return []


def get_collection_name(model_class: type) -> str:
    """获取模型的集合名称"""
    if hasattr(model_class, 'Settings') and hasattr(model_class.Settings, 'name'):
        return model_class.Settings.name
    return model_class.__name__.lower() + 's'