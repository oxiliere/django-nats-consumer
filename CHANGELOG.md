# Changelog

All notable changes to this project will be documented in this file.

## [2.0.0] - 2026-01-05

### 🎯 Major Release - Decorator-Based Handler System

This is a major breaking release that introduces decorator-based handler registration with the `@handle` decorator.

### Added

- **`@handle` decorator** for explicit handler registration
- **Full wildcard support** (`*` and `>`) for subject patterns with priority matching
- **Multiple subjects per handler** - One method can handle multiple subjects
- **Free method naming** - No naming conventions required
- **Native NATS retry** mechanism with exponential backoff
- **`CreateOrUpdateStream`** operation for idempotent stream setup in production
- **`nats_delete_stream`** management command for stream deletion
- **`nats_update_stream`** management command for stream configuration updates
- **Comprehensive documentation** with migration guide (DECORATOR_MIGRATION.md)
- **Subject naming best practices** - Strong recommendations for dot notation
- **Production deployment guide** with CreateOrUpdateStream recommendations
- **52 passing tests** covering all new features

### Changed

- **BREAKING:** `ConsumerHandler` now requires `@handle` decorator for handler methods
- **BREAKING:** No automatic method detection based on naming conventions
- **BREAKING:** `ConsumerHandler.__init__()` no longer accepts `subjects` parameter
- **BREAKING:** All handler methods must use `@handle` decorator
- Complete README rewrite with decorator examples and best practices
- Updated all example consumers to use decorator approach
- Improved error handling and logging throughout
- Better test coverage with helper functions for mock messages

### Fixed

- Django I/O errors with `watchfiles` import (moved to lazy import)
- Double acknowledgment issues in message handling
- Mock message handling in tests with proper `_ackd` attribute management
- Stream operation error handling and logging

### Removed

- Automatic method detection based on `handle_*` naming convention
- `subjects` parameter from `ConsumerHandler.__init__()`
- Old auto-detection logic and related code

### Migration Guide

See [DECORATOR_MIGRATION.md](DECORATOR_MIGRATION.md) for complete migration instructions from v1.x.

**Quick migration:**
```python
# OLD (v1.x)
class OrderHandler(ConsumerHandler):
    def __init__(self):
        subjects = ["orders.created", "orders.updated"]
        super().__init__(subjects)
    
    async def handle_created(self, msg):
        pass

# NEW (v2.x)
class OrderHandler(ConsumerHandler):
    @handle('orders.created')
    async def on_created(self, msg):
        pass
    
    @handle('orders.updated', 'orders.modified')
    async def on_updated(self, msg):
        pass
```

---

## 1.0.0 (2025-10-26)

- docs: update ([`1195243`](https://github.com/oxiliere/django-nats-consumer/commit/11952436aca33ba772e095b2d5871dcb1599cddb))
- docs: Adds documentation for the reload and event loop policy setting (#11) ([`e69d7e9`](https://github.com/oxiliere/django-nats-consumer/commit/e69d7e9f74fd1143fa70ce598f2b616b206ffe2d))
- docs: Adds documentation for the reload and event loop policy setting ([`e69d7e9`](https://github.com/oxiliere/django-nats-consumer/commit/e69d7e9f74fd1143fa70ce598f2b616b206ffe2d))
