# IoC Container Framework - Usage Guide

## Overview

This document provides a comprehensive guide for using the newly implemented IoC (Inversion of Control) container framework in the knight_hero_server project. The framework provides Spring Boot-style dependency injection and automatic service discovery.

## Key Features

- **@service** decorator for auto-registering business services
- **@repository** decorator for data access layer components  
- **@autowired** decorator for automatic dependency injection
- **Automatic service scanning** during startup
- **Lifecycle management** with proper initialization and shutdown
- **Circular dependency detection** and resolution
- **Clear separation of concerns** between Handler/Service/Repository layers

## Architecture

```
Handler Layer    -> Only handles request parsing and validation
    ↓ (autowired)
Service Layer    -> Contains business logic and orchestration  
    ↓ (autowired)
Repository Layer -> Data access and persistence operations
```

## Usage Examples

### 1. Repository Layer

```python
from common.ioc import repository
from common.database.repository.enhanced_base_repository import BaseIoCRepository

@repository("PlayerRepository")
class PlayerRepository(BaseIoCRepository):
    """Player data repository with auto-loading support"""
    
    def __init__(self):
        super().__init__("players")
    
    async def on_initialize(self):
        await super().on_initialize()
        self.logger.info("PlayerRepository initialized")
    
    async def get_player(self, player_id: str) -> Optional[dict]:
        return await self.get_by_id(player_id)
    
    async def update_diamond(self, player_id: str, amount: int) -> dict:
        if amount > 0:
            return await self.increment(player_id, "diamond", amount, "diamond_add")
        else:
            return await self.decrement_with_check(
                player_id, "diamond", abs(amount), "diamond_consume", min_value=0
            )
```

### 2. Service Layer

```python
from common.ioc import service, autowired
from services.logic.services.base.base_logic_service import BaseLogicService

@service("PlayerService")
class PlayerService(BaseLogicService):
    """Player business service with dependency injection"""
    
    @autowired("PlayerRepository")
    def player_repository(self):
        """Player repository - automatically injected"""
        pass
    
    @autowired("TaskService")  # Optional: other services
    def task_service(self):
        """Task service - automatically injected"""
        pass
    
    async def on_initialize(self):
        await super().on_initialize()
        self.logger.info("PlayerService initialized")
    
    async def get_player_info(self, player_id: str) -> Dict[str, Any]:
        # 1. Validate parameters
        validation_result = await self.validate_player_action(player_id, "get_info")
        if not validation_result["valid"]:
            return self.error_response(validation_result["reason"])
        
        # 2. Call repository for data
        player_data = await self.player_repository.get_player(player_id)
        
        # 3. Process business logic
        if not player_data:
            return self.error_response("Player not found")
        
        # 4. Return formatted response
        return self.success_response({
            "player_id": player_data["player_id"],
            "nickname": player_data.get("nickname", ""),
            "level": player_data.get("level", 1),
            "diamond": player_data.get("diamond", 0),
            "gold": player_data.get("gold", 0)
        })
    
    async def add_diamond(self, player_id: str, amount: int, source: str) -> Dict[str, Any]:
        # Business validation
        if amount <= 0:
            return self.error_response("Invalid amount")
        
        # Call repository
        result = await self.player_repository.update_diamond(player_id, amount)
        
        # Trigger related business logic
        if result.get("success"):
            await self.emit_event("diamond_changed", {
                "player_id": player_id,
                "amount": amount,
                "source": source
            })
        
        return self.success_response(result) if result.get("success") else self.error_response("Failed to add diamond")
```

### 3. Handler Layer

```python
from common.ioc import service, autowired
from services.logic.handlers.base.base_handler_ioc import BaseHandler

@service("PlayerHandler")
class PlayerHandler(BaseHandler):
    """Player request handler - delegates to services only"""
    
    @autowired("PlayerService")
    def player_service(self):
        """Player service - automatically injected"""
        pass
    
    async def handle_add_diamond(self, request: dict) -> dict:
        # 1. Parse parameters
        params = {
            "player_id": self.extract_player_id(request),
            "amount": request.get("amount", 0),
            "source": request.get("source", "unknown")
        }
        
        # 2. Validate parameters
        validation_result = self.validate_required_params(params, ["player_id", "amount"])
        if not validation_result["valid"]:
            return self.error_response(validation_result["reason"])
        
        numeric_result = self.validate_numeric_params(params, {
            "amount": {"min": 1, "max": 999999}
        })
        if not numeric_result["valid"]:
            return self.error_response(numeric_result["reason"])
        
        # 3. Delegate to service
        result = await self.player_service.add_diamond(
            params["player_id"],
            params["amount"], 
            params["source"]
        )
        
        return result
```

### 4. Service Startup

```python
# services/logic/main_ioc.py
import asyncio
from common.ioc import ServiceContainer

class LogicServer:
    def __init__(self):
        self.container = ServiceContainer()
    
    async def start(self):
        # Auto-scan and load services
        scan_paths = [
            "services/logic/services",
            "services/logic/handlers", 
            "services/logic/repositories"
        ]
        
        await self.container.initialize(scan_paths)
        
        # Get service statistics
        container_info = self.container.get_container_info()
        logger.info(f"Container initialized with {container_info['total_services']} services")
        
        # Start gRPC server
        await self._start_grpc_server()
        
        logger.info("Logic Server started successfully!")

if __name__ == "__main__":
    server = LogicServer()
    asyncio.run(server.start())
```

## Benefits

### 1. Automatic Dependency Management
- No manual service instantiation
- Automatic dependency resolution
- Circular dependency detection

### 2. Clear Separation of Concerns
- **Handlers**: Only parameter parsing and validation
- **Services**: Pure business logic
- **Repositories**: Data access only

### 3. Testability
- Easy to mock dependencies for unit testing
- Clear service boundaries
- Isolated components

### 4. Maintainability
- Reduced boilerplate code
- Consistent service structure
- Clear dependency chains

## Testing

### Unit Testing with IoC

```python
import pytest
from common.ioc import ServiceContainer
from common.ioc.decorators import clear_registry

class TestPlayerService:
    def setup_method(self):
        clear_registry()
    
    @pytest.mark.asyncio
    async def test_player_service(self):
        # Define test services
        @repository("TestPlayerRepository")
        class TestPlayerRepository(BaseService):
            async def get_player(self, player_id: str):
                return {"player_id": player_id, "diamond": 100}
        
        @service("TestPlayerService")
        class TestPlayerService(BaseService):
            @autowired("TestPlayerRepository")
            def player_repository(self):
                pass
            
            async def get_info(self, player_id: str):
                return await self.player_repository.get_player(player_id)
        
        # Create and initialize container
        container = ServiceContainer()
        # ... register services
        await container.initialize()
        
        # Test
        service = container.get_service("TestPlayerService") 
        result = await service.get_info("test123")
        assert result["diamond"] == 100
        
        await container.shutdown()
```

## Migration Guide

### From Existing Services

1. **Add IoC decorators**:
   ```python
   # Before
   class PlayerService(PlayerRepository):
       pass
   
   # After  
   @service("PlayerService")
   class PlayerService(BaseLogicService):
       @autowired("PlayerRepository")
       def player_repository(self):
           pass
   ```

2. **Update initialization**:
   ```python
   # Before
   def __init__(self, redis_client, mongo_client):
       super().__init__(redis_client, mongo_client)
   
   # After
   async def on_initialize(self):
       await super().on_initialize()
       # Custom initialization
   ```

3. **Update service startup**:
   ```python
   # Before
   service = PlayerService(redis, mongo)
   handler = PlayerHandler(service)
   
   # After
   container = ServiceContainer()
   await container.initialize(["services/logic"])
   handler = container.get_service("PlayerHandler")
   ```

## Best Practices

1. **Service Design**:
   - Keep services stateless
   - Use dependency injection for all external dependencies
   - Implement proper error handling

2. **Dependency Management**:
   - Avoid circular dependencies
   - Use interfaces/abstract classes when possible
   - Keep dependency chains shallow

3. **Testing**:
   - Test services in isolation
   - Mock dependencies appropriately
   - Test the complete dependency chain

4. **Performance**:
   - Services are singletons by default
   - Lazy loading for expensive resources
   - Proper resource cleanup in shutdown methods

## Troubleshooting

### Common Issues

1. **Service Not Found**: Ensure service is properly decorated and imported
2. **Circular Dependencies**: Check dependency chains and refactor if needed
3. **Initialization Order**: Dependencies are automatically resolved
4. **Missing Dependencies**: Verify @autowired decorators and service names

### Debugging

```python
# Check container status
container_info = container.get_container_info()
print(f"Services: {container_info['services']}")
print(f"Initialization order: {container_info['initialization_order']}")

# Health check
for service_name in container_info['services']:
    service = container.get_service(service_name)
    health = await service.health_check()
    print(f"{service_name}: {health}")
```