# PWM Fan Control

A simple python script to control the fan from the *RockPro 64* (or from other arm boards).
This script is inspirated by the [armbian forum](https://forum.armbian.com/topic/11086-pwm-fan-on-nanopi-m4/page/2/#comment-110117).

## Installation

**Requirements:**

```shell
$ apt install python3-yaml
```

Copy the `pwm-fan-control.py` file:

```shell
$ cp src/usr/local/sbin/pwm-fan-control.py /usr/local/sbin/pwm-fan-control.py
$ chmod +x /usr/local/sbin/pwm-fan-control.py
```

Copy the `pwm-fan-control.yaml` configuration file:

```shell
$ cp src/etc/default/pwm-fan-control.yaml /etc/default
```

The *pwm_fan* kernel module must be blacklisted and disabled.

```shell
$ echo "blacklist pwm_fan" > /etc/modprobe.d/blacklist-pwm.conf
$ rmmod pwm_fan
```

## Configuration

You can set *PWM Fan Control* settings in the `/etc/default/pwm-fan-control.yaml`.

### OpenWeaterMap

| Key              | Value                                                                       |
|------------------|-----------------------------------------------------------------------------|
| `check_interval` | Check the speed (value in seconds) more or less frequently. Default is `5`. |
| `pwm_period`     | Value is in nanoseconds. Default is `400000`. (*40000ns = 25kHz*)           |
| `fan_speed`      | A list of cpu/disk temperatures (in °C) and the required speed (in %).      |
| `disk`           | A list of disks to for temperature monitoring.                              |

## Start systemd service

```shell
$ cp src/etc/systemd/system/pwm-fan-control.service /etc/systemd/system
$ systemctl enable --now pwm-fan-control.service
```
