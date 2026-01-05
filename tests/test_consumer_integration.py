import pytest
import json
from unittest.mock import Mock, AsyncMock, patch
from nats.aio.msg import Msg
from nats_consumer.consumer import JetstreamPushConsumer, JetstreamPullConsumer
from nats_consumer import ConsumerHandler, handle


class IntegrationTestHandler(ConsumerHandler):
    """Handler for integration tests using @handle decorator"""
    
    def __init__(self):
        self.calls = []
        super().__init__()
    
    @handle('integration.created')
    async def on_created(self, msg):
        data = json.loads(msg.data.decode())
        self.calls.append(("created", data))
    
    @handle('integration.updated', 'integration-updated')
    async def on_updated(self, msg):
        data = json.loads(msg.data.decode())
        self.calls.append(("updated", data))
    
    @handle('integration.deleted', 'integration_deleted')
    async def on_deleted(self, msg):
        data = json.loads(msg.data.decode())
        self.calls.append(("deleted", data))


class PushConsumerWithHandler(JetstreamPushConsumer):
    """Push consumer with handler for testing"""
    stream_name = "test_push_integration"
    subjects = ["integration.created", "integration-updated", "integration_deleted"]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.handler = IntegrationTestHandler()
    
    async def handle_message(self, message):
        await self.handler.handle(message)


class PullConsumerWithHandler(JetstreamPullConsumer):
    """Pull consumer with handler for testing"""
    stream_name = "test_pull_integration"
    subjects = ["integration.created", "integration-updated", "integration_deleted"]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.handler = IntegrationTestHandler()
    
    async def handle_message(self, message):
        await self.handler.handle(message)


@pytest.fixture
def integration_handler():
    """Create an integration handler instance"""
    return IntegrationTestHandler()


@pytest.fixture
def push_consumer_with_handler(mock_django_settings, mock_nats_client):
    """Create a push consumer with handler for testing"""
    with patch('nats_consumer.consumer.NatsConsumerBase.__init__', return_value=None):
        consumer = PushConsumerWithHandler()
        consumer._nats_client = mock_nats_client
        consumer._running = False
        consumer._stop_event = AsyncMock()
        consumer.subscriptions = []
        consumer.total_success_count = 0
        consumer.total_error_count = 0
        return consumer


@pytest.fixture
def pull_consumer_with_handler(mock_django_settings, mock_nats_client):
    """Create a pull consumer with handler for testing"""
    with patch('nats_consumer.consumer.NatsConsumerBase.__init__', return_value=None):
        consumer = PullConsumerWithHandler()
        consumer._nats_client = mock_nats_client
        consumer._running = False
        consumer._stop_event = AsyncMock()
        consumer.subscriptions = []
        consumer.total_success_count = 0
        consumer.total_error_count = 0
        return consumer


class TestConsumerIntegration:
    """Integration tests for consumers with handlers"""
    
    
    @pytest.mark.asyncio
    async def test_push_consumer_handler_integration(self, push_consumer_with_handler, mock_message):
        """Test Push consumer with handler integration"""
        consumer = push_consumer_with_handler
        
        # Test different subject formats
        test_cases = [
            ("integration.created", {"id": 1, "action": "create"}),
            ("integration-updated", {"id": 2, "action": "update"}),
            ("integration_deleted", {"id": 3, "action": "delete"})
        ]
        
        for subject, data in test_cases:
            msg = mock_message(subject, data)
            await consumer.handle_message(msg)
        
        # Verify handler received all calls
        assert len(consumer.handler.calls) == 3
        
        # Verify correct routing
        calls_by_action = {call[0]: call[1] for call in consumer.handler.calls}
        assert calls_by_action["created"]["id"] == 1
        assert calls_by_action["updated"]["id"] == 2
        assert calls_by_action["deleted"]["id"] == 3
    
    @pytest.mark.asyncio
    async def test_pull_consumer_handler_integration(self, pull_consumer_with_handler, mock_message):
        """Test Pull consumer with handler integration"""
        consumer = pull_consumer_with_handler
        
        # Test message handling
        msg = mock_message("integration.created", {"id": 100})
        await consumer.handle_message(msg)
        
        # Verify handler was called
        assert len(consumer.handler.calls) == 1
        assert consumer.handler.calls[0] == ("created", {"id": 100})
    
    def test_consumer_configuration_consistency(self, push_consumer_with_handler, pull_consumer_with_handler):
        """Test consumer configuration consistency"""
        # Both should have same subjects
        assert push_consumer_with_handler.subjects == pull_consumer_with_handler.subjects
        
        # Both should use subject filtering now
        assert hasattr(push_consumer_with_handler, 'get_filter_subject')
        assert hasattr(pull_consumer_with_handler, 'get_filter_subject')
    
    def test_filter_subject_fallback_to_subjects_zero(self, mock_django_settings, mock_nats_client):
        """Test that filter_subject falls back to subjects[0] when not specified"""
        with patch('nats_consumer.consumer.NatsConsumerBase.__init__', return_value=None):
            class NoFilterConsumer(JetstreamPushConsumer):
                stream_name = "test_fallback"
                subjects = ["orders.created", "orders.updated", "orders.deleted"]
                # No filter_subject specified
            
            consumer = NoFilterConsumer()
            consumer._nats_client = mock_nats_client
            
            # Should fallback to subjects[0]
            filter_subject = consumer.get_filter_subject()
            assert filter_subject == "orders.created"  # subjects[0]
    
    def test_explicit_filter_subject_takes_priority(self, mock_django_settings, mock_nats_client):
        """Test that explicit filter_subject takes priority over subjects[0]"""
        with patch('nats_consumer.consumer.NatsConsumerBase.__init__', return_value=None):
            class ExplicitFilterConsumer(JetstreamPushConsumer):
                stream_name = "test_explicit"
                subjects = ["orders.created", "orders.updated", "orders.deleted"]
                filter_subject = "orders.*"  # Explicit filter
            
            consumer = ExplicitFilterConsumer()
            consumer._nats_client = mock_nats_client
            
            # Should use explicit filter_subject
            filter_subject = consumer.get_filter_subject()
            assert filter_subject == "orders.*"
    
    @pytest.mark.asyncio
    async def test_handler_error_propagation(self, mock_message, mock_django_settings, mock_nats_client):
        """Test that handler errors are properly propagated"""
        class ErrorHandler(ConsumerHandler):
            @handle('test.error')
            async def on_error(self, msg):
                raise ValueError("Handler error")
        
        with patch('nats_consumer.consumer.NatsConsumerBase.__init__', return_value=None):
            class ErrorConsumer(JetstreamPushConsumer):
                stream_name = "test_error"
                subjects = ["test.error"]
                
                def __init__(self):
                    super().__init__()
                    self.handler = ErrorHandler()
                
                async def handle_message(self, message):
                    await self.handler.handle(message)
            
            consumer = ErrorConsumer()
            msg = mock_message("test.error", {"test": "data"})
            
            with pytest.raises(ValueError, match="Handler error"):
                await consumer.handle_message(msg)
    
    @pytest.mark.asyncio
    async def test_consumer_without_handler_backward_compatibility(self, mock_message, mock_django_settings, mock_nats_client):
        """Test that consumers work without handlers (backward compatibility)"""
        with patch('nats_consumer.consumer.NatsConsumerBase.__init__', return_value=None):
            class LegacyConsumer(JetstreamPushConsumer):
                stream_name = "legacy"
                subjects = ["legacy.test"]
                
                def __init__(self):
                    super().__init__()
                    self.processed_messages = []
                
                async def handle_message(self, message):
                    data = json.loads(message.data.decode())
                    self.processed_messages.append(data)
            
            consumer = LegacyConsumer()
            msg = mock_message("legacy.test", {"legacy": True})
            
            await consumer.handle_message(msg)
            
            assert len(consumer.processed_messages) == 1
            assert consumer.processed_messages[0]["legacy"] == True
    
    def test_handler_mapping_consistency(self, push_consumer_with_handler, pull_consumer_with_handler):
        """Test that handler mapping is consistent across consumer types"""
        # Both should have same subjects registered
        push_subjects = set(push_consumer_with_handler.handler.get_subjects())
        pull_subjects = set(pull_consumer_with_handler.handler.get_subjects())
        
        assert push_subjects == pull_subjects
        
        # Check expected subjects are registered
        expected_subjects = {
            "integration.created",
            "integration.updated",
            "integration-updated", 
            "integration.deleted",
            "integration_deleted"
        }
        
        assert expected_subjects.issubset(push_subjects)
        assert expected_subjects.issubset(pull_subjects)
    
    def test_consumer_type_differences(self, push_consumer_with_handler, pull_consumer_with_handler):
        """Test that consumers have different configurations as expected"""
        # Different stream names
        assert push_consumer_with_handler.stream_name != pull_consumer_with_handler.stream_name
        
        # Different consumer types
        assert type(push_consumer_with_handler).__name__ == "PushConsumerWithHandler"
        assert type(pull_consumer_with_handler).__name__ == "PullConsumerWithHandler"
        
        # Same subjects
        assert push_consumer_with_handler.subjects == pull_consumer_with_handler.subjects


if __name__ == "__main__":
    pytest.main([__file__])
