# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

import base64
import gzip
import json
import math
import struct
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Callable


CDR_LE_HEADER = b"\x00\x01\x00\x00"


@dataclass(frozen=True)
class Ros2Message:
    topic: str
    schema_name: str
    schema_text: str
    log_time_ns: int
    data: bytes


TransformTuple = tuple[str, str, list[float], list[float]]


class CdrWriter:
    def __init__(self) -> None:
        self.buffer = bytearray(CDR_LE_HEADER)

    def bytes(self) -> bytes:
        return bytes(self.buffer)

    def align(self, size: int) -> None:
        payload_offset = len(self.buffer) - len(CDR_LE_HEADER)
        padding = (size - (payload_offset % size)) % size
        if padding:
            self.buffer.extend(b"\x00" * padding)

    def bool(self, value: Any) -> None:
        self.uint8(1 if value in (True, "True", "true", "1", 1) else 0)

    def uint8(self, value: Any) -> None:
        self.align(1)
        self.buffer.extend(struct.pack("<B", int(value) & 0xFF))

    def int32(self, value: Any) -> None:
        self.align(4)
        try:
            int_value = int(float(value))
        except (OverflowError, TypeError, ValueError):
            int_value = 0
        self.buffer.extend(struct.pack("<i", int_value))

    def uint32(self, value: Any) -> None:
        self.align(4)
        self.buffer.extend(struct.pack("<I", int(value) & 0xFFFFFFFF))

    def float32(self, value: Any) -> None:
        self.align(4)
        self.buffer.extend(struct.pack("<f", float(value)))

    def float64(self, value: Any) -> None:
        self.align(8)
        self.buffer.extend(struct.pack("<d", float(value)))

    def string(self, value: Any) -> None:
        encoded = str(value).encode("utf-8") + b"\x00"
        self.uint32(len(encoded))
        self.buffer.extend(encoded)

    def float32_sequence(self, values: list[float]) -> None:
        self.uint32(len(values))
        for value in values:
            self.float32(value)

    def float64_sequence(self, values: list[float]) -> None:
        self.uint32(len(values))
        for value in values:
            self.float64(value)

    def uint8_sequence(self, values: bytes) -> None:
        self.uint32(len(values))
        self.buffer.extend(values)

    def string_sequence(self, values: list[str]) -> None:
        self.uint32(len(values))
        for value in values:
            self.string(value)


SCHEMAS: dict[str, str] = {
    "std_msgs/msg/Float32": "float32 data\n",
    "std_msgs/msg/Int32": "int32 data\n",
    "geometry_msgs/msg/Point": "float64 x\nfloat64 y\nfloat64 z\n",
    "sensor_msgs/msg/JointState": """std_msgs/msg/Header header
string[] name
float64[] position
float64[] velocity
float64[] effort
================================================================================
MSG: std_msgs/msg/Header
builtin_interfaces/msg/Time stamp
string frame_id
================================================================================
MSG: builtin_interfaces/msg/Time
int32 sec
uint32 nanosec
""",
    "sensor_msgs/msg/Imu": """std_msgs/msg/Header header
geometry_msgs/msg/Quaternion orientation
float64[9] orientation_covariance
geometry_msgs/msg/Vector3 angular_velocity
float64[9] angular_velocity_covariance
geometry_msgs/msg/Vector3 linear_acceleration
float64[9] linear_acceleration_covariance
================================================================================
MSG: std_msgs/msg/Header
builtin_interfaces/msg/Time stamp
string frame_id
================================================================================
MSG: builtin_interfaces/msg/Time
int32 sec
uint32 nanosec
================================================================================
MSG: geometry_msgs/msg/Quaternion
float64 x
float64 y
float64 z
float64 w
================================================================================
MSG: geometry_msgs/msg/Vector3
float64 x
float64 y
float64 z
""",
    "nav_msgs/msg/Odometry": """std_msgs/msg/Header header
string child_frame_id
geometry_msgs/msg/PoseWithCovariance pose
geometry_msgs/msg/TwistWithCovariance twist
================================================================================
MSG: std_msgs/msg/Header
builtin_interfaces/msg/Time stamp
string frame_id
================================================================================
MSG: builtin_interfaces/msg/Time
int32 sec
uint32 nanosec
================================================================================
MSG: geometry_msgs/msg/Point
float64 x
float64 y
float64 z
================================================================================
MSG: geometry_msgs/msg/Quaternion
float64 x
float64 y
float64 z
float64 w
================================================================================
MSG: geometry_msgs/msg/Pose
geometry_msgs/msg/Point position
geometry_msgs/msg/Quaternion orientation
================================================================================
MSG: geometry_msgs/msg/PoseWithCovariance
geometry_msgs/msg/Pose pose
float64[36] covariance
================================================================================
MSG: geometry_msgs/msg/Vector3
float64 x
float64 y
float64 z
================================================================================
MSG: geometry_msgs/msg/Twist
geometry_msgs/msg/Vector3 linear
geometry_msgs/msg/Vector3 angular
================================================================================
MSG: geometry_msgs/msg/TwistWithCovariance
geometry_msgs/msg/Twist twist
float64[36] covariance
""",
    "sensor_msgs/msg/LaserScan": """std_msgs/msg/Header header
float32 angle_min
float32 angle_max
float32 angle_increment
float32 time_increment
float32 scan_time
float32 range_min
float32 range_max
float32[] ranges
float32[] intensities
================================================================================
MSG: std_msgs/msg/Header
builtin_interfaces/msg/Time stamp
string frame_id
================================================================================
MSG: builtin_interfaces/msg/Time
int32 sec
uint32 nanosec
""",
    "sensor_msgs/msg/Image": """std_msgs/msg/Header header
uint32 height
uint32 width
string encoding
uint8 is_bigendian
uint32 step
uint8[] data
================================================================================
MSG: std_msgs/msg/Header
builtin_interfaces/msg/Time stamp
string frame_id
================================================================================
MSG: builtin_interfaces/msg/Time
int32 sec
uint32 nanosec
""",
    "tf2_msgs/msg/TFMessage": """geometry_msgs/msg/TransformStamped[] transforms
================================================================================
MSG: geometry_msgs/msg/TransformStamped
std_msgs/msg/Header header
string child_frame_id
geometry_msgs/msg/Transform transform
================================================================================
MSG: std_msgs/msg/Header
builtin_interfaces/msg/Time stamp
string frame_id
================================================================================
MSG: builtin_interfaces/msg/Time
int32 sec
uint32 nanosec
================================================================================
MSG: geometry_msgs/msg/Vector3
float64 x
float64 y
float64 z
================================================================================
MSG: geometry_msgs/msg/Quaternion
float64 x
float64 y
float64 z
float64 w
================================================================================
MSG: geometry_msgs/msg/Transform
geometry_msgs/msg/Vector3 translation
geometry_msgs/msg/Quaternion rotation
""",
}

POSE_COVARIANCE = [0.0025, 0.0, 0.0, 0.0, 0.0, 0.0,
                   0.0, 0.0025, 0.0, 0.0, 0.0, 0.0,
                   0.0, 0.0, 0.0025, 0.0, 0.0, 0.0,
                   0.0, 0.0, 0.0, 0.0025, 0.0, 0.0,
                   0.0, 0.0, 0.0, 0.0, 0.0025, 0.0,
                   0.0, 0.0, 0.0, 0.0, 0.0, 0.0025]
IMU_COVARIANCE = [0.0025, 0.0, 0.0, 0.0, 0.0025, 0.0, 0.0, 0.0, 0.0025]


def convert_accident_mcap_to_ros2_mcap(path: Path) -> bytes:
    from mcap.reader import NonSeekingReader
    from mcap.well_known import MessageEncoding, Profile, SchemaEncoding
    from mcap.writer import Writer

    output = BytesIO()
    writer = Writer(output)
    writer.start(profile=Profile.ROS2)

    schema_ids: dict[str, int] = {}
    channel_ids: dict[tuple[str, str], int] = {}

    def channel_id(topic: str, schema_name: str) -> int:
        key = (topic, schema_name)
        if key in channel_ids:
            return channel_ids[key]
        if schema_name not in schema_ids:
            schema_ids[schema_name] = writer.register_schema(
                name=schema_name,
                encoding=SchemaEncoding.ROS2,
                data=SCHEMAS[schema_name].encode("utf-8"),
            )
        channel_ids[key] = writer.register_channel(
            topic=topic,
            message_encoding=MessageEncoding.CDR,
            schema_id=schema_ids[schema_name],
        )
        return channel_ids[key]

    with path.open("rb") as mcap_file:
        reader = NonSeekingReader(mcap_file)
        for _schema, channel, message in reader.iter_messages(topics=("/rct/accident/bridge",), log_time_order=False):
            if channel.topic != "/rct/accident/bridge":
                continue
            try:
                bridge_event = json.loads(message.data.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            payload = bridge_event.get("payload") if isinstance(bridge_event, dict) else None
            if not isinstance(payload, dict):
                continue
            log_time_ns = int(bridge_event.get("wall_time_ns", message.log_time))
            for ros2_message in bridge_payload_to_ros2_messages(payload, log_time_ns):
                writer.add_message(
                    channel_id=channel_id(ros2_message.topic, ros2_message.schema_name),
                    log_time=ros2_message.log_time_ns,
                    publish_time=ros2_message.log_time_ns,
                    data=ros2_message.data,
                )

    writer.finish()
    return output.getvalue()


def bridge_payload_to_ros2_messages(payload: dict[str, Any], log_time_ns: int) -> list[Ros2Message]:
    messages: list[Ros2Message] = []
    shared_tf_transforms: list[TransformTuple] = []
    for vehicle_id in (1, 2):
        prefix = f"V{vehicle_id} "
        base_topic = f"/autodrive/roboracer_{vehicle_id}"
        has_vehicle_data = any(str(key).startswith(prefix) for key in payload)
        if not has_vehicle_data:
            continue

        append_if_present(messages, payload, f"{prefix}Throttle", f"{base_topic}/throttle", "std_msgs/msg/Float32", log_time_ns, serialize_float32)
        append_if_present(messages, payload, f"{prefix}Steering", f"{base_topic}/steering", "std_msgs/msg/Float32", log_time_ns, serialize_float32)
        append_if_present(messages, payload, f"{prefix}Lap Count", f"{base_topic}/lap_count", "std_msgs/msg/Int32", log_time_ns, serialize_int32)
        append_if_present(messages, payload, f"{prefix}Lap Time", f"{base_topic}/lap_time", "std_msgs/msg/Float32", log_time_ns, serialize_float32)
        append_if_present(messages, payload, f"{prefix}Last Lap Time", f"{base_topic}/last_lap_time", "std_msgs/msg/Float32", log_time_ns, serialize_float32)
        append_if_present(messages, payload, f"{prefix}Best Lap Time", f"{base_topic}/best_lap_time", "std_msgs/msg/Float32", log_time_ns, serialize_float32)
        append_if_present(messages, payload, f"{prefix}Collisions", f"{base_topic}/collision_count", "std_msgs/msg/Int32", log_time_ns, serialize_int32)

        position = parse_float_list(payload.get(f"{prefix}Position"), 3)
        orientation = parse_float_list(payload.get(f"{prefix}Orientation Quaternion"), 4)
        angular_velocity = parse_float_list(payload.get(f"{prefix}Angular Velocity"), 3)
        linear_acceleration = parse_float_list(payload.get(f"{prefix}Linear Acceleration"), 3)
        linear_velocity = parse_float_list(payload.get(f"{prefix}Linear Velocity"), 3)
        encoder_angles = parse_float_list(payload.get(f"{prefix}Encoder Angles"), 2)

        if position is not None:
            messages.append(ros2_message(f"{base_topic}/ips", "geometry_msgs/msg/Point", log_time_ns, serialize_point(position)))
        if encoder_angles is not None:
            messages.append(ros2_message(f"{base_topic}/left_encoder", "sensor_msgs/msg/JointState", log_time_ns, serialize_joint_state(log_time_ns, vehicle_child_frame(vehicle_id, "left_encoder"), "left_encoder", encoder_angles[0])))
            messages.append(ros2_message(f"{base_topic}/right_encoder", "sensor_msgs/msg/JointState", log_time_ns, serialize_joint_state(log_time_ns, vehicle_child_frame(vehicle_id, "right_encoder"), "right_encoder", encoder_angles[1])))
        if orientation is not None and angular_velocity is not None and linear_acceleration is not None:
            messages.append(ros2_message(f"{base_topic}/imu", "sensor_msgs/msg/Imu", log_time_ns, serialize_imu(log_time_ns, vehicle_child_frame(vehicle_id, "imu"), orientation, angular_velocity, linear_acceleration)))
        if position is not None and orientation is not None and linear_velocity is not None and angular_velocity is not None:
            messages.append(ros2_message(f"{base_topic}/odom", "nav_msgs/msg/Odometry", log_time_ns, serialize_odometry(log_time_ns, "world", f"roboracer_{vehicle_id}", position, orientation, linear_velocity, angular_velocity)))

        lidar_scan_rate = parse_float(payload.get(f"{prefix}LIDAR Scan Rate"))
        lidar_ranges = parse_gzip_float_array(payload.get(f"{prefix}LIDAR Range Array"))
        lidar_intensities = parse_gzip_float_array(payload.get(f"{prefix}LIDAR Intensity Array")) or []
        if lidar_scan_rate is not None and lidar_ranges is not None:
            messages.append(ros2_message(f"{base_topic}/lidar", "sensor_msgs/msg/LaserScan", log_time_ns, serialize_laserscan(log_time_ns, vehicle_child_frame(vehicle_id, "lidar"), lidar_scan_rate, lidar_ranges, lidar_intensities)))

        image = decode_front_camera(payload.get(f"{prefix}Front Camera Image"))
        if image is not None:
            width, height, data = image
            messages.append(ros2_message(f"{base_topic}/front_camera", "sensor_msgs/msg/Image", log_time_ns, serialize_image(log_time_ns, vehicle_child_frame(vehicle_id, "front_camera"), width, height, data)))

        if position is not None and orientation is not None:
            shared_tf_transforms.extend(
                vehicle_tf_transforms(
                    vehicle_id,
                    position,
                    orientation,
                    encoder_angles,
                    parse_float(payload.get(f"{prefix}Steering")),
                )
            )
    if shared_tf_transforms:
        messages.append(ros2_message("/tf", "tf2_msgs/msg/TFMessage", log_time_ns, serialize_tf_transforms(log_time_ns, shared_tf_transforms)))
    return messages


def append_if_present(
    messages: list[Ros2Message],
    payload: dict[str, Any],
    key: str,
    topic: str,
    schema_name: str,
    log_time_ns: int,
    serializer: Callable[[Any], bytes],
) -> None:
    if key in payload:
        messages.append(ros2_message(topic, schema_name, log_time_ns, serializer(payload[key])))


def ros2_message(topic: str, schema_name: str, log_time_ns: int, data: bytes) -> Ros2Message:
    return Ros2Message(topic=topic, schema_name=schema_name, schema_text=SCHEMAS[schema_name], log_time_ns=log_time_ns, data=data)


def write_header(writer: CdrWriter, log_time_ns: int, frame_id: str) -> None:
    seconds, nanoseconds = divmod(int(log_time_ns), 1_000_000_000)
    writer.int32(seconds)
    writer.uint32(nanoseconds)
    writer.string(frame_id)


def serialize_float32(value: Any) -> bytes:
    writer = CdrWriter()
    writer.float32(parse_float(value, default=0.0))
    return writer.bytes()


def serialize_int32(value: Any) -> bytes:
    writer = CdrWriter()
    writer.int32(parse_float(value, default=0.0))
    return writer.bytes()


def serialize_point(position: list[float]) -> bytes:
    writer = CdrWriter()
    for value in position:
        writer.float64(value)
    return writer.bytes()


def serialize_joint_state(log_time_ns: int, frame_id: str, joint_name: str, joint_angle: float) -> bytes:
    writer = CdrWriter()
    write_header(writer, log_time_ns, frame_id)
    writer.string_sequence([joint_name])
    writer.float64_sequence([joint_angle])
    writer.float64_sequence([])
    writer.float64_sequence([])
    return writer.bytes()


def serialize_imu(log_time_ns: int, frame_id: str, orientation: list[float], angular_velocity: list[float], linear_acceleration: list[float]) -> bytes:
    writer = CdrWriter()
    write_header(writer, log_time_ns, frame_id)
    write_float64_values(writer, orientation)
    write_float64_values(writer, IMU_COVARIANCE)
    write_float64_values(writer, angular_velocity)
    write_float64_values(writer, IMU_COVARIANCE)
    write_float64_values(writer, linear_acceleration)
    write_float64_values(writer, IMU_COVARIANCE)
    return writer.bytes()


def serialize_odometry(
    log_time_ns: int,
    frame_id: str,
    child_frame_id: str,
    position: list[float],
    orientation: list[float],
    linear_velocity: list[float],
    angular_velocity: list[float],
) -> bytes:
    writer = CdrWriter()
    write_header(writer, log_time_ns, frame_id)
    writer.string(child_frame_id)
    write_float64_values(writer, position)
    write_float64_values(writer, orientation)
    write_float64_values(writer, POSE_COVARIANCE)
    write_float64_values(writer, linear_velocity)
    write_float64_values(writer, angular_velocity)
    write_float64_values(writer, POSE_COVARIANCE)
    return writer.bytes()


def serialize_laserscan(log_time_ns: int, frame_id: str, scan_rate: float, ranges: list[float], intensities: list[float]) -> bytes:
    writer = CdrWriter()
    write_header(writer, log_time_ns, frame_id)
    writer.float32(-2.35619)
    writer.float32(2.35619)
    writer.float32(0.004363323)
    writer.float32((1.0 / scan_rate) / 1080.0 if scan_rate else 0.0)
    writer.float32(1.0 / scan_rate if scan_rate else 0.0)
    writer.float32(0.06)
    writer.float32(10.0)
    writer.float32_sequence(ranges)
    writer.float32_sequence(intensities)
    return writer.bytes()


def serialize_image(log_time_ns: int, frame_id: str, width: int, height: int, data: bytes) -> bytes:
    writer = CdrWriter()
    write_header(writer, log_time_ns, frame_id)
    writer.uint32(height)
    writer.uint32(width)
    writer.string("rgb8")
    writer.uint8(0)
    writer.uint32(width * 3)
    writer.uint8_sequence(data)
    return writer.bytes()


def serialize_tf_message(
    log_time_ns: int,
    vehicle_id: int,
    position: list[float],
    orientation: list[float],
    encoder_angles: list[float] | None,
    steering: float | None,
) -> bytes:
    return serialize_tf_transforms(
        log_time_ns,
        vehicle_tf_transforms(vehicle_id, position, orientation, encoder_angles, steering),
    )


def vehicle_tf_transforms(
    vehicle_id: int,
    position: list[float],
    orientation: list[float],
    encoder_angles: list[float] | None,
    steering: float | None,
) -> list[TransformTuple]:
    frame = f"roboracer_{vehicle_id}"
    return [
        ("world", frame, position, orientation),
        (frame, vehicle_child_frame(vehicle_id, "left_encoder"), [0.0, 0.12, 0.0], quaternion_from_euler(0.0, 120.0 * ((encoder_angles or [0.0, 0.0])[0] % 6.283), 0.0)),
        (frame, vehicle_child_frame(vehicle_id, "right_encoder"), [0.0, -0.12, 0.0], quaternion_from_euler(0.0, 120.0 * ((encoder_angles or [0.0, 0.0])[1] % 6.283), 0.0)),
        (frame, vehicle_child_frame(vehicle_id, "ips"), [0.08, 0.0, 0.055], [0.0, 0.0, 0.0, 1.0]),
        (frame, vehicle_child_frame(vehicle_id, "imu"), [0.08, 0.0, 0.055], [0.0, 0.0, 0.0, 1.0]),
        (frame, vehicle_child_frame(vehicle_id, "lidar"), [0.2733, 0.0, 0.096], [0.0, 0.0, 0.0, 1.0]),
        (frame, vehicle_child_frame(vehicle_id, "front_camera"), [-0.015, 0.0, 0.15], [0.0, 0.0871557, 0.0, 0.9961947]),
        (frame, vehicle_child_frame(vehicle_id, "front_left_wheel"), [0.33, 0.118, 0.0], front_wheel_quaternion(steering or 0.0, left=True)),
        (frame, vehicle_child_frame(vehicle_id, "front_right_wheel"), [0.33, -0.118, 0.0], front_wheel_quaternion(steering or 0.0, left=False)),
        (frame, vehicle_child_frame(vehicle_id, "rear_left_wheel"), [0.0, 0.118, 0.0], quaternion_from_euler(0.0, (encoder_angles or [0.0, 0.0])[0] % 6.283, 0.0)),
        (frame, vehicle_child_frame(vehicle_id, "rear_right_wheel"), [0.0, -0.118, 0.0], quaternion_from_euler(0.0, (encoder_angles or [0.0, 0.0])[1] % 6.283, 0.0)),
    ]


def vehicle_child_frame(vehicle_id: int, child_frame: str) -> str:
    return child_frame


def serialize_tf_transforms(log_time_ns: int, transforms: list[TransformTuple]) -> bytes:
    writer = CdrWriter()
    writer.uint32(len(transforms))
    for parent, child, translation, rotation in transforms:
        write_header(writer, log_time_ns, parent)
        writer.string(child)
        write_float64_values(writer, translation)
        write_float64_values(writer, rotation)
    return writer.bytes()


def write_float64_values(writer: CdrWriter, values: list[float]) -> None:
    for value in values:
        writer.float64(value)


def parse_float(value: Any, default: float | None = None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_float_list(value: Any, expected_length: int | None = None) -> list[float] | None:
    if value is None:
        return None
    try:
        values = [float(item) for item in str(value).replace(",", " ").split()]
    except ValueError:
        return None
    if expected_length is not None and len(values) < expected_length:
        return None
    return values[:expected_length] if expected_length is not None else values


def parse_gzip_float_array(value: Any) -> list[float] | None:
    if not value:
        return None
    try:
        decoded = gzip.decompress(base64.b64decode(str(value))).decode("utf-8")
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    return parse_float_list(decoded)


def decode_front_camera(value: Any) -> tuple[int, int, bytes] | None:
    if not value:
        return None
    try:
        from PIL import Image

        image = Image.open(BytesIO(base64.b64decode(str(value)))).convert("RGB")
    except Exception:
        return None
    return image.width, image.height, image.tobytes()


def quaternion_from_euler(roll: float, pitch: float, yaw: float) -> list[float]:
    cy = math.cos(yaw * 0.5)
    sy = math.sin(yaw * 0.5)
    cp = math.cos(pitch * 0.5)
    sp = math.sin(pitch * 0.5)
    cr = math.cos(roll * 0.5)
    sr = math.sin(roll * 0.5)
    return [
        sr * cp * cy - cr * sp * sy,
        cr * sp * cy + sr * cp * sy,
        cr * cp * sy - sr * sp * cy,
        cr * cp * cy + sr * sp * sy,
    ]


def front_wheel_quaternion(steering: float, *, left: bool) -> list[float]:
    denominator = 2 * 0.141537 + ((-2 if left else 2) * 0.0765 * math.tan(steering))
    yaw = math.atan((2 * 0.141537 * math.tan(steering)) / denominator) if denominator else 0.0
    return quaternion_from_euler(0.0, 0.0, yaw)
