"""The whole navigation stack for a delivery, in ONE process.

Started by robot/start_stack.sh nav --route-dir DIR, and by sim/run_e2e.sh:
    ros2 launch delivery_stack.launch.py map:=DIR/map.yaml keepout_mask:=DIR/keepout_mask.yaml \
        speed_mask:=DIR/speed_mask.yaml localization_params:=FILE

Why not the stock turtlebot4_navigation launch files (measured on this robot, 2026-11-05):
  - They start about 15 separate processes on a Raspberry Pi 4. The load average reached 14, a server then missed its
    4 s lifecycle heartbeat, and Nav2 shut itself down.
  - Every process is a ROS participant, and new participants stall the Create 3 base (ROADMAP TB-25). One process is
    one participant.
  - They start servers a delivery does not use: docking_server (the Create 3 docks itself), waypoint_follower and
    smoother_server (delivery_through_poses_bt.xml uses neither).
  - The heartbeat limit cannot be raised from the stock launch file.

Safety: the stack only drives when a goal is sent to it (delivery_mission.py). It keeps Nav2's collision monitor, and a
real emergency stop stays on the controller (button B). The nodes are the ones Nav2's own composition mode loads.
"""
import os

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, SetEnvironmentVariable
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import LoadComposableNodes, Node, SetParameter
from launch_ros.descriptions import ComposableNode, ParameterFile
from nav2_common.launch import RewrittenYaml

CONTAINER = 'delivery_container'

# Topic names (must match config/nav2_delivery.yaml).
KEEPOUT_MASK_TOPIC = '/keepout_filter_mask'
KEEPOUT_INFO_TOPIC = '/keepout_filter_info'
SPEED_MASK_TOPIC = '/speed_filter_mask'
SPEED_INFO_TOPIC = '/speed_filter_info'

# Filter info (nav2 CostmapFilterInfo): type 0 = keepout, type 1 = speed limit in percent.
KEEPOUT_TYPE, KEEPOUT_BASE, KEEPOUT_MULTIPLIER = 0, 0.0, 1.0
SPEED_TYPE, SPEED_BASE, SPEED_MULTIPLIER = 1, 100.0, -1.0   # limit % = 100 - mask value

# s, 0 = the lifecycle manager does not watch its nodes through bonds. On the robot (2026-11-06, CPU load 15) it called
# bt_navigator dead 0.2 s after it came up, although bond_timeout was 20 s, and reset all of Nav2 while the mission was
# sending its goal. Every node runs in this one process, so they die together, and delivery_mission.py polls is_active
# during every leg and raises the alarm by itself.
BOND_TIMEOUT = 0.0

# In bring-up order: the map frame must exist before the costmaps activate, and the masks before the filters read them.
LIFECYCLE_NODES = [
    'map_server',
    'amcl',
    'keepout_filter_mask_server',
    'keepout_costmap_filter_info_server',
    'speed_filter_mask_server',
    'speed_costmap_filter_info_server',
    'controller_server',
    'planner_server',
    'behavior_server',
    'velocity_smoother',
    'collision_monitor',
    'bt_navigator',
]


def generate_launch_description():
    delivery_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    nav2_params = LaunchConfiguration('nav2_params')
    localization_params = LaunchConfiguration('localization_params')
    map_yaml = LaunchConfiguration('map')
    keepout_mask = LaunchConfiguration('keepout_mask')
    speed_mask = LaunchConfiguration('speed_mask')
    use_sim_time = LaunchConfiguration('use_sim_time')

    # The same remappings as nav2_bringup/navigation_launch.py, composition mode.
    tf = [('/tf', 'tf'), ('/tf_static', 'tf_static')]
    to_smoother = tf + [('cmd_vel', 'cmd_vel_nav')]

    # As in nav2_bringup: the files go both on the container (the inner costmap nodes read them there) and on each node.
    def params_file(path):
        return ParameterFile(RewrittenYaml(source_file=path, root_key='', param_rewrites={}, convert_types=True),
                             allow_substs=True)

    files = [params_file(nav2_params), params_file(localization_params)]

    def component(package, plugin, name, remappings=None, parameters=None):
        return ComposableNode(package=package, plugin=plugin, name=name, remappings=remappings or tf,
                              parameters=files + (parameters or []))

    return LaunchDescription([
        DeclareLaunchArgument('map', description='Full path of the map YAML'),
        DeclareLaunchArgument('keepout_mask', description='Full path of the keepout mask YAML'),
        DeclareLaunchArgument('speed_mask', description='Full path of the speed mask YAML'),
        DeclareLaunchArgument('localization_params',
                              description='AMCL settings with the initial pose (tools/make_localization_params.py)'),
        DeclareLaunchArgument('nav2_params', default_value=os.path.join(delivery_dir, 'config', 'nav2_delivery.yaml'),
                              description='Nav2 settings'),
        DeclareLaunchArgument('use_sim_time', default_value='false', choices=['true', 'false'],
                              description='Use sim time (leave false on the robot)'),
        SetEnvironmentVariable('RCUTILS_LOGGING_BUFFERED_STREAM', '1'),
        SetParameter('use_sim_time', use_sim_time),

        Node(package='rclcpp_components', executable='component_container_isolated', name=CONTAINER, output='screen',
             emulate_tty=True, parameters=files, remappings=tf),

        LoadComposableNodes(target_container='/' + CONTAINER, composable_node_descriptions=[
            component('nav2_map_server', 'nav2_map_server::MapServer', 'map_server',
                      parameters=[{'yaml_filename': map_yaml}]),
            component('nav2_amcl', 'nav2_amcl::AmclNode', 'amcl'),

            component('nav2_map_server', 'nav2_map_server::MapServer', 'keepout_filter_mask_server',
                      parameters=[{'yaml_filename': keepout_mask, 'topic_name': KEEPOUT_MASK_TOPIC,
                                   'frame_id': 'map'}]),
            component('nav2_map_server', 'nav2_map_server::CostmapFilterInfoServer',
                      'keepout_costmap_filter_info_server',
                      parameters=[{'type': KEEPOUT_TYPE, 'filter_info_topic': KEEPOUT_INFO_TOPIC,
                                   'mask_topic': KEEPOUT_MASK_TOPIC, 'base': KEEPOUT_BASE,
                                   'multiplier': KEEPOUT_MULTIPLIER}]),
            component('nav2_map_server', 'nav2_map_server::MapServer', 'speed_filter_mask_server',
                      parameters=[{'yaml_filename': speed_mask, 'topic_name': SPEED_MASK_TOPIC, 'frame_id': 'map'}]),
            component('nav2_map_server', 'nav2_map_server::CostmapFilterInfoServer', 'speed_costmap_filter_info_server',
                      parameters=[{'type': SPEED_TYPE, 'filter_info_topic': SPEED_INFO_TOPIC,
                                   'mask_topic': SPEED_MASK_TOPIC, 'base': SPEED_BASE,
                                   'multiplier': SPEED_MULTIPLIER}]),

            component('nav2_controller', 'nav2_controller::ControllerServer', 'controller_server', to_smoother),
            component('nav2_planner', 'nav2_planner::PlannerServer', 'planner_server'),
            component('nav2_behaviors', 'behavior_server::BehaviorServer', 'behavior_server', to_smoother),
            component('nav2_bt_navigator', 'nav2_bt_navigator::BtNavigator', 'bt_navigator'),
            component('nav2_velocity_smoother', 'nav2_velocity_smoother::VelocitySmoother', 'velocity_smoother',
                      to_smoother),
            component('nav2_collision_monitor', 'nav2_collision_monitor::CollisionMonitor', 'collision_monitor'),

            ComposableNode(package='nav2_lifecycle_manager', plugin='nav2_lifecycle_manager::LifecycleManager',
                           name='lifecycle_manager_navigation',
                           parameters=[{'autostart': True, 'node_names': LIFECYCLE_NODES,
                                        'bond_timeout': BOND_TIMEOUT}]),
        ]),
    ])
