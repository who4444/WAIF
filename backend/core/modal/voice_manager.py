"""
Voice Reference Manager for FishSpeech S2 Voice Cloning

Manages persistent storage and metadata for voice references used in zero-shot
voice cloning. Voice references are stored on disk and can be reused across
multiple TTS generation requests.
"""

import os
import hashlib
import json
from pathlib import Path
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional, List
import base64


@dataclass
class VoiceReference:
    """Metadata for a stored voice reference."""
    id: str
    audio_path: str
    transcription: str
    created_at: str
    file_hash: str
    duration_seconds: float = 0.0
    format: str = "wav"


class VoiceManager:
    """Manages persistent voice reference storage and retrieval."""
    
    # Valid reference ID pattern: alphanumeric, hyphens, underscores, spaces (max 255 chars)
    REFERENCE_ID_PATTERN = r"^[a-zA-Z0-9\-_ ]+$"
    MAX_REFERENCE_ID_LENGTH = 255
    MAX_AUDIO_SIZE = 10 * 1024 * 1024  # 10 MB
    
    def __init__(self, reference_dir: Optional[str] = None):
        """
        Initialize VoiceManager.
        
        Args:
            reference_dir: Directory to store voice references. 
                          Defaults to config.FISHSPEECH_REFERENCE_DIR
        """
        if reference_dir is None:
            from config import FISHSPEECH_REFERENCE_DIR
            reference_dir = FISHSPEECH_REFERENCE_DIR
        
        self.reference_dir = Path(reference_dir)
        self.reference_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_file = self.reference_dir / "metadata.json"
        self._metadata = self._load_metadata()
    
    def _load_metadata(self) -> dict:
        """Load voice reference metadata from disk."""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[voice_manager] Warning: Failed to load metadata: {e}")
                return {}
        return {}
    
    def _save_metadata(self) -> None:
        """Save voice reference metadata to disk."""
        try:
            with open(self.metadata_file, "w") as f:
                json.dump(self._metadata, f, indent=2)
        except Exception as e:
            print(f"[voice_manager] Error saving metadata: {e}")
    
    def validate_reference_id(self, reference_id: str) -> bool:
        """
        Validate reference ID format.
        
        Args:
            reference_id: Reference ID to validate
            
        Returns:
            True if valid, False otherwise
        """
        import re
        if len(reference_id) > self.MAX_REFERENCE_ID_LENGTH:
            return False
        return bool(re.match(self.REFERENCE_ID_PATTERN, reference_id))
    
    def save_reference(
        self,
        audio_bytes: bytes,
        reference_id: str,
        transcription: str,
        audio_format: str = "wav",
    ) -> Optional[VoiceReference]:
        """
        Save a voice reference to disk.
        
        Args:
            audio_bytes: Audio file bytes
            reference_id: Unique identifier for the voice (alphanumeric, hyphens, underscores, spaces)
            transcription: Transcription text of the audio (for context during inference)
            audio_format: Audio format (default: "wav")
            
        Returns:
            VoiceReference object if successful, None otherwise
            
        Raises:
            ValueError: If reference_id is invalid or audio_bytes too large
        """
        # Validate reference ID
        if not self.validate_reference_id(reference_id):
            raise ValueError(
                f"Invalid reference_id '{reference_id}'. "
                f"Must match pattern {self.REFERENCE_ID_PATTERN} and be ≤{self.MAX_REFERENCE_ID_LENGTH} chars"
            )
        
        # Check audio size
        if len(audio_bytes) > self.MAX_AUDIO_SIZE:
            raise ValueError(f"Audio file too large: {len(audio_bytes)} bytes (max: {self.MAX_AUDIO_SIZE})")
        
        # Create reference directory
        ref_dir = self.reference_dir / reference_id
        ref_dir.mkdir(parents=True, exist_ok=True)
        
        # Save audio file
        audio_path = ref_dir / f"sample.{audio_format}"
        audio_path.write_bytes(audio_bytes)
        
        # Save transcription
        transcription_path = ref_dir / "sample.txt"
        transcription_path.write_text(transcription)
        
        # Calculate file hash
        file_hash = hashlib.sha256(audio_bytes).hexdigest()
        
        # Estimate duration (rough estimate: typical sample rate ~24kHz, stereo)
        estimated_duration = len(audio_bytes) / (24000 * 2 * 2)  # bytes / (sample_rate * channels * bytes_per_sample)
        
        # Create metadata entry
        ref = VoiceReference(
            id=reference_id,
            audio_path=str(audio_path),
            transcription=transcription,
            created_at=datetime.now().isoformat(),
            file_hash=file_hash,
            duration_seconds=estimated_duration,
            format=audio_format,
        )
        
        # Store metadata
        self._metadata[reference_id] = asdict(ref)
        self._save_metadata()
        
        print(f"[voice_manager] Saved voice reference: {reference_id} ({len(audio_bytes)} bytes)")
        return ref
    
    def get_reference(self, reference_id: str) -> Optional[VoiceReference]:
        """
        Retrieve a voice reference by ID.
        
        Args:
            reference_id: Reference ID to retrieve
            
        Returns:
            VoiceReference object if found, None otherwise
        """
        if reference_id not in self._metadata:
            print(f"[voice_manager] Reference not found: {reference_id}")
            return None
        
        data = self._metadata[reference_id]
        return VoiceReference(**data)
    
    def get_reference_audio_path(self, reference_id: str) -> Optional[Path]:
        """
        Get the file path to a reference audio file.
        
        Args:
            reference_id: Reference ID
            
        Returns:
            Path object if found, None otherwise
        """
        ref = self.get_reference(reference_id)
        if ref and Path(ref.audio_path).exists():
            return Path(ref.audio_path)
        return None
    
    def get_reference_as_base64(self, reference_id: str) -> Optional[str]:
        """
        Get a reference audio as base64-encoded string.
        
        Args:
            reference_id: Reference ID
            
        Returns:
            Base64 string (including data URI prefix) if found, None otherwise
        """
        audio_path = self.get_reference_audio_path(reference_id)
        if not audio_path:
            return None
        
        audio_bytes = audio_path.read_bytes()
        ref = self.get_reference(reference_id)
        
        # Return as data URI
        b64 = base64.b64encode(audio_bytes).decode()
        mime_type = f"audio/{ref.format}"
        return f"data:{mime_type};base64,{b64}"
    
    def list_references(self) -> List[VoiceReference]:
        """
        List all stored voice references.
        
        Returns:
            List of VoiceReference objects
        """
        refs = []
        for ref_id, data in self._metadata.items():
            try:
                ref = VoiceReference(**data)
                refs.append(ref)
            except Exception as e:
                print(f"[voice_manager] Error loading reference {ref_id}: {e}")
        return refs
    
    def delete_reference(self, reference_id: str) -> bool:
        """
        Delete a voice reference from disk.
        
        Args:
            reference_id: Reference ID to delete
            
        Returns:
            True if successful, False otherwise
        """
        if reference_id not in self._metadata:
            print(f"[voice_manager] Reference not found: {reference_id}")
            return False
        
        # Remove directory
        ref_dir = self.reference_dir / reference_id
        if ref_dir.exists():
            import shutil
            try:
                shutil.rmtree(ref_dir)
            except Exception as e:
                print(f"[voice_manager] Error deleting reference directory: {e}")
                return False
        
        # Remove metadata
        del self._metadata[reference_id]
        self._save_metadata()
        
        print(f"[voice_manager] Deleted voice reference: {reference_id}")
        return True
    
    def reference_exists(self, reference_id: str) -> bool:
        """Check if a reference exists."""
        return reference_id in self._metadata


# Global instance
_voice_manager: Optional[VoiceManager] = None


def get_voice_manager() -> VoiceManager:
    """Get or create the global VoiceManager instance."""
    global _voice_manager
    if _voice_manager is None:
        _voice_manager = VoiceManager()
    return _voice_manager
