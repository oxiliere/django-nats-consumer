from nats_consumer import JetstreamPullConsumer, JetstreamPushConsumer, operations
from nats_consumer.operations import api


class ExamplePullConsumer(JetstreamPullConsumer):
    stream_name = "example_pull"

    def setup(self):
        return [
            operations.CreateStream(
                name=self.stream_name,
                subjects=["example_pull.foo"],
                retention=api.RetentionPolicy.LIMITED_TIME,
                max_age=1000,
            )
        ]

    async def handle_message(self, message):
        pass


class ExamplePushConsumer(JetstreamPushConsumer):
    stream_name = "example_push"

    def setup(self):
        return [
            operations.CreateStream(
                name=self.stream_name,
                subjects=["example_push.foo"],
                retention=api.RetentionPolicy.LIMITED_TIME,
                max_age=1000,
            )
        ]

    async def handle_message(self, message):
        pass
