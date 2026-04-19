#!/usr/bin/env python3
  """
  Quick HX710B sensor diagnostic — run this on the Raspberry Pi to verify wiring.

  Usage:
      python3 scripts/test_sensor.py

  Expected output when sensor is working:
      - Raw values in the hundreds of thousands (e.g. 120000 to 4000000)
      - Values change when you press/squeeze the sensor

  If you see all -1 values:
      - Check SCK and DOUT wiring (try swapping them)
      - Check that the sensor has 3.3V power and GND connected

  If you see "GPIO not available":
      - Make sure you ran: pip install RPi.GPIO
      - Make sure you are running as a user with GPIO access (or root)
  """
  import sys
  import time
  from pathlib import Path

  # Make sure src/ is importable
  ROOT = Path(__file__).resolve().parent.parent
  sys.path.insert(0, str(ROOT))

  from src.hx710b import HX710B, HX710BConfig

  SCK_PIN  = int(sys.argv[1]) if len(sys.argv) > 1 else 17
  DOUT_PIN = int(sys.argv[2]) if len(sys.argv) > 2 else 27

  print(f"Testing HX710B — SCK=GPIO{SCK_PIN}  DOUT=GPIO{DOUT_PIN}")
  print("Press Ctrl+C to stop.\n")

  sensor = HX710B(HX710BConfig(sck_pin=SCK_PIN, dout_pin=DOUT_PIN))

  if sensor.is_mock:
      print(f"WARNING: Running in MOCK mode — GPIO not available.")
      print(f"  Reason: {sensor.init_error}")
      print("  Install RPi.GPIO with: pip install RPi.GPIO")
      sys.exit(1)

  print(f"GPIO backend: {sensor._backend}\n")

  prev = None
  for i in range(60):
      raw = sensor.read_raw()
      changed = "" if prev is None or raw == prev else "  ← CHANGED"
      print(f"[{i+1:02d}] raw={raw}   pressure_pa={raw}{changed}" if raw is not None else f"[{i+1:02d}] TIMEOUT — DOUT never went LOW within 250ms")
      prev = raw
      time.sleep(0.25)

  sensor.close()
  print("\nDone. If all values were -1, try swapping SCK and DOUT wires.")
  print("If all values were the same number and never changed when pressed,")
  print("check the power supply (3.3V on VCC, GND on GND).")
  