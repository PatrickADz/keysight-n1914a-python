"""Minimal example: connect, zero the sensor, and take a single reading."""

from n1914a import N1914A, load_config

if __name__ == "__main__":
    config = load_config()  # reads config.ini if present, else defaults

    with N1914A(config.resource_address, timeout_ms=config.timeout_ms) as pm:
        print("Connected to:", pm.idn())

        pm.set_unit(config.unit)

        #input("Remove all RF power from the sensor and press Enter to zero...")
        #pm.zero(channel=config.channel)

        power = pm.get_power(channel=config.channel)
        print(f"Measured power: {power} {config.unit}")
