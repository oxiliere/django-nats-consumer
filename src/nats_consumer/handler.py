import logging
from typing import List, Optional, Callable, Union
from functools import wraps
from nats.aio.msg import Msg

logger = logging.getLogger(__name__)


def handle(*subjects: str):
    """
    Decorator to register a handler method for one or more NATS subjects.
    
    Usage:
        class MyHandler(ConsumerHandler):
            @handle('orders.created')
            async def on_order_created(self, msg: Msg):
                # Handle order created
                pass
            
            @handle('orders.updated', 'orders.modified')
            async def on_order_changed(self, msg: Msg):
                # Handle order updates
                pass
            
            @handle('orders.*')  # Wildcard support
            async def on_any_order(self, msg: Msg):
                # Handle any order event
                pass
    
    Args:
        *subjects: One or more subject patterns to handle
    
    Returns:
        Decorated handler method with _nats_subjects attribute
    """
    def decorator(func: Callable) -> Callable:
        # Store subjects on the function for later registration
        func._nats_subjects = subjects
        return func
    return decorator


class ConsumerHandler:
    """
    Base handler class that routes messages to handler methods using @handle decorator.
    
    New decorator-based approach:
        class MyHandler(ConsumerHandler):
            @handle('orders.created')
            async def on_order_created(self, msg: Msg):
                data = json.loads(msg.data.decode())
                # Process order creation
            
            @handle('orders.updated', 'orders.modified')
            async def on_order_changed(self, msg: Msg):
                # Handle multiple subjects with one method
                pass
            
            @handle('orders.*')  # Wildcard support
            async def on_any_order(self, msg: Msg):
                # Catch-all for order events
                pass
    
    Benefits:
        - Explicit: Clear which methods handle which subjects
        - Flexible: One method can handle multiple subjects
        - Wildcards: Full support for * and > patterns
        - No naming conventions: Method names can be anything
    """

    def __init__(self):
        self._handler_map = self._build_handler_map()
        self.subjects = list(self._handler_map.keys())

    def _build_handler_map(self) -> dict:
        """
        Build a mapping from subjects to handler methods by scanning for @handle decorators.
        
        Returns:
            dict: Mapping of subject -> handler method
        """
        handler_map = {}
        
        # Scan all methods in the class for @handle decorator
        for attr_name in dir(self):
            if attr_name.startswith('_'):
                continue
                
            attr = getattr(self, attr_name)
            
            # Check if method has _nats_subjects attribute (set by @handle decorator)
            if hasattr(attr, '_nats_subjects'):
                subjects = attr._nats_subjects
                for subject in subjects:
                    if subject in handler_map:
                        existing_method = handler_map[subject].__name__
                        logger.warning(
                            f"Subject '{subject}' is already handled by {existing_method}(). "
                            f"Overriding with {attr_name}()."
                        )
                    handler_map[subject] = attr
                    logger.debug(f"Registered handler: {subject} -> {attr_name}()")
        
        if not handler_map:
            logger.warning(
                f"{self.__class__.__name__} has no handlers registered. "
                f"Use @handle decorator to register handler methods."
            )
                
        return handler_map

    async def handle(self, msg: Msg):
        """
        Route the message to the appropriate handler method based on its subject.
        Supports exact matches and wildcard patterns (* and >).
        Falls back to fallback_handle if no handler is found.
        """
        subject = msg.subject
        handler_method = None
        
        # Try exact match first
        if subject in self._handler_map:
            handler_method = self._handler_map[subject]
        else:
            # Try wildcard matching
            handler_method = self._match_wildcard(subject)
        
        if handler_method is None:
            logger.warning(f"No handler found for subject: {subject}")
            await self.fallback_handle(msg, reason="no_handler")
            return
        
        try:
            await handler_method(msg)
        except Exception as e:
            logger.error(f"Error in handler '{handler_method.__name__}' for subject '{subject}': {str(e)}")
            raise
    
    def _match_wildcard(self, subject: str) -> Optional[Callable]:
        """
        Match subject against wildcard patterns in handler map.
        
        Supports:
            - '*' matches one token: 'orders.*' matches 'orders.created'
            - '>' matches one or more tokens: 'orders.>' matches 'orders.created.v1'
        
        Args:
            subject: The subject to match
        
        Returns:
            Handler method if match found, None otherwise
        """
        subject_parts = subject.split('.')
        
        for pattern, handler in self._handler_map.items():
            if '*' not in pattern and '>' not in pattern:
                continue
            
            pattern_parts = pattern.split('.')
            
            # Handle '>' wildcard (matches rest of subject)
            if '>' in pattern_parts:
                gt_index = pattern_parts.index('>')
                # '>' must be last token
                if gt_index != len(pattern_parts) - 1:
                    logger.warning(f"Invalid pattern '{pattern}': '>' must be the last token")
                    continue
                
                # Check if prefix matches
                if len(subject_parts) >= gt_index:
                    if subject_parts[:gt_index] == pattern_parts[:gt_index]:
                        return handler
            
            # Handle '*' wildcard (matches exactly one token)
            elif '*' in pattern_parts:
                if len(subject_parts) != len(pattern_parts):
                    continue
                
                match = True
                for i, (s_part, p_part) in enumerate(zip(subject_parts, pattern_parts)):
                    if p_part != '*' and s_part != p_part:
                        match = False
                        break
                
                if match:
                    return handler
        
        return None

    def get_handler_methods(self) -> List[str]:
        """Return a list of registered handler method names for debugging."""
        return [method.__name__ for method in self._handler_map.values()]
    
    def get_subjects(self) -> List[str]:
        """Return a list of all registered subjects."""
        return list(self._handler_map.keys())

    async def fallback_handle(self, msg: Msg, reason: str = "unknown"):
        """
        Fallback handler for messages that cannot be routed to specific handlers.
        
        Default behavior: NAK the message to trigger native NATS redelivery.
        
        REASONING FOR NAK (default):
        - 🔄 **Redelivery**: Allows fixing handler implementation and reprocessing
        - 🛡️ **Safety**: Prevents message loss during development/deployment
        - 🐛 **Debugging**: Keeps problematic messages in the stream for analysis
        - ⚠️ **Alerting**: Repeated NAKs can trigger monitoring alerts
        - ⏱️ **Native backoff**: Uses NATS JetStream backoff configuration
        
        Override this method to implement custom fallback behavior:
        - ACK: To discard unhandled messages (data loss risk)
        - Custom logic: Route to DLQ, log to external system, etc.
        
        Args:
            msg: The NATS message that couldn't be handled
            reason: Why the fallback was triggered
                   - "unhandled_subject": Subject not in handler's subjects list
                   - "no_mapping": No handler method mapping found
                   - "not_implemented": Handler method not implemented
        """
        logger.warning(
            f"Fallback handler triggered for subject '{msg.subject}' (reason: {reason}). "
            f"NAKing message to trigger native NATS redelivery with backoff. "
            f"Override fallback_handle() for custom behavior."
        )
        
        # Default behavior: NAK without delay to use native NATS backoff
        # This allows the consumer's backoff configuration to control redelivery timing
        # This is safer than ACK as it prevents message loss
        await msg.nak()
