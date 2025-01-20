from django.db import migrations

from .operations import CreateStream, DeleteStream, UpdateStream

__all__ = ["CreateStream", "DeleteStream", "UpdateStream", "NatsForwardMigration"]


class NatsForwardMigration(migrations.Migration):
    # async def forward(self, apps, schema_editor):
    #     for op in self.operations:
    #         await op.execute()

    pass
