import argparse
import logging
import time
from typing import Optional, Tuple

import numpy as np
import matplotlib.pyplot as plt
import pygame


def read_axis_pair(joy: "pygame.joystick.Joystick", x_idx: int, y_idx: int, invert_y: bool) -> Tuple[float, float]:
    x = joy.get_axis(x_idx)
    y = joy.get_axis(y_idx)
    if invert_y:
        y = -y
    return x, y


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def setup_plot() -> Tuple[plt.Figure, plt.Axes, any, any, any]:
    fig, ax = plt.subplots(figsize=(8, 8))
    ax.set_xlim(-1.5, 1.5)
    ax.set_ylim(-1.5, 1.5)
    ax.set_aspect('equal')
    ax.grid(True, alpha=0.3)
    ax.set_xlabel('X')
    ax.set_ylabel('Y')
    ax.set_title('Left stick = vector, Right stick X = rotation')

    # Vector from origin
    # Use a single quiver we update with set_UVC
    vec = ax.quiver(0, 0, 0, 0, scale=1, scale_units='xy', angles='xy', color='blue', linewidth=2)

    # Arc line and optional arrowhead for direction
    arc_line, = ax.plot([], [], 'r-', linewidth=2, label='Arc')
    arc_arrow = ax.quiver([], [], [], [], scale=1, scale_units='xy', color='red', linewidth=2)
    plt.ion()
    plt.show(block=False)
    return fig, ax, vec, arc_line, arc_arrow


def update_plot(ax: plt.Axes, vec, arc_line, arc_arrow, x: float, y: float, arc_value: float) -> None:
    # Update vector
    vec.set_UVC(x, y)

    # Compute arc based on arc_value in [-1, 1]
    arc_value = clamp(arc_value, -1.0, 1.0)
    arc_radius = 1.0
    center_x, center_y = 0.0, 0.0
    start_angle = np.pi / 2  # start at (0,1)
    arc_angle = -arc_value * np.pi  # positive -> clockwise
    end_angle = start_angle + arc_angle

    if abs(arc_angle) < 1e-6:
        # Degenerate arc: clear
        arc_line.set_data([], [])
        arc_arrow.set_offsets(np.array([[0.0, 0.0]]))
        arc_arrow.set_UVC(0.0, 0.0)
    else:
        theta = np.linspace(start_angle, end_angle, 100)
        arc_x = center_x + arc_radius * np.cos(theta)
        arc_y = center_y + arc_radius * np.sin(theta)
        arc_line.set_data(arc_x, arc_y)

        # Arrow slightly before end, tangent direction
        arrow_angle = end_angle - np.sign(arc_angle) * 0.1
        arrow_x = center_x + arc_radius * np.cos(arrow_angle)
        arrow_y = center_y + arc_radius * np.sin(arrow_angle)
        dx = -arc_radius * np.sin(arrow_angle) * 0.1
        dy = arc_radius * np.cos(arrow_angle) * 0.1
        arc_arrow.set_offsets(np.array([[arrow_x, arrow_y]]))
        arc_arrow.set_UVC(dx, dy)

    ax.set_title(f'Vector: ({x:.2f}, {y:.2f})  Arc: {arc_value:.2f}')


def main() -> None:
    parser = argparse.ArgumentParser(description='Live plot: left stick -> vector, right stick X -> rotation')
    parser.add_argument('--list', action='store_true', help='List controllers and exit')
    parser.add_argument('--index', type=int, help='Controller index to use (see --list)')
    parser.add_argument('--name', type=str, help='Controller name substring (case-insensitive)')
    parser.add_argument('--deadzone', type=float, default=0.10, help='Deadzone for sticks (0-1)')
    parser.add_argument('--interval', type=float, default=0.03, help='Refresh interval seconds (target ~33 FPS)')
    parser.add_argument('--left-axes', type=str, default='0,1', help="Left stick axes 'x,y' (default 0,1)")
    parser.add_argument('--right-x', type=int, default=2, help='Right stick X axis index (default 2; try 3 or 4 on some controllers)')
    parser.add_argument('--invert-left-y', dest='invert_left_y', action='store_true', default=True, help='Invert left stick Y (default: inverted)')
    parser.add_argument('--no-invert-left-y', dest='invert_left_y', action='store_false', help='Do not invert left stick Y')
    parser.add_argument('--invert-right-x', action='store_true', help='Invert right stick X')
    parser.add_argument('--loglevel', default='info', choices=['debug', 'info', 'warning', 'error', 'critical'])
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.loglevel.upper()), format='%(asctime)s - %(levelname)s - %(message)s')

    # Init pygame and joystick
    pygame.init()
    pygame.joystick.init()

    num = pygame.joystick.get_count()
    if args.list:
        print('Controllers:')
        if num == 0:
            print('  (none found)')
        else:
            for i in range(num):
                j = pygame.joystick.Joystick(i)
                print(f'  [{i}] {j.get_name()}')
        return

    if num == 0:
        logging.error('No controller detected. Pair/connect it via Bluetooth first.')
        return

    selected: Optional[int] = None
    if args.index is not None:
        if 0 <= args.index < num:
            selected = args.index
        else:
            logging.error('--index out of range (0-%d).', num - 1)
            return
    elif args.name:
        target = args.name.lower()
        matches = []
        for i in range(num):
            j = pygame.joystick.Joystick(i)
            if target in j.get_name().lower():
                matches.append(i)
        if not matches:
            logging.error("No controller matching '%s'", args.name)
            return
        if len(matches) > 1:
            logging.error("Multiple controllers match '%s': %s. Use --index.", args.name, matches)
            return
        selected = matches[0]
    else:
        selected = 0

    joy = pygame.joystick.Joystick(selected)
    joy.init()
    logging.info('Using controller [%d]: %s', selected, joy.get_name())

    # Parse left axes
    try:
        left_x_idx_str, left_y_idx_str = args.left_axes.split(',')
        left_x_idx = int(left_x_idx_str.strip())
        left_y_idx = int(left_y_idx_str.strip())
    except Exception:
        logging.error("Invalid --left-axes value '%s'. Use 'x,y' e.g. 0,1", args.left_axes)
        return

    fig, ax, vec, arc_line, arc_arrow = setup_plot()

    last_update = 0.0
    try:
        while True:
            # Handle window/quit events
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    raise KeyboardInterrupt

            now = time.time()
            if now - last_update >= args.interval:
                # Read left vector
                lx, ly = read_axis_pair(joy, left_x_idx, left_y_idx, args.invert_left_y)
                # Apply deadzone
                if abs(lx) < args.deadzone:
                    lx = 0.0
                if abs(ly) < args.deadzone:
                    ly = 0.0

                # Read right X for rotation
                rx = joy.get_axis(args.right_x)
                if args.invert_right_x:
                    rx = -rx
                if abs(rx) < args.deadzone:
                    rx = 0.0
                rx = clamp(rx, -1.0, 1.0)

                update_plot(ax, vec, arc_line, arc_arrow, lx, ly, rx)

                fig.canvas.draw_idle()
                plt.pause(0.001)
                last_update = now

    except KeyboardInterrupt:
        logging.info('Exiting...')
    finally:
        pygame.quit()


if __name__ == '__main__':
    main()



