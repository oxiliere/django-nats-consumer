import pytest
from unittest.mock import AsyncMock
from nats_consumer.handler import ConsumerHandler



class TestHandler(ConsumerHandler):
    """Test handler implementation"""
    
    def __init__(self, subjects):
        super().__init__(subjects)
        
        # Mock methods for testing
        self.handle_created = AsyncMock()
        self.handle_updated = AsyncMock()
        self.handle_deleted = AsyncMock()
        self.handle_payments = AsyncMock()
        self.handle_old_archived = AsyncMock()


@pytest.fixture
def test_handler(handler_subjects):
    """Create a test handler instance"""
    return TestHandler(handler_subjects)


class TestConsumerHandler:
    """Test cases for ConsumerHandler"""
    
    def test_handler_mapping_dot_notation(self, test_handler):
        """Test dot notation subject mapping"""
        assert "orders.created" in test_handler._handler_map
        assert test_handler._handler_map["orders.created"] == "handle_created"
        
        assert "orders.old.archived" in test_handler._handler_map
        assert test_handler._handler_map["orders.old.archived"] == "handle_old_archived"
    
    def test_handler_mapping_hyphen_notation(self, test_handler):
        """Test hyphen notation subject mapping"""
        assert "orders-updated" in test_handler._handler_map
        assert test_handler._handler_map["orders-updated"] == "handle_updated"
    
    def test_handler_mapping_underscore_notation(self, test_handler):
        """Test underscore notation subject mapping"""
        assert "orders_deleted" in test_handler._handler_map
        assert test_handler._handler_map["orders_deleted"] == "handle_deleted"
    
    def test_handler_mapping_single_token(self, test_handler):
        """Test single token subject mapping"""
        assert "payments" in test_handler._handler_map
        assert test_handler._handler_map["payments"] == "handle_payments"
    
    def test_wildcard_subjects_ignored(self, test_handler):
        """Test that wildcard subjects are ignored"""
        assert "orders.*" not in test_handler._handler_map
        assert "users.>" not in test_handler._handler_map
    
    def test_get_handler_methods(self, test_handler):
        """Test getting list of handler methods"""
        methods = test_handler.get_handler_methods()
        
        expected_methods = [
            "handle_created",
            "handle_updated", 
            "handle_deleted",
            "handle_payments",
            "handle_old_archived"
        ]
        
        assert len(methods) == len(expected_methods)
        for method in expected_methods:
            assert method in methods
    
    def test_validate_handlers_all_implemented(self, test_handler):
        """Test validation when all handlers are implemented"""
        missing = test_handler.validate_handlers()
        assert len(missing) == 0
    
    def test_validate_handlers_missing_implementation(self):
        """Test validation when handlers are missing"""
        class IncompleteHandler(ConsumerHandler):
            def __init__(self):
                super().__init__(["orders.created", "orders.deleted"])
            
            async def handle_created(self, msg):
                pass
            # Missing handle_deleted
        
        handler = IncompleteHandler()
        missing = handler.validate_handlers()
        
        assert len(missing) == 1
        assert "handle_deleted" in missing
    
    @pytest.mark.asyncio
    async def test_handle_message_routing(self, test_handler, mock_message):
        """Test message routing to correct handler"""
        msg = mock_message("orders.created")
        
        await test_handler.handle(msg)
        
        test_handler.handle_created.assert_called_once_with(msg)
        test_handler.handle_updated.assert_not_called()
        test_handler.handle_deleted.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_handle_message_different_formats(self, test_handler, mock_message):
        """Test message routing for different subject formats"""
        # Test dot notation
        msg1 = mock_message("orders.created")
        await test_handler.handle(msg1)
        test_handler.handle_created.assert_called_with(msg1)
        
        # Test hyphen notation
        msg2 = mock_message("orders-updated")
        await test_handler.handle(msg2)
        test_handler.handle_updated.assert_called_with(msg2)
        
        # Test underscore notation
        msg3 = mock_message("orders_deleted")
        await test_handler.handle(msg3)
        test_handler.handle_deleted.assert_called_with(msg3)
        
        # Test single token
        msg4 = mock_message("payments")
        await test_handler.handle(msg4)
        test_handler.handle_payments.assert_called_with(msg4)
    
    @pytest.mark.asyncio
    async def test_handle_unhandled_subject(self, test_handler, mock_message):
        """Test handling of unhandled subjects"""
        msg = mock_message("unknown.subject")
        
        # Should not raise exception, just log warning
        await test_handler.handle(msg)
        
        # No handlers should be called
        test_handler.handle_created.assert_not_called()
        test_handler.handle_updated.assert_not_called()
        test_handler.handle_deleted.assert_not_called()
        test_handler.handle_payments.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_handle_missing_handler_method(self, mock_message):
        """Test handling when handler method is not implemented - should use fallback"""
        class IncompleteHandler(ConsumerHandler):
            def __init__(self):
                super().__init__(["orders.created"])
            # Missing handle_created method
        
        handler = IncompleteHandler()
        msg = mock_message("orders.created")
        
        # Should NOT raise exception anymore, should call fallback_handle
        await handler.handle(msg)
        
        # Verify NAK was called (default fallback behavior)
        msg.nak.assert_called_once()
        msg.ack.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_handle_method_exception_propagation(self, mock_message):
        """Test that exceptions in implemented handler methods are still propagated"""
        class ErrorHandler(ConsumerHandler):
            def __init__(self):
                super().__init__(["orders.created"])
            
            async def handle_created(self, msg):
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
    async def test_successful_handler_no_fallback(self, mock_message):
        """Test that successful handlers don't trigger fallback"""
        class SuccessfulHandler(ConsumerHandler):
            def __init__(self):
                super().__init__(["orders.created"])
                self.fallback_called = False
            
            async def handle_created(self, msg):
                # Successful handler
                pass
            
            async def fallback_handle(self, msg, reason="unknown"):
                self.fallback_called = True
                await msg.nak()
        
        handler = SuccessfulHandler()
        msg = mock_message("orders.created")
        
        # Should execute successfully without calling fallback
        await handler.handle(msg)
        
        # Verify fallback was NOT called
        assert not handler.fallback_called
        msg.nak.assert_not_called()
        msg.ack.assert_not_called()
    
    def test_collision_detection_warning(self, caplog):
        """Test that handler method collisions are detected and warned"""
        import logging
        
        # Create handler with colliding subjects
        class CollidingHandler(ConsumerHandler):
            def __init__(self):
                subjects = [
                    "orders.created",    # → handle_created()
                    "users-created",     # → handle_created() (collision!)
                    "items_created"      # → handle_created() (collision!)
                ]
                super().__init__(subjects)
        
        # Capture log messages
        with caplog.at_level(logging.WARNING):
            handler = CollidingHandler()
        
        # Check that collision warnings were logged
        collision_warnings = [record for record in caplog.records 
                            if "collision detected" in record.message.lower()]
        
        assert len(collision_warnings) >= 2  # At least 2 collisions detected
        
        # Verify the handler map still works (last one wins)
        assert "orders.created" in handler._handler_map
        assert "users-created" in handler._handler_map  
        assert "items_created" in handler._handler_map
        
        # All should map to handle_created
        assert handler._handler_map["orders.created"] == "handle_created"
        assert handler._handler_map["users-created"] == "handle_created"
        assert handler._handler_map["items_created"] == "handle_created"
    
    def test_subject_naming_recommendations(self, caplog):
        """Test that recommendations are logged for non-dot subjects"""
        import logging
        
        class NonDotHandler(ConsumerHandler):
            def __init__(self):
                subjects = [
                    "orders",           # No dots
                    "users-profile",    # Hyphen instead of dot
                    "items_inventory"   # Underscore instead of dot
                ]
                super().__init__(subjects)
        
        # Capture log messages
        with caplog.at_level(logging.INFO):
            handler = NonDotHandler()
        
        # Check that recommendation was logged
        recommendation_logs = [record for record in caplog.records 
                             if "RECOMMENDATION" in record.message]
        
        assert len(recommendation_logs) >= 1
        assert "dot notation" in recommendation_logs[0].message.lower()
    
    @pytest.mark.asyncio
    async def test_fallback_handle_unhandled_subject(self, mock_message):
        """Test fallback_handle for unhandled subjects"""
        handler = TestHandler(["orders.created"])  # Only handles orders.created
        
        # Message for unhandled subject
        msg = mock_message("users.created", {"id": 1})
        
        # Should call fallback_handle, not raise exception
        await handler.handle(msg)
        
        # Verify NAK was called (default fallback behavior)
        msg.nak.assert_called_once()
        msg.ack.assert_not_called()
    
    
    @pytest.mark.asyncio
    async def test_custom_fallback_handle(self, mock_message):
        """Test custom fallback_handle implementation"""
        class CustomFallbackHandler(ConsumerHandler):
            def __init__(self):
                super().__init__(["orders.created"])
                self.fallback_calls = []
            
            async def fallback_handle(self, msg, reason="unknown"):
                # Custom behavior: ACK and log
                self.fallback_calls.append((msg.subject, reason))
                await msg.ack()  # Custom: ACK instead of NAK
        
        handler = CustomFallbackHandler()
        msg = mock_message("users.created", {"id": 1})
        
        await handler.handle(msg)
        
        # Verify custom fallback was called
        assert len(handler.fallback_calls) == 1
        assert handler.fallback_calls[0] == ("users.created", "unhandled_subject")
        
        # Verify ACK was called (custom behavior)
        msg.ack.assert_called_once()
        msg.nak.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_fallback_handle_reasons(self, mock_message):
        """Test different fallback reasons"""
        class ReasonTrackingHandler(ConsumerHandler):
            def __init__(self):
                super().__init__(["orders.created"])
                self.fallback_reasons = []
            
            async def fallback_handle(self, msg, reason="unknown"):
                self.fallback_reasons.append(reason)
                await msg.nak()
        
        handler = ReasonTrackingHandler()
        
        # Test unhandled_subject reason
        msg1 = mock_message("users.created", {"id": 1})
        await handler.handle(msg1)
        
        # Test not_implemented reason
        msg2 = mock_message("orders.created", {"id": 2})
        await handler.handle(msg2)  # handle_created not implemented
        
        # Verify reasons were tracked
        assert "unhandled_subject" in handler.fallback_reasons
        assert "not_implemented" in handler.fallback_reasons


if __name__ == "__main__":
    # Run basic tests without pytest
    handler = TestHandler()
    
    print("=== Handler Mapping Tests ===")
    print(f"Dot notation: orders.created -> {handler._handler_map.get('orders.created')}")
    print(f"Hyphen notation: orders-updated -> {handler._handler_map.get('orders-updated')}")
    print(f"Underscore notation: orders_deleted -> {handler._handler_map.get('orders_deleted')}")
    print(f"Single token: payments -> {handler._handler_map.get('payments')}")
    print(f"Multi-level: orders.old.archived -> {handler._handler_map.get('orders.old.archived')}")
    
    print(f"\n=== Wildcard Handling ===")
    print(f"orders.* in map: {'orders.*' in handler._handler_map}")
    print(f"users.> in map: {'users.>' in handler._handler_map}")
    
    print(f"\n=== Handler Methods ===")
    for method in sorted(handler.get_handler_methods()):
        print(f"  - {method}")
    
    print(f"\n=== Validation ===")
    missing = handler.validate_handlers()
    if missing:
        print(f"Missing handlers: {missing}")
    else:
        print("All handlers implemented ✅")
