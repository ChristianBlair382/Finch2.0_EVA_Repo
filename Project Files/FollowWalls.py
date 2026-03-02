from RoomFinch import RoomFinch

# Currently assumes right angle turns in the room, so pathing will be very square, can change in the future.
def follow_walls(finch: RoomFinch):
    """Drives the finch to hug the right wall around the room, and stops once it returns to the origin"""

    # Drive up to the first wall to begin loop
    print("Approaching first wall...")
    while finch.scanObstacle() > finch.FRONT_WALL_DIST:
        finch.moveForward()

    # Turn left so the wall is to the right
    finch.turnLeft(90)

    step_count = 0
    print("Starting to follow wall")

    while True:
        front = finch.scanObstacle()
        step_count += 1

        # Inside Corner Case: Turn left if wall ahead
        if front < finch.FRONT_WALL_DIST:
            print(f"  Steps: {step_count}: wall ahead — turning left  {finch.getPosition()}")
            finch.turnLeft(90)

        else:
            finch.moveForward()
            # Checks right side 
            side = finch.checkRight()

            if side < finch.SIDE_CHECK_DIST:
                # Wall is still on the right, so do nothing
                print(f"  Steps: {step_count}: wall on right — straight  {finch.getPosition()}")
            else:
                # Wall is gone, so turn right and go forward
                print(f"  Steps: {step_count}: outward corner — turning right  {finch.getPosition()}")
                finch.turnRight(90)
                finch.moveForward()

        # End of cycle, checks if finch is back at origin
        if finch.hasReturnedToOrigin(step_count):
            print(f"Full cycle complete at step {step_count}!  Final pos: {finch.getPosition()}")
            break

    finch.stop()
    finch.stopAll()


if __name__ == "__main__":
    robot = RoomFinch(device='A', maxLinearSpeed=40, maxRotationSpeed=40)
    follow_walls(robot)