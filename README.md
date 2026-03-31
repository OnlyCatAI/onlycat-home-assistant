# OnlyCat Integration for Home Assistant

HomeAssistant integration for [OnlyCat](https://www.onlycat.com/) flaps.

## Features

* 🏠 Know whether your pet is home or on the hunt using the Device Tracker
  * 🐾 In case your pet chooses another exit, you can override the presence using the `set_pet_location` service
* 🔎 Keep track of your device and build automations with it using binary sensors for:
   * 📶 Flap connection status
   * 🕒 Flap events (including timestamps, RFID codes, trigger source, and event classification)
   * 🐭 Contraband detection
   * 🔐 Lock state
   * 👤 Human detection
   * ⚠️ Device errors
   * 🎥 Last activity video and image
* 🚪 Manage the active door policy manually or using automations
* 📋 View and change door policy information via sensors and the `update_device_policy` service
* 🔄 Control your flap remotely using reboot and remote unlock buttons
* Check and manage your existing device policies

Common automation ideas enabled by this integration include:

* 🚨 Switch the door policy to "Locked" for a longer time period than usual when contraband is detected
* 💦 Deter intruders by triggering a sprinkler when an unknown RFID code is detected
* 🧹 Start your robot vacuum when your pet leaves the house
* 😻 Roll out the red carpet for your pet by activating welcome lights or triggering a feeder upon arrival

## Installation
[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=OnlyCatAI&repository=onlycat-home-assistant&category=integration)

1. Install [Home Assistant Community Store (HACS)](https://hacs.xyz/) if you haven't done so already.
2. Open HACS in Home Assistant
3. Click the three dots in the top right corner
4. Select "Custom repositories"
5. Add this repository URL: https://github.com/OnlyCatAI/onlycat-home-assistant
6. Set category to "Integration"
7. Click "Add"
8. Search for "OnlyCat" and install
9. Restart Home Assistant

## Configuration
[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=onlycat)

1. Go to `Settings` > `Devices & Services` > `Add Integration`
2. Search for "OnlyCat"
3. Enter your configuration:
   * **Device Token**: The token for your OnlyCat account. You can find it in the OnlyCat app under "Account".

## Limitations

Currently, the following features of the OnlyCat app are not yet included in the Home Assistant integration:

* Creating or modifying door policies
* Creating or modifying pet profiles (i.e., labels for RFID codes)
* Accessing the video or poster frame of flap events

## Contributing

Contributions are welcome! If you have ideas for new features & improvements or want to report a bug,
please open an issue or submit a pull request.

To get a local development environment up and running, follow these steps:

1. Install pip requirements via `pip install -r requirements.txt`
2. Run a HA instance:
   1. Directly by running `./scripts/develop`, or
   2. In Docker by running `docker run --volume ./config:/config --volume ./custom_components:/config/custom_components -p 8123:8123 "ghcr.io/home-assistant/home-assistant:stable"`
3. Add the integration from the HA "Devices & services" ui.

