"""
Fuel Monitor Module
Handles fuel status debouncing and emergency mode state machine.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Callable

from ..config import FuelStatus, SystemMode, FUEL_DEBOUNCE_SECONDS

logger = logging.getLogger(__name__)


class EmergencyState(Enum):
    """Emergency mode states"""
    INACTIVE = "inactive"          # Normal operation
    PENDING = "pending"            # Low fuel detected, waiting for debounce
    ACTIVE = "active"              # Emergency mode active
    AWAITING_ACK = "awaiting_ack"  # Fuel restored, waiting for user acknowledgment


@dataclass
class FuelMonitorState:
    """Current state of the fuel monitor"""
    raw_fuel_status: int  # Raw value from sensor
    debounced_fuel_status: int  # Debounced value
    emergency_state: EmergencyState
    system_mode: str
    low_fuel_start: Optional[datetime]  # When low fuel was first detected
    emergency_triggered_at: Optional[datetime]  # When emergency mode activated
    
    def to_dict(self) -> dict:
        return {
            "raw_fuel_status": self.raw_fuel_status,
            "debounced_fuel_status": self.debounced_fuel_status,
            "emergency_state": self.emergency_state.value,
            "system_mode": self.system_mode,
            "is_fuel_low": self.debounced_fuel_status == FuelStatus.LOW,
            "is_emergency": self.emergency_state == EmergencyState.ACTIVE,
            "awaiting_acknowledgment": self.emergency_state == EmergencyState.AWAITING_ACK
        }


class FuelMonitor:
    """
    Monitors fuel status with debouncing and manages emergency mode.
    
    State Machine:
    INACTIVE -> PENDING: Low fuel detected
    PENDING -> INACTIVE: Fuel restored before debounce timeout
    PENDING -> ACTIVE: Debounce timeout reached (emergency mode)
    ACTIVE -> AWAITING_ACK: Fuel restored while in emergency
    AWAITING_ACK -> INACTIVE: User acknowledges
    AWAITING_ACK -> ACTIVE: Fuel goes low again before acknowledgment
    """
    
    def __init__(
        self,
        debounce_seconds: float = FUEL_DEBOUNCE_SECONDS,
        on_emergency_trigger: Optional[Callable[[], None]] = None,
        on_emergency_clear: Optional[Callable[[], None]] = None
    ):
        self._debounce_seconds = debounce_seconds
        self._on_emergency_trigger = on_emergency_trigger
        self._on_emergency_clear = on_emergency_clear
        
        # State
        self._raw_status = FuelStatus.NORMAL
        self._debounced_status = FuelStatus.NORMAL
        self._emergency_state = EmergencyState.INACTIVE
        self._low_fuel_start: Optional[datetime] = None
        self._emergency_triggered_at: Optional[datetime] = None
        self._last_update: Optional[datetime] = None
    
    def update(self, fuel_status: int) -> FuelMonitorState:
        """
        Update fuel status and process state machine.
        
        Args:
            fuel_status: Raw fuel status (1 = normal, 0 = low)
        
        Returns:
            Current FuelMonitorState
        """
        now = datetime.now()
        self._raw_status = fuel_status
        self._last_update = now
        
        # State machine transitions
        if self._emergency_state == EmergencyState.INACTIVE:
            self._handle_inactive_state(fuel_status, now)
        
        elif self._emergency_state == EmergencyState.PENDING:
            self._handle_pending_state(fuel_status, now)
        
        elif self._emergency_state == EmergencyState.ACTIVE:
            self._handle_active_state(fuel_status, now)
        
        elif self._emergency_state == EmergencyState.AWAITING_ACK:
            self._handle_awaiting_ack_state(fuel_status, now)
        
        return self.get_state()
    
    def _handle_inactive_state(self, fuel_status: int, now: datetime) -> None:
        """Handle state when system is in normal operation"""
        if fuel_status == FuelStatus.LOW:
            # Start debounce timer
            self._emergency_state = EmergencyState.PENDING
            self._low_fuel_start = now
            logger.info("Low fuel detected, starting debounce timer")
    
    def _handle_pending_state(self, fuel_status: int, now: datetime) -> None:
        """Handle state when waiting for debounce"""
        if fuel_status == FuelStatus.NORMAL:
            # Fuel restored before timeout - false alarm
            self._emergency_state = EmergencyState.INACTIVE
            self._low_fuel_start = None
            logger.info("Fuel restored during debounce - false alarm")
        else:
            # Check if debounce timeout reached
            if self._low_fuel_start:
                elapsed = (now - self._low_fuel_start).total_seconds()
                if elapsed >= self._debounce_seconds:
                    # Trigger emergency mode
                    self._emergency_state = EmergencyState.ACTIVE
                    self._debounced_status = FuelStatus.LOW
                    self._emergency_triggered_at = now
                    logger.warning("EMERGENCY MODE ACTIVATED - Low fuel confirmed")
                    
                    if self._on_emergency_trigger:
                        self._on_emergency_trigger()
    
    def _handle_active_state(self, fuel_status: int, now: datetime) -> None:
        """Handle state when in emergency mode"""
        if fuel_status == FuelStatus.NORMAL:
            # Fuel restored - wait for user acknowledgment
            self._emergency_state = EmergencyState.AWAITING_ACK
            self._debounced_status = FuelStatus.NORMAL
            logger.info("Fuel restored - awaiting user acknowledgment to exit emergency")
    
    def _handle_awaiting_ack_state(self, fuel_status: int, now: datetime) -> None:
        """Handle state when waiting for user acknowledgment"""
        if fuel_status == FuelStatus.LOW:
            # Fuel went low again - back to active emergency
            self._emergency_state = EmergencyState.ACTIVE
            self._debounced_status = FuelStatus.LOW
            logger.warning("Fuel low again while awaiting acknowledgment")
    
    def acknowledge_emergency(self) -> bool:
        """
        User acknowledges and clears emergency mode.
        
        Returns:
            True if acknowledgment was accepted, False if not in awaiting state
        """
        if self._emergency_state == EmergencyState.AWAITING_ACK:
            self._emergency_state = EmergencyState.INACTIVE
            self._low_fuel_start = None
            self._emergency_triggered_at = None
            logger.info("Emergency mode cleared by user acknowledgment")
            
            if self._on_emergency_clear:
                self._on_emergency_clear()
            
            return True
        
        logger.warning("Acknowledgment rejected - not in awaiting state")
        return False
    
    def force_clear_emergency(self) -> None:
        """
        Force clear emergency mode (admin override).
        Use with caution.
        """
        self._emergency_state = EmergencyState.INACTIVE
        self._debounced_status = FuelStatus.NORMAL
        self._low_fuel_start = None
        self._emergency_triggered_at = None
        logger.warning("Emergency mode force cleared")
    
    def get_state(self) -> FuelMonitorState:
        """Get current fuel monitor state"""
        return FuelMonitorState(
            raw_fuel_status=self._raw_status,
            debounced_fuel_status=self._debounced_status,
            emergency_state=self._emergency_state,
            system_mode=self._get_system_mode(),
            low_fuel_start=self._low_fuel_start,
            emergency_triggered_at=self._emergency_triggered_at
        )
    
    def _get_system_mode(self) -> str:
        """Determine current system mode"""
        if self._emergency_state in (EmergencyState.ACTIVE, EmergencyState.AWAITING_ACK):
            return SystemMode.EMERGENCY
        return SystemMode.NORMAL
    
    @property
    def is_emergency(self) -> bool:
        """Check if system is in emergency mode"""
        return self._emergency_state in (EmergencyState.ACTIVE, EmergencyState.AWAITING_ACK)
    
    @property
    def is_fuel_low(self) -> bool:
        """Check if fuel is confirmed low (debounced)"""
        return self._debounced_status == FuelStatus.LOW
    
    @property
    def debounce_seconds(self) -> float:
        """Get debounce duration"""
        return self._debounce_seconds
    
    @debounce_seconds.setter
    def debounce_seconds(self, value: float) -> None:
        """Set debounce duration"""
        self._debounce_seconds = max(0.1, value)  # Minimum 100ms
    
    @property
    def emergency_duration(self) -> Optional[timedelta]:
        """Get how long emergency has been active"""
        if self._emergency_triggered_at and self.is_emergency:
            return datetime.now() - self._emergency_triggered_at
        return None