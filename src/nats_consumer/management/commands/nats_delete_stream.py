import asyncio
import logging

from django.core.management.base import BaseCommand, CommandError

from nats_consumer.operations import DeleteStream


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Delete a NATS JetStream stream"

    def add_arguments(self, parser):
        parser.add_argument(
            "stream_name",
            type=str,
            help="Name of the stream to delete"
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Skip confirmation prompt"
        )

    def handle(self, *args, **options):
        stream_name = options["stream_name"]
        force = options.get("force", False)

        if not force:
            confirm = input(
                f"Are you sure you want to delete stream '{stream_name}'? "
                f"This action cannot be undone. [y/N]: "
            )
            if confirm.lower() not in ["y", "yes"]:
                self.stdout.write(self.style.WARNING("Operation cancelled."))
                return

        try:
            delete_op = DeleteStream(stream_name)
            asyncio.run(delete_op.execute())
            self.stdout.write(
                self.style.SUCCESS(f"Successfully deleted stream '{stream_name}'")
            )
        except Exception as e:
            raise CommandError(f"Failed to delete stream: {e}")
