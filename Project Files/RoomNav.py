from RoomFinch import RoomFinch
from room_map import Room_Map
import threading

def manual_override(finch: RoomFinch):
    """Manual control of the Finch using letters. Q to quit manual mode."""
    print("\n--- MANUAL OVERRIDE MODE ---")
    print("F = Forward | B = Backward | L = Turn Left | R = Turn Right | Q = Exit\n")

    while True:
        choice = input("Enter command: ").strip().upper()
        if choice == "F":
            finch.moveForward(10)  # Move forward 10 cm
        elif choice == "B":
            finch.moveBackward(10)  # Move backward 10 cm
        elif choice == "L":
            finch.turnLeft(15) # Turn left 15 degrees
        elif choice == "R":
            finch.turnRight(15) # Turn right 15 degrees
        elif choice == "Q":
            finch.stopAll()
            print("\nExiting manual override mode.\n")
            break
        else:
            print("Invalid command, try again.")

def navigate_room(finch: RoomFinch):
    """Navigates the room"""
    