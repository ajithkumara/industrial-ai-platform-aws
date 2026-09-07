import json
from pathlib import Path
from shared.logger import setup_logger

logger = setup_logger("checkpoint")

class FileCheckpointManager:
    """Manages partition checkpoints locally in a JSON file."""

    def __init__(self, checkpoint_path: Path):
        self.checkpoint_path = Path(checkpoint_path)
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        self.checkpoints = self._load_checkpoints()

    def _load_checkpoints(self) -> dict:
        """Loads checkpoints from disk, returning an empty dict if not found or invalid."""
        if self.checkpoint_path.exists():
            try:
                with open(self.checkpoint_path, "r") as f:
                    data = json.load(f)
                    logger.info("Loaded partition checkpoints from disk.")
                    return data
            except Exception as e:
                logger.error(f"Error loading checkpoints file: {e}")
        return {}

    def get_checkpoint(self, partition_id: str) -> dict:
        """Returns the last saved checkpoint details (offset/sequence number) for the partition."""
        return self.checkpoints.get(partition_id)

    def get_starting_position(self, partition_id: str) -> str:
        """Returns the starting position (offset) for the partition, defaulting to beginning (-1)."""
        checkpoint = self.get_checkpoint(partition_id)
        if checkpoint and "offset" in checkpoint:
            return checkpoint["offset"]
        return "-1" # Start from the beginning if no checkpoint exists

    def update_checkpoint(self, partition_id: str, offset: str, sequence_number: int):
        """Updates and persists the checkpoint for a specific partition."""
        self.checkpoints[partition_id] = {
            "offset": offset,
            "sequence_number": sequence_number
        }
        try:
            with open(self.checkpoint_path, "w") as f:
                json.dump(self.checkpoints, f, indent=4)
            logger.info(f"Updated checkpoint for Partition {partition_id}: Offset={offset}, Seq={sequence_number}")
        except Exception as e:
            logger.error(f"Error updating checkpoint on disk: {e}")
