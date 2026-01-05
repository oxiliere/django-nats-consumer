import pytest
from unittest.mock import AsyncMock
from nats_consumer import ConsumerHandler, handle


class HandlerForTesting(ConsumerHandler):
    """Handler implementation for testing using @handle decorator"""
    
    def __init__(self):
        # Initialize mocks before calling super().__init__()
        self.created_mock = AsyncMock()
        self.updated_mock = AsyncMock()
        self.deleted_mock = AsyncMock()
        self.payments_mock = AsyncMock()
        self.archived_mock = AsyncMock()
        super().__init__()
    
    @handle('orders.created')
    async def on_created(self, msg):
        await self.created_mock(msg)
    
    @handle('orders.updated', 'orders-updated')
    async def on_updated(self, msg):
        await self.updated_mock(msg)
    
    @handle('orders.deleted', 'orders_deleted')
    async def on_deleted(self, msg):
        await self.deleted_mock(msg)
    
    @handle('payments')
    async def on_payments(self, msg):
        await self.payments_mock(msg)
    
    @handle('orders.old.archived')
    async def on_archived(self, msg):
        await self.archived_mock(msg)


@pytest.fixture
def test_handler():
    """Create a test handler instance"""
    return HandlerForTesting()


class TestConsumerHandler:
    """Test cases for ConsumerHandler with decorator approach"""
    
    def test_handler_registration(self, test_handler):
        """Test that handlers are registered correctly"""
        assert "orders.created" in test_handler._handler_map
        assert "orders.updated" in test_handler._handler_map
        assert "orders-updated" in test_handler._handler_map
        assert "orders.deleted" in test_handler._handler_map
        assert "orders_deleted" in test_handler._handler_map
        assert "payments" in test_handler._handler_map
        assert "orders.old.archived" in test_handler._handler_map
    
    def test_handler_methods_are_callable(self, test_handler):
        """Test that registered handlers are callable"""
        for subject, handler in test_handler._handler_map.items():
            assert callable(handler), f"Handler for {subject} is not callable"
    
    def test_get_subjects(self, test_handler):
        """Test get_subjects returns all registered subjects"""
        subjects = test_handler.get_subjects()
        assert "orders.created" in subjects
        assert "orders.updated" in subjects
        assert "payments" in subjects
    
    def test_get_handler_methods(self, test_handler):
        """Test get_handler_methods returns method names"""
        methods = test_handler.get_handler_methods()
        assert "on_created" in methods
        assert "on_updated" in methods
        assert "on_payments" in methods
    
    def test_multiple_subjects_one_handler(self):
        """Test that one handler can handle multiple subjects"""
        class MultiSubjectHandler(ConsumerHandler):
            @handle('orders.updated', 'orders-updated', 'orders_updated')
            async def on_update(self, msg):
                pass
        
        handler = MultiSubjectHandler()
        assert 'orders.updated' in handler._handler_map
        assert 'orders-updated' in handler._handler_map
        assert 'orders_updated' in handler._handler_map
        assert handler._handler_map['orders.updated'] == handler._handler_map['orders-updated']
    
    @pytest.mark.asyncio
    async def test_handle_message_routing(self, test_handler, mock_message):
        """Test message routing to correct handler"""
        msg = mock_message("orders.created")
        
        await test_handler.handle(msg)
        
        test_handler.created_mock.assert_called_once_with(msg)
        test_handler.updated_mock.assert_not_called()
        test_handler.deleted_mock.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_handle_message_different_formats(self, test_handler, mock_message):
        """Test message routing for different subject formats"""
        # Test dot notation
        msg1 = mock_message("orders.created")
        await test_handler.handle(msg1)
        test_handler.created_mock.assert_called_with(msg1)
        
        # Test multiple subjects mapping to same handler
        msg2 = mock_message("orders-updated")
        await test_handler.handle(msg2)
        test_handler.updated_mock.assert_called_with(msg2)
        
        msg3 = mock_message("orders.updated")
        await test_handler.handle(msg3)
        assert test_handler.updated_mock.call_count == 2
        
        # Test underscore notation
        msg4 = mock_message("orders_deleted")
        await test_handler.handle(msg4)
        test_handler.deleted_mock.assert_called_with(msg4)
        
        # Test single token
        msg5 = mock_message("payments")
        await test_handler.handle(msg5)
        test_handler.payments_mock.assert_called_with(msg5)
    
    @pytest.mark.asyncio
    async def test_handle_unhandled_subject(self, test_handler, mock_message):
        """Test handling of unhandled subjects"""
        msg = mock_message("unknown.subject")
        
        # Should not raise exception, should call fallback_handle
        await test_handler.handle(msg)
        
        # No handlers should be called
        test_handler.created_mock.assert_not_called()
        test_handler.updated_mock.assert_not_called()
        test_handler.deleted_mock.assert_not_called()
        test_handler.payments_mock.assert_not_called()
        
        # Message should be NAKed by fallback
        msg.nak.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_handle_no_decorator(self, mock_message):
        """Test handling when no @handle decorator is used"""
        class NoDecoratorHandler(ConsumerHandler):
            async def some_method(self, msg):
                pass
        
        handler = NoDecoratorHandler()
        msg = mock_message("orders.created")
        
        # Should call fallback_handle since no handlers registered
        await handler.handle(msg)
        msg.nak.assert_called_once()
        
        # Verify NAK was called (default fallback behavior)
        msg.nak.assert_called_once()
        msg.ack.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_handle_method_exception_propagation(self, mock_message):
        """Test that exceptions in implemented handler methods are still propagated"""
        class ErrorHandler(ConsumerHandler):
            @handle('orders.created')
            async def on_created(self, msg):
                raise ValueError("Test error")
        
        handler = ErrorHandler()
        msg = mock_message("orders.created")
        
        # Exceptions in implemented handlers should still be propagated
        with pytest.raises(ValueError, match="Test error"):
            await handler.handle(msg)
        
        # Message should not be acked/naked by fallback since exception was raised
        msg.nak.assert_not_called()
        msg.ack.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_successful_handler_no_fallback(self, test_handler, mock_message):
        """Test that successful handlers don't trigger fallback"""
        msg = mock_message("orders.created")
        
        # Should execute successfully without calling fallback
        await test_handler.handle(msg)
        
        # Handler was called
        test_handler.created_mock.assert_called_once_with(msg)
        
        # Fallback not triggered
        msg.nak.assert_not_called()
        msg.ack.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_wildcard_matching(self, mock_message):
        """Test wildcard pattern matching"""
        class WildcardHandler(ConsumerHandler):
            def __init__(self):
                self.calls = []
                super().__init__()
            
            @handle('orders.*')
            async def on_any_order(self, msg):
                self.calls.append(('wildcard', msg.subject))
            
            @handle('orders.created')
            async def on_created(self, msg):
                self.calls.append(('exact', msg.subject))
        
        handler = WildcardHandler()
        
        # Exact match should take priority
        assert 'orders.created' in handler._handler_map
        assert 'orders.*' in handler._handler_map
    
    @pytest.mark.asyncio
    async def test_fallback_handle_unhandled_subject(self, test_handler, mock_message):
        """Test fallback_handle for unhandled subjects"""
        # Message for unhandled subject (not in HandlerForTesting)
        msg = mock_message("users.created", {"id": 1})
        
        # Should call fallback_handle, not raise exception
        await test_handler.handle(msg)
        
        # Verify NAK was called (default fallback behavior)
        msg.nak.assert_called_once()
        msg.ack.assert_not_called()
    
    
    @pytest.mark.asyncio
    async def test_custom_fallback_handle(self, mock_message):
        """Test custom fallback_handle implementation"""
        class CustomFallbackHandler(ConsumerHandler):
            def __init__(self):
                self.fallback_calls = []
                super().__init__()
            
            @handle('orders.created')
            async def on_created(self, msg):
                pass
            
            async def fallback_handle(self, msg, reason="unknown"):
                # Custom behavior: ACK and log
                self.fallback_calls.append((msg.subject, reason))
                await msg.ack()  # Custom: ACK instead of NAK
        
        handler = CustomFallbackHandler()
        msg = mock_message("users.created", {"id": 1})
        
        await handler.handle(msg)
        
        # Verify custom fallback was called
        assert len(handler.fallback_calls) == 1
        assert handler.fallback_calls[0] == ("users.created", "no_handler")
        
        # Verify ACK was called (custom behavior)
        msg.ack.assert_called_once()
        msg.nak.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_fallback_handle_reasons(self, mock_message):
        """Test different fallback reasons"""
        class ReasonTrackingHandler(ConsumerHandler):
            def __init__(self):
                self.fallback_reasons = []
                super().__init__()
            
            @handle('orders.created')
            async def on_created(self, msg):
                # Handler registered but we'll test with different subject
                pass
            
            async def fallback_handle(self, msg, reason="unknown"):
                self.fallback_reasons.append(reason)
                await msg.nak()
        
        handler = ReasonTrackingHandler()
        
        # Test no_handler reason (subject not registered)
        msg1 = mock_message("users.created", {"id": 1})
        await handler.handle(msg1)
        
        # Verify reason was tracked
        assert "no_handler" in handler.fallback_reasons


if __name__ == "__main__":
    # Run basic tests without pytest
    handler = HandlerForTesting()
    
    print("=== Handler Mapping Tests ===")
    print(f"Registered subjects: {handler.get_subjects()}")
    
    print(f"\n=== Handler Methods ===")
    for method in sorted(handler.get_handler_methods()):
        print(f"  - {method}")
    
    print(f"\n=== Handler Map ===")
    for subject, method in handler._handler_map.items():
        print(f"  {subject} -> {method.__name__}()")
