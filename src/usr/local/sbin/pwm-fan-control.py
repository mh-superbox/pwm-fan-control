#!/usr/bin/env python3
import json
import logging
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from dataclasses import field
from dataclasses import is_dataclass
from pathlib import Path
from typing import List
from typing import Optional

import yaml

logging.basicConfig(level=logging.DEBUG, format="%(levelname)s - %(message)s")

logger = logging.getLogger("PWMFanControl")


@dataclass
class ConfigBase:
    def update(self, new):
        for key, value in new.items():
            if hasattr(self, key):
                item = getattr(self, key)

                if is_dataclass(item):
                    item.update(value)
                else:
                    setattr(self, key, value)


@dataclass
class Config(ConfigBase):
    check_interval: int = field(default=5)
    pwm_period: int = field(default=40000)
    fan_speed: List[dict] = field(default_factory=list)
    disk: list = field(default_factory=list)

    def __post_init__(self):
        config_path: Path = Path("/etc/default/pwm-fan-control.yaml")

        _config: dict = self.get_config(config_path)
        self.update(_config)

    @staticmethod
    def get_config(config_path: Path) -> dict:
        _config: dict = {}

        if config_path.exists():
            _config = yaml.load(config_path.read_text(), Loader=yaml.FullLoader)

        return _config


class PWMFanControl:
    def __init__(self):
        self._config = Config()
        self._check_pwm_fan_kernel_module()

        self._current_pwm: int = 0

        self.pwmchip_path: Path = Path("/sys/class/pwm/pwmchip1")
        self._export_path: Path = self.pwmchip_path.joinpath("export")
        self._duty_cycle_path: Path = self.pwmchip_path.joinpath("pwm0/duty_cycle")
        self._period_path: Path = self.pwmchip_path.joinpath("pwm0/period")
        self._polarity_path: Path = self.pwmchip_path.joinpath("pwm0/polarity")
        self._enable_path: Path = self.pwmchip_path.joinpath("pwm0/enable")

        self._pwmchip_export()
        self._pwmchip_period: int = self._config.pwm_period
        self._pwmchip_duty_cycle: int = self._duty_cycles[0]

        self._pwmchip_enable: bool = False
        self._pwmchip_polarity: str = "normal"
        self._pwmchip_enable: bool = True

        for path in (self._duty_cycle_path, self._period_path, self._enable_path):
            if not path.is_file():
                logger.error("File %s not found!", path)
                sys.exit(1)

    def _pwmchip_export(self):
        """Exports a PWM channel for use with sysfs."""
        try:
            with open(self._export_path, "w") as f:
                f.write("0\n")
        except OSError:
            logger.info("pwmchip already activated!")

    @property
    def _pwmchip_duty_cycle(self) -> int:
        """Get the active time of the PWM signal.

        Returns
        -------
        int
            Active time of the PWM signal in nanoseconds.
        """
        try:
            with open(self._duty_cycle_path) as f:
                return int(f.read())
        except ValueError as error:
            logger.error(error)
            sys.exit(1)

    @_pwmchip_duty_cycle.setter
    def _pwmchip_duty_cycle(self, value: int):
        """Change the active time of the PWM signal.

        Parameters
        ----------
        value : int
            Value is in nanoseconds and must be less than the period.
        """
        with open(self._duty_cycle_path, "w") as f:
            f.write(f"{value}\n")

    @property
    def _pwmchip_period(self) -> int:
        """Get the total period of the PWM signal.

        Returns
        -------
        int
            Total period of the PWM signal in nanoseconds.
        """
        try:
            with open(self._period_path) as f:
                return int(f.read())
        except ValueError as error:
            logger.error(error)
            sys.exit(1)

    @_pwmchip_period.setter
    def _pwmchip_period(self, value: int):
        """Change the total period of the PWM signal.

        Parameters
        ----------
        value : int
            Value is in nanoseconds and is the sum of the active and inactive time of the PWM.
        """
        with open(self._period_path, "w") as f:
            f.write(f"{value}\n")

    @property
    def _pwmchip_enable(self) -> bool:
        """Get the PWM signal status."""
        try:
            with open(self._enable_path) as f:
                _value = int(f.read())
                return True if _value == 1 else False
        except ValueError as error:
            logger.error(error)
            sys.exit(1)

    @_pwmchip_enable.setter
    def _pwmchip_enable(self, value: bool):
        """Enable/disable the PWM signal.

        Parameters
        ----------
        value : bool
            Enable or disable the PWM signal.
        """
        _value: int = 1 if value is True else 0

        with open(self._enable_path, "w") as f:
            f.write(f"{_value}\n")

    @property
    def _pwmchip_polarity(self) -> str:
        """Get the polarity of the PWM signal.

        Return
        ----------
        value : str
            Value is the string "normal" or "inversed".
        """
        with open(self._polarity_path) as f:
            return f.read().replace("\n", "")

    @_pwmchip_polarity.setter
    def _pwmchip_polarity(self, value: str):
        """Changes the polarity of the PWM signal.

        Writes to this property only work if the PWM chip supports changing
        the polarity. The polarity can only be changed if the PWM is not
        enabled.

        Parameters
        ----------
        value : str
            Value is the string "normal" or "inversed".
        """
        with open(self._polarity_path, "w") as f:
            f.write(f"{value}\n")

    @property
    def _cpu_temperature(self) -> int:
        """Get the CPU temperature.

        Returns
        -------
        int
            CPU temperature in °C.
        """
        cpu_temperatures: List[int] = []

        for chip in [
            "cpu_thermal-virtual-0",
            "gpu_thermal-virtual-0",
        ]:
            command: str = "sensors"

            try:
                output = subprocess.run([command, "-j", "-u", chip], capture_output=True)
                output_json: dict = json.loads(output.stdout.decode("utf-8"))

                for key, value in output_json[chip].items():
                    if t := re.match(r"^temp([0-9]+)$", key):
                        cpu_temperature: Optional[float] = value.get(f"temp{t.group(1)}_input")

                        if cpu_temperature:
                            cpu_temperatures.append(int(round(cpu_temperature, 0)))
            except KeyError:
                print(f"[Error] Can not read temperature from {chip}")
                sys.exit(1)
            except FileNotFoundError:
                logger.error("No such file or directory: '%s'", command)
                sys.exit(1)

        if cpu_temperatures:
            return cpu_temperatures[0] if len(cpu_temperatures) == 1 else max(*cpu_temperatures)

        return 0

    @property
    def _disk_temperature(self) -> int:
        """Get the max disk devices temperature.

        Returns
        -------
        int
            Disk devices temperature in °C.
        """
        disk_temperatures: List[int] = []

        for device in self._config.disk:
            command: str = "smartctl"

            try:
                output = subprocess.run([command, "-A", "-j", device], capture_output=True)
                output_json: dict = json.loads(output.stdout.decode("utf-8"))
                current_temperature: int = output_json["temperature"]["current"]
                disk_temperatures.append(current_temperature)
            except KeyError:
                logger.error("Can not read temperature from %s", device)
                sys.exit(1)
            except FileNotFoundError:
                logger.error("No such file or directory: '%s'", command)
                sys.exit(1)

        if disk_temperatures:
            return disk_temperatures[0] if len(disk_temperatures) == 1 else max(*disk_temperatures)

        return 0

    @property
    def _duty_cycles(self) -> List[int]:
        duty_cycles: List[int] = []

        for item in self._config.fan_speed:
            duty_cycles.append(int(self._config.pwm_period * item["speed"] / 100))

        return duty_cycles

    @property
    def _cpu_temperatures(self) -> List[int]:
        cpu_temperatures: List[int] = []

        for item in self._config.fan_speed:
            cpu_temperatures.append(item["cpu"])

        return cpu_temperatures

    @property
    def _disk_temperatures(self) -> List[int]:
        disk_temperatures: List[int] = []

        for item in self._config.fan_speed:
            disk_temperatures.append(item["disk"])

        return disk_temperatures

    @staticmethod
    def _check_pwm_fan_kernel_module():
        try:
            output_lsmod = subprocess.run(["lsmod"], check=True, capture_output=True)
            output = subprocess.run(["grep", "pwm_fan"], input=output_lsmod.stdout, capture_output=True)

            if output.stdout:
                logger.error("pwm_fan kernel module found. Module must be blacklisted!")
                sys.exit(1)
        except FileNotFoundError as error:
            logger.error(error)
            sys.exit(1)

    def monitor(self):
        while True:
            duty: int = 0

            for index in range(len(self._duty_cycles)):
                # Add some hysteresis when the fan speeds down to avoid continuous stop and go
                hysteresis: int = 2 if self._pwmchip_duty_cycle >= self._duty_cycles[index] else 0

                if (
                    self._cpu_temperature > self._cpu_temperatures[index] - hysteresis
                    or self._disk_temperature > self._disk_temperatures[index] - hysteresis
                ):
                    # If the fan is stopped, first full speed to ensure it really starts
                    duty = self._duty_cycles[0] if self._pwmchip_duty_cycle == 0 else self._duty_cycles[index]

                    logger.debug(
                        "CPU: %s °C, Disk: %s °C, Fan Speed: %s %%, %s kHz, Polarity: %s",
                        self._cpu_temperature,
                        self._disk_temperature,
                        duty * 100 / self._config.pwm_period,
                        round((self._pwmchip_period / 1e9) ** -1 / 1000),
                        self._pwmchip_polarity,
                    )

                    break

            self._pwmchip_duty_cycle: int = duty
            time.sleep(self._config.check_interval)


def main():
    pwm_fan_control = PWMFanControl()

    try:
        pwm_fan_control.monitor()
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
