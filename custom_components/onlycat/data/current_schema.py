"""Device Policy Schmema for OnlyCat integration."""

DEVICE_POLICY_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "Transit Policy Schema",
    "type": "object",
    "properties": {
        # Entries manually added to schema from OnlyCat website
        "deviceTransitPolicyId": {
            "type": "integer",
            "description": "Unique identifier for the transit policy, given by OnlyCat.",
        },
        "deviceId": {
            "type": "string",
            "description": "Unique identifier for the device, given by OnlyCat.",
        },
        "name": {"type": "string", "description": "Name of the transit policy."},
        # End of manually added entries
        "transitPolicy": {
            "type": "object",
            "properties": {
                # Entries manually added to schema from OnlyCat website
                "ux": {
                    "type": "object",
                    "description": "Interaction settings for this policy.",
                    "properties": {
                        "onActivate": {
                            "type": "object",
                            "description": "Configuration for sound played when this policy is activated.",
                            "properties": {
                                "sound": {
                                    "type": "string",
                                    "description": "Sound to play when this policy is activated.",
                                    "enum": [
                                        "affirm",
                                        "alarm",
                                        "angry-meow",
                                        "bell",
                                        "choir",
                                        "coin",
                                        "deny",
                                        "fanfare",
                                        "success",
                                    ],
                                }
                            },
                        }
                    },
                },
                # End of manually added entries
                "idleLock": {
                    "type": "boolean",
                    "description": "Indicates if the device should be locked when idle.",
                },
                "idleLockBattery": {
                    "type": "boolean",
                    "description": "Override for idleLock when the device is running on battery power.",
                },
                "rules": {
                    "type": "array",
                    "description": "List of rules to evaluate transit events.",
                    "items": {
                        "type": "object",
                        "properties": {
                            # Entries manually added to schema from OnlyCat website
                            "enabled": {
                                "type": "boolean",
                                "description": "Indicates whether this rule is enabled.",
                            },
                            "description": {
                                "type": "string",
                                "description": "Description of the rule.",
                            },
                            # End of manually added entries
                            "criteria": {
                                "type": "object",
                                "properties": {
                                    "eventTriggerSource": {
                                        "description": "Event trigger source(s) to match.",
                                        "anyOf": [
                                            {
                                                "type": "integer",
                                                "enum": [0, 1, 2, 3],
                                                "description": "0 (MANUAL), 1 (REMOTE), 2 (INDOOR_MOTION), 3 (OUTDOOR_MOTION).",
                                            },
                                            {
                                                "type": "array",
                                                "items": {
                                                    "type": "integer",
                                                    "enum": [0, 1, 2, 3],
                                                },
                                                "description": "Array of event trigger sources.",
                                            },
                                        ],
                                    },
                                    "eventClassification": {
                                        "description": "Event classification(s) to match.",
                                        "anyOf": [
                                            {
                                                "type": "integer",
                                                "enum": [0, 1, 2, 3, 4, 10],
                                                "description": "0 (UNKNOWN), 1 (CLEAR), 2 (SUSPICIOUS), 3 (CONTRABAND), 4 (HUMAN_ACTIVITY), 10 (REMOTE_UNLOCK).",
                                            },
                                            {
                                                "type": "array",
                                                "items": {
                                                    "type": "integer",
                                                    "enum": [0, 1, 2, 3, 4, 10],
                                                },
                                                "description": "Array of event classifications.",
                                            },
                                        ],
                                    },
                                    "rfidCode": {
                                        "description": "RFID code(s) to match.",
                                        "anyOf": [
                                            {"type": "string"},
                                            {
                                                "type": "array",
                                                "items": {"type": "string"},
                                            },
                                        ],
                                    },
                                    "rfidTimeout": {
                                        "type": "integer",
                                        "description": "Timeout in milliseconds to wait for an RFID code.",
                                    },
                                    "timeRange": {
                                        "description": "Time range(s) during which the rule is active (e.g., '08:00-18:00').",
                                        "anyOf": [
                                            {"type": "string"},
                                            {
                                                "type": "array",
                                                "items": {"type": "string"},
                                            },
                                        ],
                                    },
                                    "motionSensorState": {
                                        "description": "Instantaneous motion sensor state(s) to match, may be used for fast relock on opposing side motion.",
                                        "anyOf": [
                                            {
                                                "type": "integer",
                                                "enum": [0, 1, 2, 3],
                                                "description": "0 (UNKNOWN), 1 (NONE), 2 (INDOOR), 3 (OUTDOOR).",
                                            },
                                            {
                                                "type": "array",
                                                "items": {
                                                    "type": "integer",
                                                    "enum": [0, 1, 2, 3],
                                                },
                                                "description": "Array of motion sensor states.",
                                            },
                                        ],
                                    },
                                    "flapState": {
                                        "description": "Flap state(s) to match, may be used for fast relock once transit commences.",
                                        "anyOf": [
                                            {
                                                "type": "integer",
                                                "enum": [0, 1, 2, 3],
                                                "description": "0 (CLOSED), 1 (OPEN_OUTWARD), 2 (OPEN_INWARD), 3 (INVALID).",
                                            },
                                            {
                                                "type": "array",
                                                "items": {
                                                    "type": "integer",
                                                    "enum": [0, 1, 2, 3],
                                                },
                                                "description": "Array of flap states.",
                                            },
                                        ],
                                    },
                                },
                                "additionalProperties": False,
                            },
                            "action": {
                                "type": "object",
                                "properties": {
                                    "lock": {
                                        "type": "boolean",
                                        "description": "Determines whether to lock (true) or unlock (false) the device.",
                                    },
                                    "sound": {
                                        "type": "string",
                                        "description": "Sound to play when the rule matches.",
                                    },
                                    "lockoutDuration": {
                                        "type": "integer",
                                        "description": "If provided, the device locks for this many milliseconds, and no further rules are evaluated until the timeout expires.",
                                    },
                                    "final": {
                                        "type": "boolean",
                                        "description": "If true, no further rules are evaluated for this event after this action.",
                                    },
                                },
                                "additionalProperties": False,
                            },
                        },
                        "required": ["criteria", "action"],
                        "additionalProperties": False,
                    },
                },
            },
            "additionalProperties": False,
        },
    },
    "additionalProperties": False,
}
