"""
Lua脚本管理
预定义常用的Lua脚本
作者: lx
日期: 2025-06-20
"""

class LuaScripts:
    """Lua脚本集合"""
    
    # 原子增加并检查范围
    INCR_WITH_LIMIT = """
    local key = KEYS[1]
    local field = ARGV[1]
    local increment = tonumber(ARGV[2])
    local min_val = tonumber(ARGV[3])
    local max_val = tonumber(ARGV[4])
    
    local current = tonumber(redis.call('HGET', key, field) or 0)
    local new_value = current + increment
    
    if new_value < min_val then
        new_value = min_val
    elseif new_value > max_val then
        new_value = max_val
    end
    
    redis.call('HSET', key, field, new_value)
    return {current, new_value}
    """
    
    # 批量操作
    BATCH_OPERATIONS = """
    local key = KEYS[1]
    local results = {}
    local i = 1
    
    while i <= #ARGV do
        local op = ARGV[i]
        local field = ARGV[i+1]
        local value = tonumber(ARGV[i+2])
        
        if op == 'incr' then
            local current = tonumber(redis.call('HGET', key, field) or 0)
            local new_value = current + value
            redis.call('HSET', key, field, new_value)
            table.insert(results, {field, current, new_value})
        end
        
        i = i + 3
    end
    
    return results
    """
    
    # 检查并设置
    CHECK_AND_SET = """
    local key = KEYS[1]
    local field = ARGV[1]
    local expected = ARGV[2]
    local new_value = ARGV[3]
    
    local current = redis.call('HGET', key, field)
    
    if current == expected then
        redis.call('HSET', key, field, new_value)
        return 1
    else
        return 0
    end
    """