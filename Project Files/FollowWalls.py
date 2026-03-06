from RoomFinch import RoomFinch
from room_map import Room_Map
# |==================================|
# |Deprecated, replaced by roomnav.py|
# |==================================|
# Currently assumes right angle turns in the room, so pathing will be very square, can change in the future.
def follow_walls(finch: RoomFinch):
    """Drives the finch to hug the right wall around the room, and stops once it returns to the origin"""

    finch.setBeakColor(0, 0, 255)  # Set beak LED to blue (starting state)
    # Ask user to choose mode
    print("Select mode:")
    print("A = Automatic (start mapping)")
    print("M = Manual override")

    choice = input("Enter A or M: ").strip().upper()
    if choice == "M":
        finch.manual_override()  # enter manual mode
        return
    
    # Drive up to the first wall to begin loop
    print("Approaching first wall...")
    while finch.scanObstacle() > finch.FRONT_WALL_DIST:
        finch.playBeep(60, 1)
        finch.moveForward()
        finch.recordSensors()  # Record light and temperature while approaching first wall
    
    # Turn left so the wall is to the right
    finch.turnLeft(90)

    step_count = 0
    print("Starting to follow wall")
    finch.setBeakColor(255, 255, 0)  # Change beak LED to yellow (actively mapping)


    while True:
        front = finch.scanObstacle()
        step_count += 1

        # Inside Corner Case: Turn left if wall ahead
        if front < finch.FRONT_WALL_DIST:
            finch.playBeep(40, 150)  # Low beep when obstacle ahead
            print(f"  Steps: {step_count}: wall ahead — turning left  {finch.getPosition()}")
            finch.turnLeft(90)

        else:
            finch.moveForward()
            finch.recordSensors()  # Record sensors after each forward movement

            # Checks right side 
            side = finch.checkRight()

            if side < finch.SIDE_CHECK_DIST:
                # Wall is still on the right, so do nothing
                print(f"  Steps: {step_count}: wall on right — straight  {finch.getPosition()}")
            else:
                finch.playBeep(80, 150)  # Higher beep for outward corner
                # Wall is gone, so turn right and go forward
                print(f"  Steps: {step_count}: outward corner — turning right  {finch.getPosition()}")
                finch.moveForward(20)
                finch.recordSensors()  # Record sensors after extra outward corner movement
                finch.turnRight(90)
                

        # End of cycle, checks if finch is back at origin
        if finch.hasReturnedToOrigin(step_count):
            print(f"Full cycle complete at step {step_count}!  Final pos: {finch.getPosition()}")
            break

    finch.stop()
    finch.stopAll()
    finch.setBeakColor(0, 255, 0)  # Green beak LED to indicate completion
    finch.playSuccessSound()  # Play success melody

    smile = [
        [0, 1, 0, 1, 0],
        [0, 1, 0, 1, 0],
        [0, 0, 0, 0, 0],
        [1, 0, 0, 0, 1],
        [0, 1, 1, 1, 0]
    ]
        
    finch.displaySymbol(smile)  # Display smile face on 5x5 LED matrix
    print("\nRoom Data Summary")
    print(f"Average Temperature: {round(finch.getAverageTemperature(), 2)} °C")  # Display average temperature
    print(f"Average Light Level: {round(finch.getAverageLight(), 2)}")           # Display average light level


if __name__ == "__main__":
    robot = RoomFinch(device='A', maxLinearSpeed=40, maxRotationSpeed=40)
    follow_walls(robot)
