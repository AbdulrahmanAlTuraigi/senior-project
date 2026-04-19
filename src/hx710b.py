"""
HX710B reader utilities for Raspberry Pi.

Implements a simple bit-banged 24-bit ADC read over GPIO pins.
"""

from __future__ import annotations

import math
import logging
import random
import time
from dataclasses import dataclass
from typing import Optional

try:
    import RPi.GPIO as GPIO  # type: ignore

    _GPIO_AVAILABLE = True
except Exception:
    GPIO = None  # type: ignore
    _GPIO_AVAILABLE = False

try:
    import gpiod  # type: ignore
    from gpiod.line import Direction, Value  # type: ignore

    _GPIOD_AVAILABLE = True
except Exception:
    gpiod = None  # type: ignore
    Direction = None  # type: ignore
    Value = None  # type: ignore
    _GPIOD_AVAILABLE = False


logger = logging.getLogger(__name__)


@dataclass
class HX710BConfig:
    """Runtime config for one HX710B input channel."""

    sck_pin: int
    dout_pin: int
    gain_pulses: int = 1
    ready_timeout_s: float = 0.25
    offset: float = 0.0
    scale: float = 1.0


class HX710B:
    """Read raw and calibrated values from HX710B via GPIO."""

    def __init__(self, config: HX710BConfig) -> None:
        self.config = config
        self._mock_mode = True
        self._init_error: str | None = None
        self._backend = "mock"
        self._line_req = None
        self._t0 = time.time()

        if _GPIO_AVAILABLE:
            try:
                GPIO.setwarnings(False)
                GPIO.setmode(GPIO.BCM)
                GPIO.setup(self.config.sck_pin, GPIO.OUT)
                GPIO.setup(self.config.dout_pin, GPIO.IN)
                GPIO.output(self.config.sck_pin, GPIO.LOW)
                self._mock_mode = False
                self._backend = "rpi_gpio"
                return
            except Exception as exc:
                self._init_error = f"RPi.GPIO init failed: {exc}"

        if _GPIOD_AVAILABLE:
            try:
                self._line_req = gpiod.request_lines(
                    "/dev/gpiochip0",
                    consumer="hx710b",
                    config={
                        self.config.sck_pin: gpiod.LineSettings(
                            direction=Direction.OUTPUT,
                            output_value=Value.INACTIVE,
                        ),
                        self.config.dout_pin: gpiod.LineSettings(
                            direction=Direction.INPUT,
                        ),
                    },
                )
                self._mock_mode = False
                self._backend = "gpiod"
                return
            except Exception as exc:
                prev = self._init_error
                self._init_error = (
                    f"{prev}; gpiod init failed: {exc}" if prev else f"gpiod init failed: {exc}"
                )

        logger.warning(
            "Falling back to mock mode for HX710B on SCK=%s DOUT=%s (%s)",
            self.config.sck_pin,
            self.config.dout_pin,
            self._init_error or "No GPIO backend available",
        )

    @property
    def is_mock(self) -> bool:
        """True when GPIO is unavailable and synthetic values are generated."""
        return self._mock_mode

    @property
    def init_error(self) -> str | None:
        """GPIO init error text when fallback to mock mode was triggered."""
        return self._init_error

    def close(self) -> None:
        """Release GPIO resources on shutdown."""
        if self._backend == "rpi_gpio":
            GPIO.cleanup([self.config.sck_pin, self.config.dout_pin])
        if self._backend == "gpiod" and self._line_req is not None:
            self._line_req.release()
            self._line_req = None

    def _wait_ready(self) -> bool:
        deadline = time.time() + self.config.ready_timeout_s
        while time.time() < deadline:
            if self._backend == "rpi_gpio":
                is_ready = GPIO.input(self.config.dout_pin) == 0
            elif self._backend == "gpiod":
                is_ready = self._line_req.get_value(self.config.dout_pin) == Value.INACTIVE
            else:
                is_ready = False
            if is_ready:
                return True
            time.sleep(0.001)
        return False

    def read_raw(self) -> Optional[int]:
        """Return signed 24-bit raw ADC value, or None on timeout."""
        if self._mock_mode:
            t = time.time() - self._t0
            wave = 120000 + 15000 * math.sin(2.0 * math.pi * 0.25 * t)
            noise = random.uniform(-1200, 1200)
            return int(wave + noise)

        if not self._wait_ready():
            return None

        value = 0
        for _ in range(24):
            if self._backend == "rpi_gpio":
                GPIO.output(self.config.sck_pin, GPIO.HIGH)
                bit = GPIO.input(self.config.dout_pin)
                GPIO.output(self.config.sck_pin, GPIO.LOW)
            else:
                self._line_req.set_value(self.config.sck_pin, Value.ACTIVE)
                bit = 1 if self._line_req.get_value(self.config.dout_pin) == Value.ACTIVE else 0
                self._line_req.set_value(self.config.sck_pin, Value.INACTIVE)
            value = (value << 1) | bit

        # Extra clock pulses select next conversion mode/gain.
        for _ in range(max(1, self.config.gain_pulses)):
            if self._backend == "rpi_gpio":
                GPIO.output(self.config.sck_pin, GPIO.HIGH)
                GPIO.output(self.config.sck_pin, GPIO.LOW)
            else:
                self._line_req.set_value(self.config.sck_pin, Value.ACTIVE)
                self._line_req.set_value(self.config.sck_pin, Value.INACTIVE)

        if value & 0x800000:
            value -= 1 << 24
        return value

    def read_value(self) -> Optional[float]:
        """Return calibrated floating-point value (e.g., pressure units)."""
        raw = self.read_raw()
        if raw is None:
            return None
        return (raw - self.config.offset) * self.config.scale
