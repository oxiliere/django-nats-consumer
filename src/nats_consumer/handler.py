import logging
from typing import List, Optional
from nats.aio.msg import Msg

logger = logging.getLogger(__name__)


class ConsumerHandler:
    """
    Base handler class that routes messages to specific handler methods based on subject names.
    
    Supports multiple subject formats:
        - Dot notation: 'orders.created' -> handle_created()
        - Hyphen notation: 'orders-created' -> handle_created()
        - Underscore notation: 'orders_created' -> handle_created()
        - Single token: 'orders' -> handle_orders()
        - Multi-level: 'orders.old.deleted' -> handle_old_deleted()
    
    Example:
        subjects = ['orders.created', 'orders-deleted', 'orders_updated', 'payments']
        
        The handler will automatically route:
        - 'orders.created' -> handle_created()
        - 'orders-deleted' -> handle_deleted()
        - 'orders_updated' -> handle_updated()
        - 'payments' -> handle_payments()
    
    Note: Wildcard subjects (* and >) are currently ignored.
    """

    def __init__(self, subjects: List[str]):
        self.subjects = subjects
        self._handler_map = self._build_handler_map()

    def _build_handler_map(self) -> dict:
        """
        Build a mapping from subjects to handler method names.
        
        RECOMMENDED PRACTICE:
        - Use dots (.) in subjects: 'orders.created', 'users.profile.updated'
        - Use wildcards (*) in filters: 'orders.*', 'users.profile.*'
        - Avoid hyphens (-) and underscores (_) in subjects for consistency
        
        Supported formats (for backward compatibility):
        - 'orders.created' -> 'handle_created' ✅ RECOMMENDED
        - 'orders-created' -> 'handle_created' ⚠️ LEGACY
        - 'orders_created' -> 'handle_created' ⚠️ LEGACY
        - 'orders' -> 'handle_orders'
        - 'orders.old.deleted' -> 'handle_old_deleted'
        """
        handler_map = {}
        method_collisions = {}  # Track potential collisions
        
        for subject in self.subjects:
            # Skip wildcard subjects for now
            if '*' in subject or '>' in subject:
                continue
                
            # Normalize separators: convert dots and hyphens to underscores
            normalized = subject.replace('.', '_').replace('-', '_')
            
            # Split by underscores to get parts
            parts = normalized.split('_')
            
            if len(parts) >= 2:
                # Multi-part subject: take everything after the first part (domain)
                # e.g., 'orders_created' -> 'handle_created'
                # e.g., 'orders_old_deleted' -> 'handle_old_deleted'
                handler_parts = parts[1:]
                handler_name = f"handle_{'_'.join(handler_parts)}"
            else:
                # Single-part subject
                # e.g., 'orders' -> 'handle_orders'
                handler_name = f"handle_{parts[0]}"
            
            # Check for collisions
            if handler_name in method_collisions:
                existing_subject = method_collisions[handler_name]
                logger.warning(
                    f"Handler method collision detected: '{subject}' and '{existing_subject}' "
                    f"both map to '{handler_name}()'. Consider using dot notation for subjects "
                    f"(e.g., 'orders.created' instead of 'orders-created')."
                )
            else:
                method_collisions[handler_name] = subject
                
            handler_map[subject] = handler_name
        
        # Log recommendations for non-dot subjects
        non_dot_subjects = [s for s in self.subjects if '.' not in s and ('*' not in s and '>' not in s)]
        if non_dot_subjects:
            logger.info(
                f"RECOMMENDATION: Consider using dot notation for subjects: {non_dot_subjects}. "
                f"Example: 'orders.created' instead of 'orders-created' or 'orders_created'"
            )
                
        return handler_map

    async def handle(self, msg: Msg):
        """
        Route the message to the appropriate handler method based on its subject.
        Falls back to fallback_handle if no specific handler is found.
        """
        subject = msg.subject
        
        if subject not in self.subjects:
            logger.warning(f"Received message for unhandled subject: {subject}")
            await self.fallback_handle(msg, reason="unhandled_subject")
            return
            
        handler_name = self._handler_map.get(subject)
        if not handler_name:
            logger.warning(f"No handler mapping found for subject: {subject}")
            await self.fallback_handle(msg, reason="no_mapping")
            return
            
        if not hasattr(self, handler_name):
            logger.error(f"Handler method '{handler_name}' not implemented for subject '{subject}'")
            await self.fallback_handle(msg, reason="not_implemented")
            return
            
        handler_method = getattr(self, handler_name)
        try:
            await handler_method(msg)
        except Exception as e:
            logger.error(f"Error in handler '{handler_name}' for subject '{subject}': {str(e)}")
            raise

    def get_handler_methods(self) -> List[str]:
        """Return a list of expected handler method names for debugging."""
        return list(self._handler_map.values())

    def validate_handlers(self) -> List[str]:
        """
        Validate that all required handler methods are implemented.
        Returns a list of missing handler methods.
        """
        missing_handlers = []
        for subject, handler_name in self._handler_map.items():
            if not hasattr(self, handler_name) or not callable(getattr(self, handler_name)):
                missing_handlers.append(handler_name)
        return missing_handlers

    async def fallback_handle(self, msg: Msg, reason: str = "unknown"):
        """
        Fallback handler for messages that cannot be routed to specific handlers.
        
        Default behavior: NAK the message to trigger redelivery.
        
        REASONING FOR NAK (default):
        - 🔄 **Redelivery**: Allows fixing handler implementation and reprocessing
        - 🛡️ **Safety**: Prevents message loss during development/deployment
        - 🐛 **Debugging**: Keeps problematic messages in the stream for analysis
        - ⚠️ **Alerting**: Repeated NAKs can trigger monitoring alerts
        
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
            f"NAKing message to trigger redelivery. Override fallback_handle() for custom behavior."
        )
        
        # Default behavior: NAK to trigger redelivery
        # This is safer than ACK as it prevents message loss
        await msg.nak()
