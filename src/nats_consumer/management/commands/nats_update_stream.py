import asyncio
import logging

from django.core.management.base import BaseCommand, CommandError

from nats_consumer import get_nats_client
from nats_consumer.operations import UpdateStream, api


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Update a NATS JetStream stream configuration"

    def add_arguments(self, parser):
        parser.add_argument(
            "stream_name",
            type=str,
            help="Name of the stream to update"
        )
        parser.add_argument(
            "--subjects",
            type=str,
            nargs="+",
            help="Subjects for the stream (space-separated)"
        )
        parser.add_argument(
            "--max-msgs",
            type=int,
            help="Maximum number of messages to store"
        )
        parser.add_argument(
            "--max-bytes",
            type=int,
            help="Maximum bytes to store"
        )
        parser.add_argument(
            "--max-age",
            type=int,
            help="Maximum age of messages in seconds"
        )
        parser.add_argument(
            "--max-msg-size",
            type=int,
            help="Maximum size of a single message in bytes"
        )
        parser.add_argument(
            "--storage",
            type=str,
            choices=["file", "memory"],
            help="Storage type: file or memory"
        )
        parser.add_argument(
            "--retention",
            type=str,
            choices=["limits", "interest", "workqueue"],
            help="Retention policy: limits, interest, or workqueue"
        )
        parser.add_argument(
            "--replicas",
            type=int,
            help="Number of replicas (1-5)"
        )
        parser.add_argument(
            "--discard",
            type=str,
            choices=["old", "new"],
            help="Discard policy when limits are reached: old or new"
        )
        parser.add_argument(
            "--duplicate-window",
            type=int,
            help="Duplicate tracking window in seconds"
        )

    def handle(self, *args, **options):
        stream_name = options["stream_name"]
        
        # Collect update parameters
        update_params = {}
        
        if options.get("subjects"):
            update_params["subjects"] = options["subjects"]
        
        if options.get("max_msgs") is not None:
            update_params["max_msgs"] = options["max_msgs"]
        
        if options.get("max_bytes") is not None:
            update_params["max_bytes"] = options["max_bytes"]
        
        if options.get("max_age") is not None:
            update_params["max_age"] = options["max_age"]
        
        if options.get("max_msg_size") is not None:
            update_params["max_msg_size"] = options["max_msg_size"]
        
        if options.get("storage"):
            storage_map = {
                "file": api.StorageType.FILE,
                "memory": api.StorageType.MEMORY
            }
            update_params["storage"] = storage_map[options["storage"]]
        
        if options.get("retention"):
            retention_map = {
                "limits": api.RetentionPolicy.LIMITS,
                "interest": api.RetentionPolicy.INTEREST,
                "workqueue": api.RetentionPolicy.WORKQUEUE
            }
            update_params["retention"] = retention_map[options["retention"]]
        
        if options.get("replicas") is not None:
            update_params["num_replicas"] = options["replicas"]
        
        if options.get("discard"):
            discard_map = {
                "old": api.DiscardPolicy.OLD,
                "new": api.DiscardPolicy.NEW
            }
            update_params["discard"] = discard_map[options["discard"]]
        
        if options.get("duplicate_window") is not None:
            update_params["duplicate_window"] = options["duplicate_window"] * 1_000_000_000  # Convert to nanoseconds
        
        if not update_params:
            raise CommandError("No update parameters provided. Use --help to see available options.")
        
        try:
            asyncio.run(self._update_stream(stream_name, update_params))
        except Exception as e:
            raise CommandError(f"Failed to update stream: {e}")

    async def _update_stream(self, stream_name: str, update_params: dict):
        """Update the specified stream with new configuration"""
        nats_client = await get_nats_client()
        
        try:
            js = nats_client.jetstream()
            
            # Get current stream info
            try:
                stream_info = await js.stream_info(stream_name)
                current_config = stream_info.config
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"Stream '{stream_name}' does not exist: {e}")
                )
                return
            
            # Display current configuration
            self.stdout.write(self.style.WARNING("\nCurrent configuration:"))
            self._display_config(current_config)
            
            # Create updated config by merging current with updates
            config_dict = {
                "name": stream_name,
                "subjects": update_params.get("subjects", current_config.subjects),
                "retention": update_params.get("retention", current_config.retention),
                "max_consumers": current_config.max_consumers,
                "max_msgs": update_params.get("max_msgs", current_config.max_msgs),
                "max_bytes": update_params.get("max_bytes", current_config.max_bytes),
                "max_age": update_params.get("max_age", current_config.max_age) if "max_age" in update_params else current_config.max_age,
                "max_msg_size": update_params.get("max_msg_size", current_config.max_msg_size),
                "storage": update_params.get("storage", current_config.storage),
                "num_replicas": update_params.get("num_replicas", current_config.num_replicas),
                "discard": update_params.get("discard", current_config.discard),
                "duplicate_window": update_params.get("duplicate_window", current_config.duplicate_window),
            }
            
            # Use UpdateStream operation
            update_op = UpdateStream(**config_dict)
            await update_op.execute(nats_client=nats_client)
            
            self.stdout.write(self.style.SUCCESS(f"\nSuccessfully updated stream '{stream_name}'"))
            
            # Display updated configuration
            updated_info = await js.stream_info(stream_name)
            self.stdout.write(self.style.SUCCESS("\nUpdated configuration:"))
            self._display_config(updated_info.config)
            
        except Exception as e:
            logger.error(f"Error updating stream '{stream_name}': {e}")
            raise
        finally:
            await nats_client.close()
    
    def _display_config(self, config):
        """Display stream configuration"""
        self.stdout.write(f"  Subjects: {config.subjects}")
        self.stdout.write(f"  Storage: {config.storage}")
        self.stdout.write(f"  Retention: {config.retention}")
        self.stdout.write(f"  Max messages: {config.max_msgs}")
        self.stdout.write(f"  Max bytes: {config.max_bytes}")
        self.stdout.write(f"  Max age: {config.max_age / 1_000_000_000 if config.max_age else 0} seconds")
        self.stdout.write(f"  Replicas: {config.num_replicas}")
